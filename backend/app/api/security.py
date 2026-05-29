"""SECURITY-001 — security event API: list, acknowledge, quarantine."""
import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.custom_fields import add_tags
from app.core.deps import get_current_user, require_operator
from app.core.time import utcnow
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.security import SecurityEvent
from app.models.subnet import Subnet
from app.models.user import User
from app.utils import ip_in_cidr

router = APIRouter()


def _out(e: SecurityEvent) -> dict:
    return {
        "id": e.id, "event_type": e.event_type, "severity": e.severity,
        "mac": e.mac, "ip": e.ip, "details": e.details,
        "detected_at": e.detected_at.isoformat() + "Z" if e.detected_at else None,
        "acknowledged": e.acknowledged,
        "acknowledged_at": e.acknowledged_at.isoformat() + "Z" if e.acknowledged_at else None,
        "quarantined": e.quarantined,
    }


@router.get("/events")
def list_events(
    event_type: str | None = Query(None),
    severity: str | None = Query(None),
    acknowledged: bool | None = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(SecurityEvent)
    if event_type is not None:
        q = q.filter(SecurityEvent.event_type == event_type)
    if severity is not None:
        q = q.filter(SecurityEvent.severity == severity)
    if acknowledged is not None:
        q = q.filter(SecurityEvent.acknowledged == acknowledged)
    return [_out(e) for e in q.order_by(SecurityEvent.detected_at.desc()).all()]


@router.post("/events/{event_id}/ack")
def acknowledge(event_id: int, current_user: User = Depends(require_operator), db: Session = Depends(get_db)):
    e = db.get(SecurityEvent, event_id)
    if e is None:
        raise HTTPException(404, "Event not found")
    e.acknowledged = True
    e.acknowledged_at = utcnow()
    write_audit(db, current_user.username, "ack", "security_event", str(e.id), f"{e.event_type} {e.ip or e.mac}")
    db.commit()
    return _out(e)


@router.post("/events/{event_id}/quarantine")
def quarantine(event_id: int, current_user: User = Depends(require_operator), db: Session = Depends(get_db)):
    e = db.get(SecurityEvent, event_id)
    if e is None:
        raise HTTPException(404, "Event not found")
    if not e.ip:
        raise HTTPException(400, "Event has no IP to quarantine")

    addr = db.query(IPAddress).filter_by(address=e.ip).first()
    if addr is None:
        subnet = next((s for s in db.query(Subnet).all() if ip_in_cidr(e.ip, s.cidr)), None)
        if subnet is None:
            raise HTTPException(422, "No subnet contains this IP; cannot quarantine")
        addr = IPAddress(address=e.ip, subnet_id=subnet.id, status=AddressStatus.deprecated,
                         mac_address=e.mac or None)
        db.add(addr)
        db.flush()
    else:
        addr.status = AddressStatus.deprecated
    add_tags(db, "address", addr.id, ["quarantined"])

    e.quarantined = True
    e.acknowledged = True
    e.acknowledged_at = utcnow()
    write_audit(db, current_user.username, "quarantine", "security_event", str(e.id), f"{e.event_type} {e.ip}")
    db.commit()
    return _out(e)
