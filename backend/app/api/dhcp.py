import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.providers.registry import get_dhcp_providers
from app.providers.dhcp.base import DHCPReservation, DHCPScope
from app.models.cache import CachedDHCPScope, CachedDHCPLease

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


@router.get("/scopes/{scope_id}/leases", response_model=list[DHCPReservation])
def list_leases(scope_id: str, source: str = Query(""), db: Session = Depends(get_db)):
    q = db.query(CachedDHCPLease).filter(CachedDHCPLease.scope_id == scope_id)
    if source:
        q = q.filter(CachedDHCPLease.source == source)
    rows = q.all()
    return [
        DHCPReservation(
            scope_id=r.scope_id, ip_address=r.ip_address,
            mac_address=r.mac_address, client_duid=r.client_duid,
            iaid=r.iaid, name=r.name, description=r.description,
        )
        for r in rows
    ]


@router.post("/scopes/{scope_id}/reservations", response_model=DHCPReservation, status_code=201)
def add_reservation(scope_id: str, reservation: DHCPReservation, source: str = Query(""),
                    db: Session = Depends(get_db)):
    reservation.scope_id = scope_id
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DHCP provider configured")
    try:
        target.add_reservation(reservation)
    except Exception as e:
        logger.error("DHCP %s add_reservation: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    now = _utcnow()
    db.add(CachedDHCPLease(
        scope_id=scope_id, ip_address=reservation.ip_address,
        mac_address=reservation.mac_address, client_duid=reservation.client_duid,
        iaid=reservation.iaid, name=reservation.name,
        description=reservation.description, source=target.source, synced_at=now,
    ))
    db.commit()
    return reservation


@router.delete("/scopes/{scope_id}/reservations/{ip_address}", status_code=204)
def delete_reservation(scope_id: str, ip_address: str, source: str = Query(""),
                       db: Session = Depends(get_db)):
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DHCP provider configured")
    try:
        target.delete_reservation(scope_id, ip_address)
    except Exception as e:
        logger.error("DHCP %s delete_reservation: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    db.query(CachedDHCPLease).filter(
        CachedDHCPLease.scope_id == scope_id,
        CachedDHCPLease.ip_address == ip_address,
        CachedDHCPLease.source == target.source,
    ).delete()
    db.commit()
