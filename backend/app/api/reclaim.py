from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.core.audit import write_audit
from app.core.deps import get_current_user, require_operator
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.subnet import Subnet
from app.models.user import User

router = APIRouter()
ro_router = APIRouter()  # read-only routes mounted before addresses.router to avoid /{id} capture

_STALE_STATUSES = (AddressStatus.reserved, AddressStatus.assigned)


def _now() -> datetime:
    # DateTime columns are naive-UTC; strip tzinfo to match
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stale_query(db: Session, subnet_id: int | None = None):
    threshold_days = settings.stale_reclaim_days
    now = _now()
    cutoff = now - timedelta(days=threshold_days)

    q = (
        db.query(IPAddress)
        .filter(IPAddress.status.in_(_STALE_STATUSES))
        .filter(IPAddress.last_seen.isnot(None))
        .filter(IPAddress.last_seen < cutoff)
        .filter(
            (IPAddress.reclaim_dismissed_until.is_(None)) |
            (IPAddress.reclaim_dismissed_until < now)
        )
    )
    if subnet_id is not None:
        q = q.filter(IPAddress.subnet_id == subnet_id)
    return q


class StaleAddress(BaseModel):
    id: int
    address: str
    subnet_id: int
    subnet_cidr: str
    hostname: str | None
    status: str
    mac_address: str | None
    last_seen: datetime | None
    days_stale: int

    model_config = {"from_attributes": True}


class ReclaimAction(BaseModel):
    action: Literal["deprecate", "extend", "dismiss"]


class BulkDeprecateRequest(BaseModel):
    subnet_id: int


def _to_stale_address(a: IPAddress, subnet_cidr: str) -> dict:
    now = _now()
    days_stale = (now - a.last_seen).days if a.last_seen else 0
    return {
        "id": a.id,
        "address": a.address,
        "subnet_id": a.subnet_id,
        "subnet_cidr": subnet_cidr,
        "hostname": a.hostname,
        "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        "mac_address": a.mac_address,
        "last_seen": a.last_seen,
        "days_stale": days_stale,
    }


@ro_router.get("/stale", response_model=list[StaleAddress])
def list_stale(
    subnet_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator),
):
    if settings.stale_reclaim_days == 0:
        return []

    rows = _stale_query(db, subnet_id).offset(offset).limit(limit).all()

    subnet_cache: dict[int, str] = {}
    result = []
    for a in rows:
        if a.subnet_id not in subnet_cache:
            s = db.get(Subnet, a.subnet_id)
            subnet_cache[a.subnet_id] = s.cidr if s else ""
        result.append(_to_stale_address(a, subnet_cache[a.subnet_id]))
    return result


@ro_router.get("/stale/count")
def count_stale(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if settings.stale_reclaim_days == 0:
        return {"count": 0}
    return {"count": _stale_query(db).count()}


@router.put("/{address_id}/reclaim")
def reclaim_address(
    address_id: int,
    body: ReclaimAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")

    now = _now()
    before = {
        "status": address.status.value if hasattr(address.status, "value") else str(address.status),
        "reclaim_dismissed_until": str(address.reclaim_dismissed_until) if address.reclaim_dismissed_until else None,
    }

    if body.action == "deprecate":
        address.status = AddressStatus.deprecated
        summary = f"reclaim:deprecate {address.address}"
    elif body.action == "extend":
        address.reclaim_dismissed_until = now + timedelta(days=90)
        summary = f"reclaim:extend {address.address} +90d"
    else:  # dismiss
        address.reclaim_dismissed_until = datetime(9999, 12, 31)
        summary = f"reclaim:dismiss {address.address} permanent"

    after = {
        "status": address.status.value if hasattr(address.status, "value") else str(address.status),
        "reclaim_dismissed_until": str(address.reclaim_dismissed_until) if address.reclaim_dismissed_until else None,
    }

    write_audit(db, current_user.username, "update", "address", str(address.id),
                summary, before=before, after=after)
    db.commit()
    db.refresh(address)

    subnet = db.get(Subnet, address.subnet_id)
    return _to_stale_address(address, subnet.cidr if subnet else "")


@router.post("/stale/bulk-deprecate")
def bulk_deprecate(
    body: BulkDeprecateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if settings.stale_reclaim_days == 0:
        return {"deprecated": 0}

    rows = _stale_query(db, subnet_id=body.subnet_id).all()
    count = 0
    for a in rows:
        before_status = a.status.value if hasattr(a.status, "value") else str(a.status)
        a.status = AddressStatus.deprecated
        write_audit(db, current_user.username, "update", "address", str(a.id),
                    f"reclaim:bulk-deprecate {a.address}",
                    before={"status": before_status},
                    after={"status": "deprecated"})
        count += 1
    db.commit()
    return {"deprecated": count}
