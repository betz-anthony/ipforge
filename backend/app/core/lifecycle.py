"""LIFECYCLE-001 — per-IP timeline + point-in-time reconstruction.

Read-only surfacing of already-captured data: audit log (address writes, keyed by
IP via the `summary` column), drift items, and reachability alert events.
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.scan import DriftItem, AlertEvent


def _loads(s: str | None) -> dict | None:
    if not s:
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def _address_audits(db: Session, ip: str) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "address", AuditLog.summary == ip)
        .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
        .all()
    )


def ip_timeline(db: Session, ip: str) -> list[dict]:
    events: list[dict] = []

    for a in _address_audits(db, ip):
        events.append({
            "ts": a.timestamp,
            "kind": "change",
            "action": a.action,
            "user": a.username,
            "summary": a.summary,
            "before": _loads(a.before_state),
            "after": _loads(a.after_state),
        })

    for d in db.query(DriftItem).filter(DriftItem.ip_address == ip).all():
        events.append({
            "ts": d.detected_at,
            "kind": "drift",
            "category": d.category,
            "severity": d.severity,
            "resolved": d.resolved,
            "resolved_at": d.resolved_at,
        })

    for e in db.query(AlertEvent).filter(AlertEvent.ip_address == ip).all():
        events.append({
            "ts": e.detected_at,
            "kind": "reachability",
            "event_type": e.event_type,
        })

    events.sort(key=lambda x: (x["ts"] or datetime.min), reverse=True)
    return events


def ip_point_in_time(db: Session, ip: str, as_of: datetime) -> dict | None:
    """Reconstruct the address state as of `as_of` from the audit trail."""
    rows = _address_audits(db, ip)
    latest = None
    for a in rows:
        if a.timestamp is not None and a.timestamp <= as_of:
            latest = a
        else:
            break
    if latest is None:
        return None
    after = _loads(latest.after_state)
    if latest.action == "delete" or after is None:
        return {"state": "unallocated", "as_of": latest.timestamp}
    return {"state": "allocated", "as_of": latest.timestamp, **after}
