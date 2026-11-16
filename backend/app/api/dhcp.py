import json
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.provider_config import ProviderConfig
from app.models.subnet import Subnet
from app.providers.registry import get_dhcp_providers, get_dns_providers
from app.providers.dhcp.base import DHCPReservation, DHCPScope, DHCPScopeOption
from app.providers.dns.base import DNSRecord
from app.models.cache import CachedDHCPScope, CachedDHCPScopePool, CachedDHCPScopeConfig, CachedDHCPLease, CachedDNSRecord, CachedDNSZone
from app.models.dhcp_scope_override import DHCPScopeReservedSyncExclusion, DHCPScopeSubnetAutoCreateExclusion
from app.core.deps import require_operator
from app.core.audit import write_audit
from app.core.time import utcnow
from app.core.errors import raise_provider_error, provider_unconfigured
from app.core.pagination import paginate
from app.core.ip_sort import ip_sort_key
from app.utils import ip_in_cidr

logger = logging.getLogger(__name__)
router = APIRouter()

DHCP_SORT_MAP = {
    # ip_sort_key, not ip_address itself — numeric IP order, not
    # lexicographic string order (see app/core/ip_sort.py).
    "ip_address": CachedDHCPLease.ip_sort_key,
    "name":       CachedDHCPLease.name,
}


def _pool_ranges(scope: CachedDHCPScope,
                 pools: dict[tuple[str, str], list[tuple[str, str]]]) -> list[tuple[str, str]]:
    """Every pool range of an IPv4 scope: the per-pool rows when synced (a Kea
    subnet can have several), else the scope's collapsed start/end range."""
    ranges = pools.get((scope.source, scope.scope_id))
    if ranges:
        return ranges
    if scope.start_range and scope.end_range:
        return [(scope.start_range, scope.end_range)]
    return []


def _pool_utilization(db: Session, scope: CachedDHCPScope,
                      ranges: list[tuple[str, str]]) -> tuple[int | None, int | None]:
    """(size, used) across the scope's pool ranges. Used counts every cached
    lease/reservation whose IP falls inside a pool — scope-wide, independent of
    any list search or paging."""
    size = used = 0
    for start, end in ranges:
        lo, hi = ip_sort_key(start), ip_sort_key(end)
        if lo is None or hi is None or hi < lo:
            continue
        size += int.from_bytes(hi, "big") - int.from_bytes(lo, "big") + 1
        used += (
            db.query(func.count(CachedDHCPLease.id))
            .filter(CachedDHCPLease.scope_id == scope.scope_id,
                    CachedDHCPLease.source == scope.source,
                    CachedDHCPLease.ip_sort_key >= lo,
                    CachedDHCPLease.ip_sort_key <= hi)
            .scalar() or 0
        )
    return (size, used) if size > 0 else (None, None)


def _options_of(cfg: CachedDHCPScopeConfig | None) -> list[DHCPScopeOption]:
    if cfg is None:
        return []
    try:
        return [DHCPScopeOption(**o) for o in json.loads(cfg.options_json or "[]")]
    except (ValueError, TypeError):
        return []


def _providers_with_auto_create(db: Session) -> set[str]:
    """Names of enabled DHCP providers whose config turns on subnet auto-creation."""
    names: set[str] = set()
    for row in db.query(ProviderConfig).filter(
        ProviderConfig.category == "dhcp", ProviderConfig.enabled == True,  # noqa: E712
    ).all():
        try:
            if json.loads(row.config or "{}").get("auto_create_subnets"):
                names.add(row.name)
        except ValueError:
            continue
    return names


@router.get("/scopes", response_model=list[DHCPScope])
def list_scopes(db: Session = Depends(get_db)):
    rows = db.query(CachedDHCPScope).all()
    excluded = {
        (row.source, row.scope_id)
        for row in db.query(DHCPScopeReservedSyncExclusion).all()
    }
    no_autocreate = {
        (row.source, row.scope_id)
        for row in db.query(DHCPScopeSubnetAutoCreateExclusion).all()
    }
    provider_auto = _providers_with_auto_create(db)
    scope_cfg = {(c.source, c.scope_id): c for c in db.query(CachedDHCPScopeConfig).all()}
    pools: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for p in db.query(CachedDHCPScopePool).all():
        pools.setdefault((p.source, p.scope_id), []).append((p.start_ip, p.end_ip))
    lease_counts = {
        (src, sid): n for src, sid, n in
        db.query(CachedDHCPLease.source, CachedDHCPLease.scope_id, func.count(CachedDHCPLease.id))
        .group_by(CachedDHCPLease.source, CachedDHCPLease.scope_id).all()
    }
    out = []
    for r in rows:
        size = used = None
        if r.ip_version == 4:
            size, used = _pool_utilization(db, r, _pool_ranges(r, pools))
        out.append(DHCPScope(
            scope_id=r.scope_id, name=r.name, subnet_mask=r.subnet_mask,
            start_range=r.start_range, end_range=r.end_range,
            description=r.description, active=r.active,
            ip_version=r.ip_version, source=r.source,
            sync_reserved_ranges=(r.source, r.scope_id) not in excluded,
            auto_create_subnet=(r.source, r.scope_id) not in no_autocreate,
            provider_auto_create_subnets=r.source in provider_auto,
            lease_seconds=cfg.lease_seconds if (cfg := scope_cfg.get((r.source, r.scope_id))) else None,
            options=_options_of(cfg),
            pool_size=size, pool_used=used,
            lease_count=lease_counts.get((r.source, r.scope_id), 0),
        ))
    return out


class ReservedSyncUpdate(BaseModel):
    enabled: bool


@router.put("/scopes/{scope_id:path}/reserved-sync")
def set_scope_reserved_sync(
    scope_id: str,
    body: ReservedSyncUpdate,
    source: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Toggle whether this scope's gateway/exclusions feed the Reserved
    Ranges auto-sync (sync.py's sync_dhcp). Only affects the next sync
    pass — leases/pools for the scope keep syncing either way."""
    existing = db.query(DHCPScopeReservedSyncExclusion).filter_by(
        source=source, scope_id=scope_id,
    ).first()

    if body.enabled:
        if existing:
            db.delete(existing)
    else:
        if not existing:
            db.add(DHCPScopeReservedSyncExclusion(source=source, scope_id=scope_id))

    write_audit(
        db, current_user.username, "update", "dhcp_scope_reserved_sync", f"{source}/{scope_id}",
        f"{'enabled' if body.enabled else 'disabled'} Reserved Ranges sync for scope {scope_id} ({source})",
    )
    db.commit()
    return {"source": source, "scope_id": scope_id, "sync_reserved_ranges": body.enabled}


class AutoCreateSubnetUpdate(BaseModel):
    enabled: bool


@router.put("/scopes/{scope_id:path}/auto-create-subnet")
def set_scope_auto_create_subnet(
    scope_id: str,
    body: AutoCreateSubnetUpdate,
    source: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Per-scope switch for subnet auto-creation. Only matters when the
    scope's provider has auto_create_subnets on; affects the next sync."""
    existing = db.query(DHCPScopeSubnetAutoCreateExclusion).filter_by(
        source=source, scope_id=scope_id,
    ).first()
    if body.enabled:
        if existing:
            db.delete(existing)
    elif not existing:
        db.add(DHCPScopeSubnetAutoCreateExclusion(source=source, scope_id=scope_id))

    write_audit(
        db, current_user.username, "update", "dhcp_scope_subnet_autocreate", f"{source}/{scope_id}",
        f"{'enabled' if body.enabled else 'disabled'} subnet auto-creation for scope {scope_id} ({source})",
    )
    db.commit()
    return {"source": source, "scope_id": scope_id, "auto_create_subnet": body.enabled}


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


class UpdateReservationRequest(BaseModel):
    old: DHCPReservation
    new: DHCPReservation


class UpdateReservationResponse(DHCPReservation):
    dns_stale: bool = False


@router.put("/scopes/{scope_id:path}/reservations/{ip_address}", response_model=UpdateReservationResponse)
def update_reservation(
    scope_id: str,
    ip_address: str,
    body: UpdateReservationRequest,
    source: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    old, new = body.old, body.new
    if new.ip_address != old.ip_address:
        raise HTTPException(422, "ip_address cannot change on an edit — delete and recreate instead")

    old.scope_id = scope_id
    old.ip_address = ip_address
    new.scope_id = scope_id
    new.ip_address = ip_address

    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        provider_unconfigured("dhcp")

    lease = db.query(CachedDHCPLease).filter_by(
        scope_id=scope_id, ip_address=ip_address, source=target.source,
    ).first()
    if lease is None:
        raise HTTPException(404, "reservation not found")

    try:
        target.update_reservation(old, new)
    except Exception as e:
        raise_provider_error(e, step="dhcp", user=current_user)

    # DHCP-DNS-LINK-001: a hostname change can leave a co-managed A/AAAA
    # record stale. P3 does not follow it through — surface staleness like
    # DNS's ptr_stale, so the UI/drift can flag it instead of hiding it.
    dns_stale = (
        new.name != old.name
        and db.query(CachedDNSRecord).filter_by(name=old.name, value=ip_address).first() is not None
    )

    now = utcnow()
    try:
        lease.mac_address = new.mac_address
        lease.client_duid = new.client_duid
        lease.iaid = new.iaid
        lease.name = new.name
        lease.description = new.description
        lease.synced_at = now
        write_audit(db, current_user.username, "update", "dhcp_reservation",
                    ip_address, f"{ip_address} ({old.name} -> {new.name})",
                    before=old.model_dump(), after=new.model_dump())
        db.commit()
    except Exception as e:
        db.rollback()
        try:
            target.update_reservation(new, old)
        except Exception as exc:
            logger.warning("provider update_reservation undo failed for %s/%s: %s",
                           scope_id, ip_address, exc)
        logger.error("DHCP update_reservation cache update failed: %s", e, exc_info=True)
        raise HTTPException(502, f"DHCP reservation update failed: {e}")

    return UpdateReservationResponse(**new.model_dump(), dns_stale=dns_stale)


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
