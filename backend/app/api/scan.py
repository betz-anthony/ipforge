import threading
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cache import SyncStatus
from app.models.scan import Collision, ScanResult
from app.models.subnet import Subnet

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _age(synced_at) -> int | None:
    if synced_at is None:
        return None
    return max(0, int((_utcnow() - synced_at).total_seconds()))


class ScanTriggerBody(BaseModel):
    start_ip: str | None = None
    end_ip:   str | None = None


@router.post("/subnets/{subnet_id}")
def trigger_scan(
    subnet_id: int,
    body: ScanTriggerBody = ScanTriggerBody(),
    db: Session = Depends(get_db),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    from app.scan import scan_subnet
    threading.Thread(
        target=scan_subnet,
        args=(subnet_id,),
        kwargs={"start_ip": body.start_ip, "end_ip": body.end_ip},
        daemon=True,
    ).start()
    return {"status": "triggered"}


@router.get("/subnets/{subnet_id}")
def get_scan_status(subnet_id: int, db: Session = Depends(get_db)):
    key = f"scan:{subnet_id}"
    status_row = db.get(SyncStatus, key)

    all_results = (
        db.query(ScanResult)
        .filter_by(subnet_id=subnet_id)
        .order_by(ScanResult.scanned_at.desc())
        .all()
    )
    latest_results = []
    if all_results:
        latest_time = all_results[0].scanned_at
        latest_results = [
            {"ip": r.ip_address, "reachable": r.reachable, "latency_ms": r.latency_ms}
            for r in all_results
            if r.scanned_at == latest_time
        ]

    return {
        "status":      status_row.status    if status_row else "never",
        "scanned_at":  status_row.synced_at.isoformat() + "Z" if (status_row and status_row.synced_at) else None,
        "age_seconds": _age(status_row.synced_at) if status_row else None,
        "error":       status_row.error     if status_row else None,
        "results":     latest_results,
    }


@router.get("/collisions")
def list_collisions(
    resolved:  bool      = Query(False),
    subnet_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    collisions = (
        db.query(Collision)
        .filter(Collision.resolved == resolved)
        .order_by(Collision.detected_at.desc())
        .all()
    )
    if subnet_id is not None:
        subnet = db.get(Subnet, subnet_id)
        if subnet:
            from app.utils import ip_in_cidr
            collisions = [c for c in collisions if ip_in_cidr(c.ip_address, subnet.cidr)]

    return [
        {
            "id":             c.id,
            "ip_address":     c.ip_address,
            "collision_type": c.collision_type,
            "details":        c.details,
            "detected_at":    c.detected_at.isoformat() + "Z" if c.detected_at else None,
            "resolved":       c.resolved,
            "resolved_at":    c.resolved_at.isoformat() + "Z" if c.resolved_at else None,
        }
        for c in collisions
    ]


@router.put("/collisions/{collision_id}/resolve")
def resolve_collision(collision_id: int, db: Session = Depends(get_db)):
    c = db.get(Collision, collision_id)
    if not c:
        raise HTTPException(404, "Collision not found")
    c.resolved    = True
    c.resolved_at = _utcnow()
    db.commit()
    return {"id": c.id, "resolved": True}
