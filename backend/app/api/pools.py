"""ALLOC-POOLS-001 — named allocation pools within a subnet."""
import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.allocation import _INELIGIBLE
from app.api.subnets import reserved_ip_set
from app.core.access import AccessContext, get_access_context
from app.core.audit import write_audit
from app.core.deps import get_current_user
from app.core.ip_sort import ip_sort_key
from app.core.pools import normalize_pool_name, pool_bounds
from app.database import get_db
from app.models.address import IPAddress
from app.models.subnet import Subnet
from app.models.subnet_pool import SubnetPool
from app.models.user import User

router = APIRouter()


class PoolIn(BaseModel):
    name: str
    start_ip: str
    end_ip: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return normalize_pool_name(v)


def _pool_out(db: Session, subnet: Subnet, p: SubnetPool) -> dict:
    lo, hi = pool_bounds(p)
    version = ipaddress.ip_address(p.start_ip).version
    to_ip = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address

    # Count by address range, not subnet_id: with nested subnets an in-use IP
    # inside the window may be recorded under a parent subnet.
    used_set = {
        row.address
        for row in db.query(IPAddress.address).filter(
            IPAddress.ip_sort_key >= ip_sort_key(p.start_ip),
            IPAddress.ip_sort_key <= ip_sort_key(p.end_ip),
            IPAddress.status.in_(_INELIGIBLE),
        )
    }
    reserved = {
        ip for ip in reserved_ip_set(db, subnet.id)
        if lo <= int(ipaddress.ip_address(ip)) <= hi
    } - used_set
    total = hi - lo + 1
    used = len(used_set)
    return {
        "id": p.id, "subnet_id": p.subnet_id, "name": p.name,
        "start_ip": p.start_ip, "end_ip": p.end_ip, "description": p.description,
        "total": total, "used": used, "reserved": len(reserved),
        "free": max(0, total - used - len(reserved)),
    }


def _validate_window(subnet: Subnet, body: PoolIn) -> None:
    network = ipaddress.ip_network(subnet.cidr, strict=False)
    try:
        start = ipaddress.ip_address(body.start_ip)
        end = ipaddress.ip_address(body.end_ip)
    except ValueError:
        raise HTTPException(422, "Invalid IP address")
    if start.version != network.version or end.version != network.version:
        raise HTTPException(422, "Pool IP version does not match subnet")
    if start not in network or end not in network:
        raise HTTPException(422, "Pool must be inside the subnet CIDR")
    if int(start) > int(end):
        raise HTTPException(422, "start_ip must be <= end_ip")


def _check_conflicts(db: Session, subnet_id: int, body: PoolIn, exclude_id: int | None) -> None:
    start, end = int(ipaddress.ip_address(body.start_ip)), int(ipaddress.ip_address(body.end_ip))
    for other in db.query(SubnetPool).filter_by(subnet_id=subnet_id).all():
        if other.id == exclude_id:
            continue
        if other.name == body.name:
            raise HTTPException(409, f'Pool name "{body.name}" already exists in this subnet')
        os_, oe = pool_bounds(other)
        if start <= oe and os_ <= end:
            raise HTTPException(409, f'Pool overlaps existing pool "{other.name}" ({other.start_ip}–{other.end_ip})')


def _subnet_or_404(db: Session, subnet_id: int) -> Subnet:
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    return subnet


@router.get("/{subnet_id}/pools")
def list_pools(
    subnet_id: int,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    subnet = _subnet_or_404(db, subnet_id)
    access.require_read(subnet_id)
    rows = db.query(SubnetPool).filter_by(subnet_id=subnet_id).all()
    rows.sort(key=lambda p: ip_sort_key(p.start_ip) or b"")
    return [_pool_out(db, subnet, p) for p in rows]


@router.post("/{subnet_id}/pools", status_code=201)
def create_pool(
    subnet_id: int,
    body: PoolIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    subnet = _subnet_or_404(db, subnet_id)
    access.require_write(subnet_id)
    _validate_window(subnet, body)
    _check_conflicts(db, subnet_id, body, exclude_id=None)
    row = SubnetPool(subnet_id=subnet_id, name=body.name, start_ip=body.start_ip,
                     end_ip=body.end_ip, description=body.description)
    db.add(row)
    db.flush()
    write_audit(db, current_user.username, "create", "subnet_pool", str(row.id),
                f"{subnet.cidr} {body.name} {body.start_ip}-{body.end_ip}")
    db.commit()
    db.refresh(row)
    return _pool_out(db, subnet, row)


@router.put("/{subnet_id}/pools/{pool_id}")
def update_pool(
    subnet_id: int,
    pool_id: int,
    body: PoolIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    subnet = _subnet_or_404(db, subnet_id)
    access.require_write(subnet_id)
    row = db.query(SubnetPool).filter_by(id=pool_id, subnet_id=subnet_id).first()
    if row is None:
        raise HTTPException(404, "Pool not found")
    _validate_window(subnet, body)
    _check_conflicts(db, subnet_id, body, exclude_id=row.id)
    row.name, row.start_ip, row.end_ip, row.description = (
        body.name, body.start_ip, body.end_ip, body.description)
    write_audit(db, current_user.username, "update", "subnet_pool", str(row.id),
                f"{subnet.cidr} {body.name} {body.start_ip}-{body.end_ip}")
    db.commit()
    db.refresh(row)
    return _pool_out(db, subnet, row)


@router.delete("/{subnet_id}/pools/{pool_id}", status_code=204)
def delete_pool(
    subnet_id: int,
    pool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    subnet = _subnet_or_404(db, subnet_id)
    access.require_write(subnet_id)
    row = db.query(SubnetPool).filter_by(id=pool_id, subnet_id=subnet_id).first()
    if row is None:
        raise HTTPException(404, "Pool not found")
    write_audit(db, current_user.username, "delete", "subnet_pool", str(row.id),
                f"{subnet.cidr} {row.name} {row.start_ip}-{row.end_ip}")
    db.delete(row)
    db.commit()
    return Response(status_code=204)
