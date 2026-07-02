import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.subnet import Subnet
from app.providers.registry import get_dhcp_providers, get_dns_providers
from app.providers.dhcp.base import DHCPReservation, DHCPScope
from app.providers.dns.base import DNSRecord
from app.models.cache import CachedDHCPScope, CachedDHCPLease, CachedDNSRecord, CachedDNSZone
from app.core.deps import require_operator
from app.core.audit import write_audit
from app.core.time import utcnow
from app.core.errors import raise_provider_error, provider_unconfigured
from app.core.pagination import paginate
from app.utils import ip_in_cidr

logger = logging.getLogger(__name__)
router = APIRouter()

DHCP_SORT_MAP = {
    "ip_address": CachedDHCPLease.ip_address,
    "name":       CachedDHCPLease.name,
}


@router.get("/scopes", response_model=list[DHCPScope])
def list_scopes(db: Session = Depends(get_db)):
    rows = db.query(CachedDHCPScope).all()
    return [
        DHCPScope(
            scope_id=r.scope_id, name=r.name, subnet_mask=r.subnet_mask,
            start_range=r.start_range, end_range=r.end_range,
            description=r.description, active=r.active,
            ip_version=r.ip_version, source=r.source,
        )
        for r in rows
    ]


@router.get("/scopes/{scope_id:path}/leases")
def list_leases(
    scope_id: str,
    source: str = Query(""),
    q: str | None = Query(None),
    sort: str = Query(""),
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(CachedDHCPLease).filter(CachedDHCPLease.scope_id == scope_id)
    if source:
        query = query.filter(CachedDHCPLease.source == source)
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(
            CachedDHCPLease.ip_address.ilike(pattern),
            CachedDHCPLease.mac_address.ilike(pattern),
            CachedDHCPLease.name.ilike(pattern),
        ))
    result = paginate(query, limit=limit, offset=offset,
                      sort_map=DHCP_SORT_MAP, sort=sort, dir=dir,
                      tiebreaker=CachedDHCPLease.id.asc())
    items = [
        {
            "scope_id": r.scope_id, "ip_address": r.ip_address,
            "mac_address": r.mac_address, "client_duid": r.client_duid,
            "iaid": r.iaid, "name": r.name, "description": r.description,
            "synced_at": r.synced_at.isoformat() + "Z" if r.synced_at else None,
        }
        for r in result["items"]
    ]
    return {"items": items, "total": result["total"],
            "limit": result["limit"], "offset": result["offset"]}


@router.get("/by-ip/{address}")
def get_leases_by_ip(address: str, db: Session = Depends(get_db)):
    rows = db.query(CachedDHCPLease).filter(CachedDHCPLease.ip_address == address).all()
    return [
        {
            "scope_id": r.scope_id, "ip_address": r.ip_address,
            "mac_address": r.mac_address, "client_duid": r.client_duid,
            "iaid": r.iaid, "name": r.name, "description": r.description,
            "source": r.source,
            "synced_at": r.synced_at.isoformat() + "Z" if r.synced_at else None,
        }
        for r in rows
    ]


def _resolve_dns_provider(explicit: str | None, subnet_default: str | None):
    """Explicit name wins, else the subnet's configured DNS provider, else the
    first enabled one. Returns None when no DNS provider is configured."""
    provs = get_dns_providers()
    if not provs:
        return None
    if explicit:
        return next((p for p in provs if p.source == explicit), None)
    if subnet_default:
        match = next((p for p in provs if p.source == subnet_default), None)
        if match:
            return match
    return provs[0]


@router.post("/scopes/{scope_id:path}/reservations", response_model=DHCPReservation, status_code=201)
def add_reservation(
    scope_id: str,
    reservation: DHCPReservation,
    source: str = Query(""),
    register_dns: bool = Query(False),
    dns_zone: str = Query(""),
    dns_provider: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    reservation.scope_id = scope_id
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        provider_unconfigured("dhcp")

    # DHCP-DNS-LINK-001: optionally also create the matching A/AAAA record.
    # Validate everything BEFORE touching the DHCP provider so a bad request
    # never leaves a reservation behind.
    dns_prov = None
    if register_dns:
        if not (dns_zone or "").strip():
            raise HTTPException(422, "dns_zone is required when register_dns is true")
        if not (reservation.name or "").strip():
            raise HTTPException(422, "name is required to create a DNS record")
        subnet = next(
            (s for s in db.query(Subnet).all() if ip_in_cidr(reservation.ip_address, s.cidr)),
            None,
        )
        dns_prov = _resolve_dns_provider(dns_provider, subnet.dns_provider_name if subnet else None)
        if dns_prov is None:
            raise HTTPException(400, "No DNS provider available")

    try:
        target.add_reservation(reservation)
    except Exception as e:
        raise_provider_error(e, step="dhcp", user=current_user)

    now = utcnow()
    a_record: DNSRecord | None = None
    if register_dns and dns_prov:
        a_record = DNSRecord(
            name=reservation.name,
            record_type="AAAA" if ":" in reservation.ip_address else "A",
            value=reservation.ip_address, zone=dns_zone,
        )
        try:
            dns_prov.add_record(a_record)
        except Exception as e:
            # Roll back the DHCP reservation we just created so the two backends
            # don't diverge, then surface the DNS error.
            try:
                target.delete_reservation(scope_id, reservation.ip_address)
            except Exception:
                logger.warning("rollback delete_reservation failed for %s/%s",
                               scope_id, reservation.ip_address)
            raise_provider_error(e, step="dns", user=current_user)

    db.add(CachedDHCPLease(
        scope_id=scope_id, ip_address=reservation.ip_address,
        mac_address=reservation.mac_address, client_duid=reservation.client_duid,
        iaid=reservation.iaid, name=reservation.name,
        description=reservation.description, source=target.source, synced_at=now,
    ))
    if a_record is not None and dns_prov is not None:
        db.query(CachedDNSRecord).filter_by(
            name=a_record.name, record_type=a_record.record_type,
            zone=a_record.zone, source=dns_prov.source,
        ).delete()
        db.add(CachedDNSRecord(
            name=a_record.name, record_type=a_record.record_type,
            value=a_record.value, zone=a_record.zone, ttl=a_record.ttl,
            source=dns_prov.source, synced_at=now,
        ))
        if db.get(CachedDNSZone, (a_record.zone, dns_prov.source)) is None:
            db.add(CachedDNSZone(zone=a_record.zone, source=dns_prov.source, synced_at=now))

    write_audit(db, current_user.username, "create", "dhcp_reservation",
                reservation.ip_address,
                f"{reservation.ip_address} ({reservation.name})",
                after={**reservation.model_dump(), "dns_registered": a_record is not None})
    db.commit()
    return reservation


@router.delete("/scopes/{scope_id:path}/reservations/{ip_address}", status_code=204)
def delete_reservation(
    scope_id: str,
    ip_address: str,
    source: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        provider_unconfigured("dhcp")
    try:
        target.delete_reservation(scope_id, ip_address)
    except Exception as e:
        raise_provider_error(e, step="dhcp", user=current_user)

    lease = db.query(CachedDHCPLease).filter(
        CachedDHCPLease.scope_id == scope_id,
        CachedDHCPLease.ip_address == ip_address,
        CachedDHCPLease.source == target.source,
    ).first()
    if lease is None:
        logger.warning("delete_reservation: no cached lease for %s/%s", scope_id, ip_address)
    before = {
        "scope_id": scope_id, "ip_address": ip_address, "source": target.source,
        "name": lease.name if lease else None,
        "mac_address": lease.mac_address if lease else None,
        "client_duid": lease.client_duid if lease else None,
        "iaid": lease.iaid if lease else None,
        "description": lease.description if lease else None,
    }
    if lease:
        db.delete(lease)
    write_audit(db, current_user.username, "delete", "dhcp_reservation",
                ip_address, ip_address, before=before)
    db.commit()
