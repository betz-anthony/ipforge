import logging
import threading
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import get_current_user
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord
from app.models.cache import SyncStatus
from app.models.scan import Collision, ScanResult
from app.models.subnet import Subnet
from app.models.user import User
from app.providers.dhcp.base import DHCPReservation
from app.providers.dns.base import DNSRecord
from app.providers.registry import get_dhcp_providers, get_dns_providers
from app.utils import ip_in_cidr

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _age(synced_at) -> int | None:
    if synced_at is None:
        return None
    return max(0, int((_utcnow() - synced_at).total_seconds()))


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


class CollisionResponse(BaseModel):
    id: int
    ip_address: str
    collision_type: Literal["active_but_available", "multi_dhcp_scope", "hostname_mismatch"]
    details: str | None
    detected_at: str | None
    resolved: bool
    resolved_at: str | None


class CollisionResolveRequest(BaseModel):
    new_status:         str | None       = None  # active_but_available
    canonical_hostname: str | None       = None  # hostname_mismatch
    sources_to_remove:  list[str] | None = None  # multi_dhcp_scope


class ResolveResponse(BaseModel):
    id: int
    resolved: bool


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


@router.get("/collisions", response_model=list[CollisionResponse])
def list_collisions(
    resolved:  bool       = Query(False),
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
            collisions = [c for c in collisions if ip_in_cidr(c.ip_address, subnet.cidr)]

    return [
        CollisionResponse(
            id=c.id,
            ip_address=c.ip_address,
            collision_type=c.collision_type,
            details=c.details,
            detected_at=c.detected_at.isoformat() + "Z" if c.detected_at else None,
            resolved=c.resolved,
            resolved_at=c.resolved_at.isoformat() + "Z" if c.resolved_at else None,
        )
        for c in collisions
    ]


@router.put("/collisions/{collision_id}/resolve", response_model=ResolveResponse)
def resolve_collision(
    collision_id: int,
    body: CollisionResolveRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(Collision, collision_id)
    if not c:
        raise HTTPException(404, "Collision not found")

    action_taken: dict = {}

    if body:
        if c.collision_type == "active_but_available" and body.new_status:
            try:
                new_status = AddressStatus(body.new_status)
            except ValueError:
                raise HTTPException(422, f"Invalid status: {body.new_status}")
            addr = db.query(IPAddress).filter_by(address=c.ip_address).first()
            if addr is None:
                raise HTTPException(422, "No IPAM record found for this IP")
            addr.status = new_status
            action_taken = {"new_status": body.new_status}

    c.resolved    = True
    c.resolved_at = _utcnow()
    db.flush()
    write_audit(
        db, current_user.username, "resolve", "collision", str(c.id),
        f"{c.collision_type} {c.ip_address}",
        after=action_taken if action_taken else None,
    )
    db.commit()
    return ResolveResponse(id=c.id, resolved=True)
