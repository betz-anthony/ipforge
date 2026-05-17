from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDNSRecord, CachedDHCPLease
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


class DeletePreviewItem(BaseModel):
    key: str
    type: str
    provider: str
    zone: str | None = None
    record_type: str | None = None
    name: str | None = None
    value: str | None = None
    scope_id: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None


class DeletePreview(BaseModel):
    address: str
    hostname: str | None
    items: list[DeletePreviewItem]


def _build_preview_items(address: IPAddress, db: Session) -> list[DeletePreviewItem]:
    seen: dict[str, DeletePreviewItem] = {}

    # Stored provider fields
    if address.dns_provider and address.dns_zone:
        key = f"dns-{address.dns_provider}-{address.dns_zone}-{address.hostname or address.address}"
        seen[key] = DeletePreviewItem(
            key=key, type="dns",
            provider=address.dns_provider, zone=address.dns_zone,
            record_type="A", name=address.hostname or "", value=address.address,
        )

    if address.dhcp_provider and address.dhcp_scope_id:
        key = f"dhcp-{address.dhcp_provider}-{address.dhcp_scope_id}-{address.address}"
        seen[key] = DeletePreviewItem(
            key=key, type="dhcp",
            provider=address.dhcp_provider, scope_id=address.dhcp_scope_id,
            ip_address=address.address, mac_address=address.mac_address or "",
        )

    # Cache: DNS A records matching IP or hostname
    dns_filters = [CachedDNSRecord.value == address.address]
    if address.hostname:
        dns_filters.append(CachedDNSRecord.name == address.hostname)
    for r in db.query(CachedDNSRecord).filter(
        CachedDNSRecord.record_type == "A",
        or_(*dns_filters),
    ).all():
        key = f"dns-{r.source}-{r.zone}-{r.name}"
        if key not in seen:
            seen[key] = DeletePreviewItem(
                key=key, type="dns",
                provider=r.source, zone=r.zone,
                record_type=r.record_type, name=r.name, value=r.value,
            )

    # Cache: DHCP leases matching IP
    for l in db.query(CachedDHCPLease).filter(
        CachedDHCPLease.ip_address == address.address
    ).all():
        key = f"dhcp-{l.source}-{l.scope_id}-{l.ip_address}"
        if key not in seen:
            seen[key] = DeletePreviewItem(
                key=key, type="dhcp",
                provider=l.source, scope_id=l.scope_id,
                ip_address=l.ip_address, mac_address=l.mac_address or "",
            )

    return list(seen.values())


@router.get("/{address_id}/delete-preview", response_model=DeletePreview)
def get_delete_preview(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    address = db.get(IPAddress, address_id)
    if not address:
        raise HTTPException(404, "Address not found")
    return DeletePreview(
        address=address.address,
        hostname=address.hostname,
        items=_build_preview_items(address, db),
    )


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
