import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.providers.registry import get_dhcp_providers
from app.providers.dhcp.base import DHCPReservation, DHCPScope
from app.models.cache import CachedDHCPScope, CachedDHCPLease
from app.core.deps import require_operator
from app.core.audit import write_audit
from app.core.time import utcnow
from app.core.errors import raise_provider_error, provider_unconfigured

logger = logging.getLogger(__name__)
router = APIRouter()


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
def list_leases(scope_id: str, source: str = Query(""), db: Session = Depends(get_db)):
    q = db.query(CachedDHCPLease).filter(CachedDHCPLease.scope_id == scope_id)
    if source:
        q = q.filter(CachedDHCPLease.source == source)
    rows = q.all()
    return [
        {
            "scope_id": r.scope_id, "ip_address": r.ip_address,
            "mac_address": r.mac_address, "client_duid": r.client_duid,
            "iaid": r.iaid, "name": r.name, "description": r.description,
            "synced_at": r.synced_at.isoformat() + "Z" if r.synced_at else None,
        }
        for r in rows
    ]


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


@router.post("/scopes/{scope_id:path}/reservations", response_model=DHCPReservation, status_code=201)
def add_reservation(
    scope_id: str,
    reservation: DHCPReservation,
    source: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    reservation.scope_id = scope_id
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        provider_unconfigured("dhcp")
    try:
        target.add_reservation(reservation)
    except Exception as e:
        raise_provider_error(e, step="dhcp", user=current_user)

    now = utcnow()
    db.add(CachedDHCPLease(
        scope_id=scope_id, ip_address=reservation.ip_address,
        mac_address=reservation.mac_address, client_duid=reservation.client_duid,
        iaid=reservation.iaid, name=reservation.name,
        description=reservation.description, source=target.source, synced_at=now,
    ))
    write_audit(db, current_user.username, "create", "dhcp_reservation",
                reservation.ip_address,
                f"{reservation.ip_address} ({reservation.name})",
                after=reservation.model_dump())
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
