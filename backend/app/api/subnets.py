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
        "parent_id": s.parent_id,
        "created_at": str(s.created_at) if s.created_at else None,
    }


def _build_stats_rows(subnets: list[Subnet], db: Session) -> list[dict]:
    """Build per-subnet own stats as a list of dicts (no rollup yet)."""
    if not subnets:
        return []
    ids = [s.id for s in subnets]
    counts = (
        db.query(IPAddress.subnet_id, func.count(IPAddress.id).label("used"))
        .filter(IPAddress.status.in_(_USED_STATUSES))
        .filter(IPAddress.subnet_id.in_(ids))
        .group_by(IPAddress.subnet_id)
        .all()
    )
    count_map = {row.subnet_id: row.used for row in counts}
    rows = []
    for s in subnets:
        used = count_map.get(s.id, 0)
        net = ipaddress.ip_network(s.cidr, strict=False)
        if net.version == 6:
            total = net.num_addresses
        elif net.prefixlen >= 31:
            total = net.num_addresses
        else:
            total = max(1, net.num_addresses - 2)
        pct = min(100.0, round(used / total * 100, 1)) if total > 0 else 0.0
        rows.append({
            "id": s.id, "name": s.name, "cidr": s.cidr,
            "ip_version": s.ip_version, "vlan_id": s.vlan_id,
            "description": s.description, "notes": s.notes,
            "created_at": s.created_at, "parent_id": s.parent_id,
            "used_count": used, "total_count": total, "utilization_pct": pct,
            "rollup_used_count": used, "rollup_total_count": total,
            "rollup_utilization_pct": pct,
        })
    return rows


def _compute_rollup(rows: list[dict]) -> None:
    """Post-order DFS rollup. Modifies rollup_* fields in-place."""
    children_map: dict[int | None, list[dict]] = {}
    for r in rows:
        children_map.setdefault(r["parent_id"], []).append(r)

    def dfs(r: dict) -> None:
        children = children_map.get(r["id"], [])
        for c in children:
            dfs(c)
        rollup_used  = r["used_count"]  + sum(c["rollup_used_count"]  for c in children)
        rollup_total = r["total_count"] + sum(c["rollup_total_count"] for c in children)
        r["rollup_used_count"]  = rollup_used
        r["rollup_total_count"] = rollup_total
        r["rollup_utilization_pct"] = (
            min(100.0, round(rollup_used / rollup_total * 100, 1))
            if rollup_total > 0 else 0.0
        )

    for root in children_map.get(None, []):
        dfs(root)


def _is_ancestor(db: Session, potential_ancestor_id: int, node_id: int) -> bool:
    """True if potential_ancestor_id is an ancestor of node_id (or equal)."""
    visited: set[int] = set()
    current_id: int | None = node_id
    while current_id is not None:
        if current_id in visited:
            break
        visited.add(current_id)
        if current_id == potential_ancestor_id:
            return True
        node = db.get(Subnet, current_id)
        if node is None:
            break
        current_id = node.parent_id
    return False


@router.get("", response_model=list[SubnetWithStats])
def list_subnets(
    ip_version: int | None = Query(None, description="Filter by IP version (4 or 6)"),
    db: Session = Depends(get_db),
):
    q = db.query(Subnet)
    if ip_version is not None:
        q = q.filter(Subnet.ip_version == ip_version)
    subnets = q.all()
    rows = _build_stats_rows(subnets, db)
    _compute_rollup(rows)
    return [SubnetWithStats(**r) for r in rows]


@router.get("/suggest-parent", response_model=list[SubnetWithStats])
def suggest_parent(
    cidr: str = Query(..., description="CIDR of the subnet being created/edited"),
    db: Session = Depends(get_db),
):
    try:
        target = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return []
    subnets = db.query(Subnet).all()
    parsed_subnets = [(s, ipaddress.ip_network(s.cidr, strict=False)) for s in subnets]
    candidates_with_net = [
        (s, net) for s, net in parsed_subnets
        if s.cidr != cidr and net.version == target.version and net.supernet_of(target)
    ]
    candidates_with_net.sort(key=lambda pair: pair[1].prefixlen, reverse=True)
    candidates = [s for s, _ in candidates_with_net]
    rows = _build_stats_rows(candidates, db)
    return [SubnetWithStats(**r) for r in rows]


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
    if data.parent_id is not None:
        parent = db.get(Subnet, data.parent_id)
        if parent is None:
            raise HTTPException(404, "Parent subnet not found")
        parent_network = ipaddress.ip_network(parent.cidr, strict=False)
        if parent_network.version != network.version:
            raise HTTPException(422, "Parent and subnet must be the same IP version")
        if not parent_network.supernet_of(network):
            raise HTTPException(422, "Parent's CIDR does not contain this subnet's CIDR")
    subnet = Subnet(
        name=data.name, cidr=data.cidr, ip_version=network.version,
        vlan_id=data.vlan_id, description=data.description,
        notes=data.notes, parent_id=data.parent_id,
    )
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
        if key == "parent_id":
            continue  # handled separately below
        setattr(subnet, key, value)
    if "parent_id" in data.model_fields_set:
        new_parent_id = data.parent_id
        if new_parent_id is not None:
            if new_parent_id == subnet_id:
                raise HTTPException(422, "A subnet cannot be its own parent")
            parent = db.get(Subnet, new_parent_id)
            if parent is None:
                raise HTTPException(404, "Parent subnet not found")
            parent_network = ipaddress.ip_network(parent.cidr, strict=False)
            subnet_network = ipaddress.ip_network(subnet.cidr, strict=False)
            if parent_network.version != subnet_network.version:
                raise HTTPException(422, "Parent and subnet must be the same IP version")
            if not parent_network.supernet_of(subnet_network):
                raise HTTPException(422, "Parent's CIDR does not contain this subnet's CIDR")
            if _is_ancestor(db, subnet_id, new_parent_id):
                raise HTTPException(422, "Cycle detected: new parent is a descendant of this subnet")
        subnet.parent_id = new_parent_id
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
    if db.query(Subnet).filter(Subnet.parent_id == subnet_id).first():
        raise HTTPException(409, "Cannot delete subnet with children")
    write_audit(db, current_user.username, "delete", "subnet", str(subnet.id),
                f"{subnet.cidr} ({subnet.name})", before=_subnet_state(subnet))
    db.delete(subnet)
    db.commit()
