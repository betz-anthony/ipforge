from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.scan import ScanHistoryDay
from app.models.user import User
from app.schemas.address import AddressCreate, AddressRead, AddressUpdate
from app.core.deps import require_operator
from app.core.audit import write_audit
from pydantic import BaseModel

router = APIRouter()


class ScanHistoryDayRead(BaseModel):
    date: date
    up_count: int
    total_count: int
    uptime_pct: float
    avg_latency_ms: float | None

    model_config = {"from_attributes": True}


def _address_state(a: IPAddress) -> dict:
    return {
        "id": a.id, "address": a.address, "subnet_id": a.subnet_id,
        "hostname": a.hostname,
        "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        "mac_address": a.mac_address, "description": a.description, "notes": a.notes,
    }


@router.get("", response_model=list[AddressRead])
def list_addresses(
    subnet_id: int | None = Query(None),
    status: AddressStatus | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(IPAddress)
    if subnet_id is not None:
        q = q.filter(IPAddress.subnet_id == subnet_id)
    if status is not None:
        q = q.filter(IPAddress.status == status)
    return q.all()


@router.post("", response_model=AddressRead, status_code=201)
def create_address(
    data: AddressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if db.query(IPAddress).filter(IPAddress.address == data.address).first():
        raise HTTPException(409, "Address already exists")
    address = IPAddress(**data.model_dump())
    db.add(address)
    db.flush()
    write_audit(db, current_user.username, "create", "address", str(address.id),
                address.address, after=_address_state(address))
    db.commit()
    db.refresh(address)
    return address


@router.get("/{address_id}/scan-history", response_model=list[ScanHistoryDayRead])
def get_scan_history(address_id: int, db: Session = Depends(get_db)):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now.date() - timedelta(days=29)
    rows = (
        db.query(ScanHistoryDay)
        .filter_by(ip_address=address.address)
        .filter(ScanHistoryDay.date >= cutoff)
        .order_by(ScanHistoryDay.date.desc())
        .all()
    )
    return rows


@router.get("/by-ip/{address}", response_model=AddressRead)
def get_address_by_ip(address: str, db: Session = Depends(get_db)):
    record = db.query(IPAddress).filter(IPAddress.address == address).first()
    if not record:
        raise HTTPException(404, "Address not found")
    return record


@router.get("/{address_id}", response_model=AddressRead)
def get_address(address_id: int, db: Session = Depends(get_db)):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    return address


@router.put("/{address_id}", response_model=AddressRead)
def update_address(
    address_id: int,
    data: AddressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    before = _address_state(address)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(address, key, value)
    db.flush()
    write_audit(db, current_user.username, "update", "address", str(address.id),
                address.address, before=before, after=_address_state(address))
    db.commit()
    db.refresh(address)
    return address


@router.delete("/{address_id}", status_code=204)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    write_audit(db, current_user.username, "delete", "address", str(address.id),
                address.address, before=_address_state(address))
    db.delete(address)
    db.commit()
