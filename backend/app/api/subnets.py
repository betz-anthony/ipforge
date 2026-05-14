import ipaddress
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.user import User
from app.schemas.subnet import SubnetCreate, SubnetRead, SubnetUpdate, SubnetWithStats
from app.core.deps import require_operator
from app.core.audit import write_audit

router = APIRouter()

_USED_STATUSES = [AddressStatus.assigned, AddressStatus.reserved, AddressStatus.discovered]


def _subnet_state(s: Subnet) -> dict:
    return {
        "id": s.id, "name": s.name, "cidr": s.cidr,
        "ip_version": s.ip_version, "vlan_id": s.vlan_id,
        "description": s.description, "notes": s.notes,
        "created_at": str(s.created_at) if s.created_at else None,
    }


@router.get("", response_model=list[SubnetWithStats])
def list_subnets(
    ip_version: int | None = Query(None, description="Filter by IP version (4 or 6)"),
    db: Session = Depends(get_db),
):
    q = db.query(Subnet)
    if ip_version is not None:
        q = q.filter(Subnet.ip_version == ip_version)
    subnets = q.all()

    counts = (
        db.query(IPAddress.subnet_id, func.count(IPAddress.id).label("used"))
        .filter(IPAddress.status.in_(_USED_STATUSES))
        .group_by(IPAddress.subnet_id)
        .all()
    )
    count_map = {row.subnet_id: row.used for row in counts}

    result = []
    for s in subnets:
        used = count_map.get(s.id, 0)
        network = ipaddress.ip_network(s.cidr, strict=False)
        if network.version == 6:
            total = network.num_addresses
        elif network.prefixlen >= 31:
            total = network.num_addresses
        else:
            total = max(1, network.num_addresses - 2)
        pct = min(100.0, round(used / total * 100, 1)) if total > 0 else 0.0
        result.append(SubnetWithStats(
            id=s.id, name=s.name, cidr=s.cidr, ip_version=s.ip_version,
            vlan_id=s.vlan_id, description=s.description, notes=s.notes,
            created_at=s.created_at,
            used_count=used, total_count=total, utilization_pct=pct,
        ))
    return result


@router.post("", response_model=SubnetRead, status_code=201)
def create_subnet(
    data: SubnetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    try:
        network = ipaddress.ip_network(data.cidr, strict=False)
    except ValueError:
        raise HTTPException(400, "Invalid CIDR notation")
    if db.query(Subnet).filter(Subnet.cidr == data.cidr).first():
        raise HTTPException(409, "Subnet already exists")
    subnet_data = data.model_dump(exclude={'ip_version'})
    subnet = Subnet(**subnet_data, ip_version=network.version)
    db.add(subnet)
    db.flush()
    write_audit(db, current_user.username, "create", "subnet", str(subnet.id),
                f"{subnet.cidr} ({subnet.name})", after=_subnet_state(subnet))
    db.commit()
    db.refresh(subnet)
    return subnet


@router.get("/{subnet_id}", response_model=SubnetRead)
def get_subnet(subnet_id: int, db: Session = Depends(get_db)):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    return subnet


@router.put("/{subnet_id}", response_model=SubnetRead)
def update_subnet(
    subnet_id: int,
    data: SubnetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    before = _subnet_state(subnet)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(subnet, key, value)
    db.flush()
    write_audit(db, current_user.username, "update", "subnet", str(subnet.id),
                f"{subnet.cidr} ({subnet.name})", before=before, after=_subnet_state(subnet))
    db.commit()
    db.refresh(subnet)
    return subnet


@router.delete("/{subnet_id}", status_code=204)
def delete_subnet(
    subnet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    write_audit(db, current_user.username, "delete", "subnet", str(subnet.id),
                f"{subnet.cidr} ({subnet.name})", before=_subnet_state(subnet))
    db.delete(subnet)
    db.commit()
