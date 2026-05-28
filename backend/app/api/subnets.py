import ipaddress
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.subnet import Subnet
from app.models.subnet_range import SubnetRange
from app.models.address import IPAddress, AddressStatus
from app.models.scan import DriftItem
from app.models.user import User
from app.schemas.subnet import SubnetCreate, SubnetRead, SubnetUpdate, SubnetWithStats, SubnetForecast
from app.core.deps import get_current_user
from app.core.audit import write_audit
from app.core.access import AccessContext, get_access_context
from app.core.forecast import compute_forecast
from app.config import settings
from app.models.scan import SubnetUtilizationDay
from app.scan import subnet_total_count
from app.core.custom_fields import (
    load_custom_fields, load_tags, load_custom_fields_bulk, load_tags_bulk,
    set_custom_fields, set_tags, filter_entity_ids,
)


def _cf_filters(request: Request) -> dict[str, str]:
    return {k[3:]: v for k, v in request.query_params.items() if k.startswith("cf_")}

router = APIRouter()

_USED_STATUSES = [AddressStatus.assigned, AddressStatus.reserved, AddressStatus.discovered]


def _subnet_state(s: Subnet) -> dict:
    return {
        "id": s.id, "name": s.name, "cidr": s.cidr,
        "ip_version": s.ip_version, "vlan_id": s.vlan_id,
        "description": s.description, "notes": s.notes,
        "parent_id": s.parent_id,
        "created_at": str(s.created_at) if s.created_at else None,
        "dns_provider_name": s.dns_provider_name,
        "dhcp_provider_name": s.dhcp_provider_name,
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

    used_addr_rows = (
        db.query(IPAddress.subnet_id, IPAddress.address)
        .filter(IPAddress.status.in_(_USED_STATUSES))
        .filter(IPAddress.subnet_id.in_(ids))
        .all()
    )
    used_addrs: dict[int, set[str]] = {}
    for sid, addr in used_addr_rows:
        used_addrs.setdefault(sid, set()).add(addr)

    range_rows = db.query(SubnetRange).filter(SubnetRange.subnet_id.in_(ids)).all()
    ranges_by_subnet: dict[int, list[SubnetRange]] = {}
    for r in range_rows:
        ranges_by_subnet.setdefault(r.subnet_id, []).append(r)

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

        reserved_count = 0
        srs = ranges_by_subnet.get(s.id)
        if srs:
            usable_excludes = set()
            if net.version == 4 and net.prefixlen < 31:
                usable_excludes = {str(net.network_address), str(net.broadcast_address)}
            used_set = used_addrs.get(s.id, set())
            reserved_ips: set[str] = set()
            for r in srs:
                a, b = int(ipaddress.ip_address(r.start_ip)), int(ipaddress.ip_address(r.end_ip))
                for n in range(a, b + 1):
                    reserved_ips.add(str(ipaddress.ip_address(n)))
            reserved_ips -= usable_excludes
            reserved_ips -= used_set
            reserved_count = len(reserved_ips)

        pct = min(100.0, round(used / total * 100, 1)) if total > 0 else 0.0
        rows.append({
            "id": s.id, "name": s.name, "cidr": s.cidr,
            "ip_version": s.ip_version, "vlan_id": s.vlan_id,
            "description": s.description, "notes": s.notes,
            "created_at": s.created_at, "parent_id": s.parent_id,
            "scan_interval_minutes": s.scan_interval_minutes,
            "dns_provider_name": s.dns_provider_name,
            "dhcp_provider_name": s.dhcp_provider_name,
            "request_eligible": s.request_eligible,
            "used_count": used, "total_count": total, "utilization_pct": pct,
            "reserved_count": reserved_count,
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
    request: Request,
    ip_version: int | None = Query(None, description="Filter by IP version (4 or 6)"),
    tag: str | None = Query(None, description="Filter by tag name"),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    q = db.query(Subnet)
    if ip_version is not None:
        q = q.filter(Subnet.ip_version == ip_version)
    subnets = q.all()
    if not access.global_read:
        subnets = [s for s in subnets if s.id in access.viewable]
    match = filter_entity_ids(db, "subnet", tag=tag, cf_filters=_cf_filters(request))
    if match is not None:
        subnets = [s for s in subnets if s.id in match]
    rows = _build_stats_rows(subnets, db)
    _compute_rollup(rows)
    ids = [r["id"] for r in rows]
    cf = load_custom_fields_bulk(db, "subnet", ids)
    tg = load_tags_bulk(db, "subnet", ids)
    for r in rows:
        r["custom_fields"] = cf.get(r["id"], {})
        r["tags"] = tg.get(r["id"], [])
    return [SubnetWithStats(**r) for r in rows]


@router.get("/suggest-parent", response_model=list[SubnetWithStats])
def suggest_parent(
    cidr: str = Query(..., description="CIDR of the subnet being created/edited"),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
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
    if not access.global_read:
        candidates = [s for s in candidates if s.id in access.viewable]
    rows = _build_stats_rows(candidates, db)
    return [SubnetWithStats(**r) for r in rows]


def _forecast_dict(db: Session, subnet: Subnet) -> dict:
    rows = (
        db.query(SubnetUtilizationDay.date, SubnetUtilizationDay.used_count)
        .filter(SubnetUtilizationDay.subnet_id == subnet.id)
        .order_by(SubnetUtilizationDay.date)
        .all()
    )
    snapshots = [(r.date, r.used_count) for r in rows]
    f = compute_forecast(
        snapshots,
        total_count=subnet_total_count(subnet.cidr),
        warn_pct=settings.util_warn_threshold,
        critical_pct=settings.util_critical_threshold,
    )
    f.update({"subnet_id": subnet.id, "cidr": subnet.cidr, "name": subnet.name})
    return f


@router.get("/forecasts", response_model=list[SubnetForecast])
def list_forecasts(
    limit: int = Query(5, ge=1, le=100),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    subnets = db.query(Subnet).all()
    if not access.global_read:
        subnets = [s for s in subnets if s.id in access.viewable]
    forecasts = [_forecast_dict(db, s) for s in subnets]
    projected = [f for f in forecasts if f["days_to_critical"] is not None]
    projected.sort(key=lambda f: f["days_to_critical"])
    return [SubnetForecast(**f) for f in projected[:limit]]


@router.get("/{subnet_id}/forecast", response_model=SubnetForecast)
def get_forecast(
    subnet_id: int,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_read(subnet_id)
    return SubnetForecast(**_forecast_dict(db, subnet))


@router.post("", response_model=SubnetRead, status_code=201)
def create_subnet(
    data: SubnetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    if not access.global_write:
        raise HTTPException(403, "Scoped users cannot create subnets")
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
        scan_interval_minutes=data.scan_interval_minutes,
        dns_provider_name=data.dns_provider_name,
        dhcp_provider_name=data.dhcp_provider_name,
        request_eligible=data.request_eligible,
    )
    db.add(subnet)
    db.flush()
    write_audit(db, current_user.username, "create", "subnet", str(subnet.id),
                f"{subnet.cidr} ({subnet.name})", after=_subnet_state(subnet))
    db.commit()
    db.refresh(subnet)
    return subnet


@router.get("/{subnet_id}", response_model=SubnetRead)
def get_subnet(
    subnet_id: int,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_read(subnet_id)
    subnet.custom_fields = load_custom_fields(db, "subnet", subnet.id)
    subnet.tags = load_tags(db, "subnet", subnet.id)
    return subnet


@router.put("/{subnet_id}", response_model=SubnetRead)
def update_subnet(
    subnet_id: int,
    data: SubnetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_write(subnet_id)
    before = _subnet_state(subnet)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key in ("parent_id", "custom_fields", "tags"):
            continue  # handled separately below
        setattr(subnet, key, value)
    if data.custom_fields is not None:
        set_custom_fields(db, "subnet", subnet.id, data.custom_fields)
    if data.tags is not None:
        set_tags(db, "subnet", subnet.id, data.tags)
    if "parent_id" in data.model_fields_set:
        new_parent_id = data.parent_id
        if new_parent_id is not None:
            if new_parent_id == subnet_id:
                raise HTTPException(422, "A subnet cannot be its own parent")
            parent = db.get(Subnet, new_parent_id)
            if parent is None:
                raise HTTPException(404, "Parent subnet not found")
            access.require_read(new_parent_id)
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
    subnet.custom_fields = load_custom_fields(db, "subnet", subnet.id)
    subnet.tags = load_tags(db, "subnet", subnet.id)
    return subnet


MAP_MAX_HOSTS = 1024


@router.get("/{subnet_id}/map")
def subnet_map(
    subnet_id: int,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_read(subnet_id)

    net = ipaddress.ip_network(subnet.cidr, strict=False)
    if net.version == 4 and net.prefixlen < 31:
        host_count = max(0, net.num_addresses - 2)
    else:
        host_count = net.num_addresses

    if host_count > MAP_MAX_HOSTS:
        return {"too_large": True, "host_count": host_count}

    addr_status = {
        a.address: a.status.value
        for a in db.query(IPAddress).filter(IPAddress.subnet_id == subnet_id).all()
    }
    reserved = reserved_ip_set(db, subnet_id)
    collision_ips = {
        c.ip_address for c in db.query(DriftItem.ip_address).filter(DriftItem.resolved.is_(False)).all()
    }

    cells = []
    for ip in net.hosts():
        s = str(ip)
        if s in addr_status:
            status = addr_status[s]
        elif s in reserved:
            status = "reserved"
        else:
            status = "free"
        cells.append({"ip": s, "status": status, "collision": s in collision_ips})

    return {"too_large": False, "host_count": host_count, "cells": cells}


RangeKind = Literal["gateway", "dhcp_pool", "static", "reserved"]


class RangeIn(BaseModel):
    start_ip: str
    end_ip: str
    kind: RangeKind
    label: str | None = None


def _range_out(r: SubnetRange) -> dict:
    return {
        "id": r.id, "subnet_id": r.subnet_id,
        "start_ip": r.start_ip, "end_ip": r.end_ip,
        "kind": r.kind, "label": r.label,
    }


def reserved_ip_set(db: Session, subnet_id: int) -> set[str]:
    """All host IPs covered by the subnet's reserved ranges."""
    ips: set[str] = set()
    for r in db.query(SubnetRange).filter_by(subnet_id=subnet_id).all():
        start = int(ipaddress.ip_address(r.start_ip))
        end = int(ipaddress.ip_address(r.end_ip))
        for n in range(start, end + 1):
            ips.add(str(ipaddress.ip_address(n)))
    return ips


@router.get("/{subnet_id}/ranges")
def list_ranges(
    subnet_id: int,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_read(subnet_id)
    rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id).order_by(SubnetRange.start_ip).all()
    return [_range_out(r) for r in rows]


@router.post("/{subnet_id}/ranges", status_code=201)
def create_range(
    subnet_id: int,
    body: RangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_write(subnet_id)
    network = ipaddress.ip_network(subnet.cidr, strict=False)
    try:
        start = ipaddress.ip_address(body.start_ip)
        end = ipaddress.ip_address(body.end_ip)
    except ValueError:
        raise HTTPException(422, "Invalid IP address")
    if start.version != network.version or end.version != network.version:
        raise HTTPException(422, "Range IP version does not match subnet")
    if start not in network or end not in network:
        raise HTTPException(422, "Range must be inside the subnet CIDR")
    if int(start) > int(end):
        raise HTTPException(422, "start_ip must be <= end_ip")
    for r in db.query(SubnetRange).filter_by(subnet_id=subnet_id).all():
        es, ee = int(ipaddress.ip_address(r.start_ip)), int(ipaddress.ip_address(r.end_ip))
        if int(start) <= ee and es <= int(end):
            raise HTTPException(409, f"Range overlaps existing range {r.start_ip}–{r.end_ip}")
    row = SubnetRange(
        subnet_id=subnet_id, start_ip=body.start_ip, end_ip=body.end_ip,
        kind=body.kind, label=body.label,
    )
    db.add(row)
    db.flush()
    write_audit(db, current_user.username, "create", "subnet_range", str(row.id),
                f"{subnet.cidr} {body.start_ip}-{body.end_ip} ({body.kind})")
    db.commit()
    db.refresh(row)
    return _range_out(row)


@router.delete("/{subnet_id}/ranges/{range_id}", status_code=204)
def delete_range(
    subnet_id: int,
    range_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_write(subnet_id)
    row = db.query(SubnetRange).filter_by(id=range_id, subnet_id=subnet_id).first()
    if row is None:
        raise HTTPException(404, "Range not found")
    write_audit(db, current_user.username, "delete", "subnet_range", str(row.id),
                f"{subnet.cidr} {row.start_ip}-{row.end_ip} ({row.kind})")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.delete("/{subnet_id}", status_code=204)
def delete_subnet(
    subnet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    access: AccessContext = Depends(get_access_context),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")
    access.require_write(subnet_id)
    if db.query(Subnet).filter(Subnet.parent_id == subnet_id).first():
        raise HTTPException(409, "Cannot delete subnet with children")
    count = db.query(IPAddress).filter(IPAddress.subnet_id == subnet_id).count()
    if count > 0:
        raise HTTPException(409, f"Subnet must be empty before deletion ({count} addresses remain)")
    write_audit(db, current_user.username, "delete", "subnet", str(subnet.id),
                f"{subnet.cidr} ({subnet.name})", before=_subnet_state(subnet))
    db.delete(subnet)
    db.commit()
