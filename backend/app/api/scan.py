import logging
import threading
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import get_current_user
from app.core.time import utcnow
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord
from app.models.cache import SyncStatus
from app.models.scan import Collision, ScanResult, AlertEvent
from app.models.subnet import Subnet
from app.models.user import User
from app.providers.dhcp.base import DHCPReservation
from app.providers.dns.base import DNSRecord
from app.providers.registry import get_dhcp_providers, get_dns_providers
from app.utils import ip_in_cidr

logger = logging.getLogger(__name__)
router = APIRouter()


def _age(synced_at) -> int | None:
    if synced_at is None:
        return None
    return max(0, int((utcnow() - synced_at).total_seconds()))


# ── Request / response schemas ───────────────────────────────────────────────

class ScanTriggerBody(BaseModel):
    start_ip: str | None = None
    end_ip:   str | None = None


class TriggerResponse(BaseModel):
    status: str


class ScanHostResult(BaseModel):
    ip: str
    reachable: bool
    latency_ms: float | None


class ScanStatusResponse(BaseModel):
    status: str
    scanned_at: str | None
    age_seconds: int | None
    error: str | None
    results: list[ScanHostResult]


class AlertEventRead(BaseModel):
    id: int
    event_type: str
    ip_address: str
    subnet_id: int
    detected_at: str
    details: str | None
    acknowledged: bool
    acknowledged_at: str | None


class AcknowledgeAllResponse(BaseModel):
    count: int


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/subnets/{subnet_id}", response_model=TriggerResponse)
def trigger_scan(
    subnet_id: int,
    body: ScanTriggerBody | None = None,
    db: Session = Depends(get_db),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")

    key = f"scan:{subnet_id}"
    status_row = db.get(SyncStatus, key)
    if status_row and status_row.status == "running":
        raise HTTPException(409, "Scan already running for this subnet")

    if body is None:
        body = ScanTriggerBody()

    from app.scan import scan_subnet
    threading.Thread(
        target=scan_subnet,
        args=(subnet_id,),
        kwargs={"start_ip": body.start_ip, "end_ip": body.end_ip},
        daemon=True,
    ).start()
    return TriggerResponse(status="triggered")


@router.get("/subnets/{subnet_id}", response_model=ScanStatusResponse)
def get_scan_status(subnet_id: int, db: Session = Depends(get_db)):
    key = f"scan:{subnet_id}"
    status_row = db.get(SyncStatus, key)

    all_results = (
        db.query(ScanResult)
        .filter_by(subnet_id=subnet_id)
        .order_by(ScanResult.scanned_at.desc())
        .all()
    )
    latest_results: list[ScanHostResult] = []
    if all_results:
        latest_time = all_results[0].scanned_at
        latest_results = [
            ScanHostResult(ip=r.ip_address, reachable=r.reachable, latency_ms=r.latency_ms)
            for r in all_results
            if r.scanned_at == latest_time
        ]

    return ScanStatusResponse(
        status=status_row.status if status_row else "never",
        scanned_at=status_row.synced_at.isoformat() + "Z" if (status_row and status_row.synced_at) else None,
        age_seconds=_age(status_row.synced_at) if status_row else None,
        error=status_row.error if status_row else None,
        results=latest_results,
    )


@router.get("/alerts", response_model=list[AlertEventRead])
def list_alerts(
    acknowledged: bool = Query(False),
    subnet_id: int | None = Query(None),
    limit: int = Query(50),
    db: Session = Depends(get_db),
):
    q = db.query(AlertEvent).filter(AlertEvent.acknowledged == acknowledged)
    if subnet_id is not None:
        q = q.filter(AlertEvent.subnet_id == subnet_id)
    alerts = q.order_by(AlertEvent.detected_at.desc()).limit(limit).all()
    return [
        AlertEventRead(
            id=a.id,
            event_type=a.event_type,
            ip_address=a.ip_address,
            subnet_id=a.subnet_id,
            detected_at=a.detected_at.isoformat() + "Z",
            details=a.details,
            acknowledged=a.acknowledged,
            acknowledged_at=a.acknowledged_at.isoformat() + "Z" if a.acknowledged_at else None,
        )
        for a in alerts
    ]


@router.post("/alerts/acknowledge-all", response_model=AcknowledgeAllResponse)
def acknowledge_all_alerts(
    subnet_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = utcnow()
    q = db.query(AlertEvent).filter(AlertEvent.acknowledged == False)  # noqa: E712
    if subnet_id is not None:
        q = q.filter(AlertEvent.subnet_id == subnet_id)
    count = q.update({"acknowledged": True, "acknowledged_at": now}, synchronize_session=False)
    db.commit()
    return AcknowledgeAllResponse(count=count)


@router.put("/alerts/{alert_id}/acknowledge", response_model=AlertEventRead)
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    alert = db.get(AlertEvent, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    alert.acknowledged_at = utcnow()
    db.commit()
    db.refresh(alert)
    return AlertEventRead(
        id=alert.id,
        event_type=alert.event_type,
        ip_address=alert.ip_address,
        subnet_id=alert.subnet_id,
        detected_at=alert.detected_at.isoformat() + "Z",
        details=alert.details,
        acknowledged=alert.acknowledged,
        acknowledged_at=alert.acknowledged_at.isoformat() + "Z" if alert.acknowledged_at else None,
    )
