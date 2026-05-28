"""GITOPS-001 — declarative reconciliation engine (one-way: doc -> IPForge).

Parse a YAML document of desired state (vlans / subnets / reserved_ranges /
allocations), diff it against the DB (plan), and reconcile (apply). Resources the
engine creates are tagged in `gitops_managed` with the doc's `source`, so prune
only removes rows this source created — manual and provider-synced rows are never
touched. Providers (DNS/DHCP) are only written via the allocate path, never pruned.
"""
import ipaddress
import logging

import yaml

from app.models.address import IPAddress, AddressStatus
from app.models.gitops import GitopsManaged
from app.models.subnet import Subnet
from app.models.subnet_range import SubnetRange
from app.models.vlan import Vlan

logger = logging.getLogger(__name__)

_RANGE_KINDS = {"gateway", "dhcp_pool", "static", "reserved"}


class GitopsError(Exception):
    pass


# ── parse / validate ─────────────────────────────────────────────────────────

def parse(text: str) -> dict:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise GitopsError(f"Invalid YAML: {e}")
    if not isinstance(doc, dict):
        raise GitopsError("Document must be a mapping")
    if not doc.get("source") or not isinstance(doc["source"], str):
        raise GitopsError("'source' (string) is required")

    doc.setdefault("vlans", [])
    doc.setdefault("subnets", [])
    doc.setdefault("allocations", [])

    for v in doc["vlans"]:
        vid = v.get("vlan_id")
        if not isinstance(vid, int) or not (1 <= vid <= 4094):
            raise GitopsError(f"vlan_id must be 1–4094: {vid!r}")
        if not v.get("name"):
            raise GitopsError(f"vlan {vid} requires a name")

    for s in doc["subnets"]:
        try:
            ipaddress.ip_network(s["cidr"], strict=False)
        except (KeyError, ValueError):
            raise GitopsError(f"Invalid subnet cidr: {s.get('cidr')!r}")
        if not s.get("name"):
            raise GitopsError(f"subnet {s['cidr']} requires a name")
        for r in s.get("reserved_ranges", []):
            if not r.get("start"):
                raise GitopsError(f"reserved range in {s['cidr']} requires start")
            if r.get("kind") not in _RANGE_KINDS:
                raise GitopsError(f"reserved range kind must be one of {sorted(_RANGE_KINDS)}")

    for a in doc["allocations"]:
        if not a.get("subnet") or not a.get("hostname"):
            raise GitopsError("each allocation requires subnet and hostname")

    return doc


# ── managed-marker helpers ───────────────────────────────────────────────────

def _mark(db, source: str, rtype: str, rid: int) -> None:
    m = db.query(GitopsManaged).filter_by(resource_type=rtype, resource_id=rid).first()
    if m:
        m.source = source
    else:
        db.add(GitopsManaged(source=source, resource_type=rtype, resource_id=rid))


def _managed(db, source: str, rtype: str) -> list[GitopsManaged]:
    return db.query(GitopsManaged).filter_by(source=source, resource_type=rtype).all()


def _unmark(db, rtype: str, rid: int) -> None:
    db.query(GitopsManaged).filter_by(resource_type=rtype, resource_id=rid).delete(synchronize_session=False)


# ── range normalization ──────────────────────────────────────────────────────

def _norm_range(r: dict) -> tuple[str, str, str, str | None]:
    start = r["start"]
    return start, r.get("end") or start, r["kind"], r.get("label")


# ── plan ─────────────────────────────────────────────────────────────────────

def _empty():
    return {"create": [], "update": [], "prune": []}


def plan(doc: dict, db) -> dict:
    source = doc["source"]
    out = {"vlans": _empty(), "subnets": _empty(), "reserved_ranges": _empty(), "allocations": _empty()}

    # vlans
    desired_vlans = {v["vlan_id"]: v for v in doc["vlans"]}
    vlan_rows = {v.vlan_id: v for v in db.query(Vlan).all()}
    for vid, spec in desired_vlans.items():
        row = vlan_rows.get(vid)
        if row is None:
            out["vlans"]["create"].append(str(vid))
        elif row.name != spec["name"] or (row.description or "") != (spec.get("description") or ""):
            out["vlans"]["update"].append(str(vid))
    for m in _managed(db, source, "vlan"):
        row = db.get(Vlan, m.resource_id)
        if row is None or row.vlan_id not in desired_vlans:
            out["vlans"]["prune"].append(str(row.vlan_id) if row else f"#{m.resource_id}")

    # subnets
    desired_subnets = {s["cidr"]: s for s in doc["subnets"]}
    subnet_rows = {s.cidr: s for s in db.query(Subnet).all()}
    for cidr, spec in desired_subnets.items():
        row = subnet_rows.get(cidr)
        if row is None:
            out["subnets"]["create"].append(cidr)
        elif _subnet_differs(row, spec, subnet_rows):
            out["subnets"]["update"].append(cidr)
    for m in _managed(db, source, "subnet"):
        row = db.get(Subnet, m.resource_id)
        if row is None or row.cidr not in desired_subnets:
            out["subnets"]["prune"].append(row.cidr if row else f"#{m.resource_id}")

    # reserved ranges (across subnets present in the doc)
    desired_ranges: set[tuple[str, str, str]] = set()
    for s in doc["subnets"]:
        row = subnet_rows.get(s["cidr"])
        for r in s.get("reserved_ranges", []):
            start, end, kind, _ = _norm_range(r)
            ident = f"{s['cidr']} {start}-{end} {kind}"
            existing = None
            if row is not None:
                existing = db.query(SubnetRange).filter_by(subnet_id=row.id, start_ip=start, end_ip=end).first()
            if existing is None:
                out["reserved_ranges"]["create"].append(ident)
            desired_ranges.add((s["cidr"], start, end))
    for m in _managed(db, source, "subnet_range"):
        rng = db.get(SubnetRange, m.resource_id)
        if rng is None:
            out["reserved_ranges"]["prune"].append(f"#{m.resource_id}")
            continue
        sub = db.get(Subnet, rng.subnet_id)
        key = (sub.cidr if sub else "?", rng.start_ip, rng.end_ip)
        if key not in desired_ranges:
            out["reserved_ranges"]["prune"].append(f"{key[0]} {rng.start_ip}-{rng.end_ip} {rng.kind}")

    # allocations
    desired_allocs: set[tuple[str, str]] = set()
    for a in doc["allocations"]:
        cidr, host = a["subnet"], a["hostname"]
        desired_allocs.add((cidr, host.lower()))
        row = subnet_rows.get(cidr)
        existing = None
        if row is not None:
            existing = (
                db.query(IPAddress)
                .filter(IPAddress.subnet_id == row.id, IPAddress.hostname.ilike(host))
                .first()
            )
        if existing is None:
            out["allocations"]["create"].append(f"{cidr}/{host}")
    for m in _managed(db, source, "address"):
        addr = db.get(IPAddress, m.resource_id)
        if addr is None:
            out["allocations"]["prune"].append(f"#{m.resource_id}")
            continue
        sub = db.get(Subnet, addr.subnet_id)
        key = (sub.cidr if sub else "?", (addr.hostname or "").lower())
        if key not in desired_allocs:
            out["allocations"]["prune"].append(f"{key[0]}/{addr.hostname}")

    return out


def _subnet_differs(row: Subnet, spec: dict, subnet_rows: dict) -> bool:
    if "name" in spec and row.name != spec["name"]:
        return True
    if "vlan_id" in spec and row.vlan_id != spec["vlan_id"]:
        return True
    if "description" in spec and (row.description or "") != (spec.get("description") or ""):
        return True
    if "dns_provider_name" in spec and (row.dns_provider_name or "") != (spec.get("dns_provider_name") or ""):
        return True
    if "dhcp_provider_name" in spec and (row.dhcp_provider_name or "") != (spec.get("dhcp_provider_name") or ""):
        return True
    if "parent" in spec:
        parent = subnet_rows.get(spec["parent"])
        if (parent.id if parent else None) != row.parent_id:
            return True
    return False


# ── apply ────────────────────────────────────────────────────────────────────

def apply(doc: dict, db, current_user) -> dict:
    source = doc["source"]
    applied = {"vlans": 0, "subnets": 0, "reserved_ranges": 0, "allocations": 0}
    pruned = {"vlans": 0, "subnets": 0, "reserved_ranges": 0, "allocations": 0}
    errors: list[str] = []

    # 1. vlans
    desired_vlans = {v["vlan_id"]: v for v in doc["vlans"]}
    for vid, spec in desired_vlans.items():
        row = db.query(Vlan).filter_by(vlan_id=vid).first()
        if row is None:
            row = Vlan(vlan_id=vid, name=spec["name"], description=spec.get("description"))
            db.add(row)
            db.flush()
        else:
            row.name = spec["name"]
            if "description" in spec:
                row.description = spec.get("description")
        _mark(db, source, "vlan", row.id)
        applied["vlans"] += 1

    # 2. subnets — parents before children
    desired_subnets = sorted(doc["subnets"], key=lambda s: ipaddress.ip_network(s["cidr"], strict=False).prefixlen)
    for spec in desired_subnets:
        cidr = spec["cidr"]
        net = ipaddress.ip_network(cidr, strict=False)
        parent_id = None
        if spec.get("parent"):
            p = db.query(Subnet).filter_by(cidr=spec["parent"]).first()
            parent_id = p.id if p else None
        row = db.query(Subnet).filter_by(cidr=cidr).first()
        if row is None:
            row = Subnet(name=spec["name"], cidr=cidr, ip_version=net.version,
                         vlan_id=spec.get("vlan_id"), description=spec.get("description"),
                         parent_id=parent_id, dns_provider_name=spec.get("dns_provider_name"),
                         dhcp_provider_name=spec.get("dhcp_provider_name"))
            db.add(row)
            db.flush()
        else:
            row.name = spec["name"]
            if "vlan_id" in spec:
                row.vlan_id = spec.get("vlan_id")
            if "description" in spec:
                row.description = spec.get("description")
            if spec.get("parent"):
                row.parent_id = parent_id
            if "dns_provider_name" in spec:
                row.dns_provider_name = spec.get("dns_provider_name")
            if "dhcp_provider_name" in spec:
                row.dhcp_provider_name = spec.get("dhcp_provider_name")
        _mark(db, source, "subnet", row.id)
        applied["subnets"] += 1

        # 3. reserved ranges for this subnet
        for r in spec.get("reserved_ranges", []):
            start, end, kind, label = _norm_range(r)
            rng = db.query(SubnetRange).filter_by(subnet_id=row.id, start_ip=start, end_ip=end).first()
            if rng is None:
                rng = SubnetRange(subnet_id=row.id, start_ip=start, end_ip=end, kind=kind, label=label)
                db.add(rng)
                db.flush()
            else:
                rng.kind = kind
                rng.label = label
            _mark(db, source, "subnet_range", rng.id)
            applied["reserved_ranges"] += 1
    db.commit()

    # 4. allocations (via the existing allocator; honors register_dns/dhcp)
    from app.api.allocation import AllocateRequest, _do_allocate, _BYPASS_ACCESS
    for a in doc["allocations"]:
        sub = db.query(Subnet).filter_by(cidr=a["subnet"]).first()
        if sub is None:
            errors.append(f"allocation {a['hostname']}: subnet {a['subnet']} not found")
            continue
        try:
            req = AllocateRequest(
                hostname=a["hostname"], mac_address=a.get("mac_address"),
                register_dns=a.get("register_dns", False), register_dhcp=a.get("register_dhcp", False),
                dns_zone=a.get("dns_zone"), dns_provider=a.get("dns_provider"),
                dhcp_provider=a.get("dhcp_provider"),
            )
            result = _do_allocate(db, sub.id, req, current_user, access=_BYPASS_ACCESS)
            _mark(db, source, "address", result["id"])
            applied["allocations"] += 1
        except Exception as exc:
            db.rollback()
            errors.append(f"allocation {a['hostname']}: {exc}")
    db.commit()

    # 5. prune managed-of-source rows absent from the doc (allocations, ranges,
    #    then subnets, then vlans)
    p = plan(doc, db)

    desired_alloc = {(a["subnet"], a["hostname"].lower()) for a in doc["allocations"]}
    for m in _managed(db, source, "address"):
        addr = db.get(IPAddress, m.resource_id)
        keep = False
        if addr is not None:
            sub = db.get(Subnet, addr.subnet_id)
            keep = sub is not None and (sub.cidr, (addr.hostname or "").lower()) in desired_alloc
        if not keep:
            if addr is not None:
                db.delete(addr)
            _unmark(db, "address", m.resource_id)
            pruned["allocations"] += 1

    desired_ranges = set()
    for s in doc["subnets"]:
        for r in s.get("reserved_ranges", []):
            start, end, _, _ = _norm_range(r)
            desired_ranges.add((s["cidr"], start, end))
    for m in _managed(db, source, "subnet_range"):
        rng = db.get(SubnetRange, m.resource_id)
        keep = False
        if rng is not None:
            sub = db.get(Subnet, rng.subnet_id)
            keep = sub is not None and (sub.cidr, rng.start_ip, rng.end_ip) in desired_ranges
        if not keep:
            if rng is not None:
                db.delete(rng)
            _unmark(db, "subnet_range", m.resource_id)
            pruned["reserved_ranges"] += 1

    desired_cidrs = {s["cidr"] for s in doc["subnets"]}
    for m in _managed(db, source, "subnet"):
        row = db.get(Subnet, m.resource_id)
        if row is None or row.cidr not in desired_cidrs:
            if row is not None:
                try:
                    db.delete(row)
                    db.flush()
                except Exception as exc:
                    db.rollback()
                    errors.append(f"prune subnet {row.cidr}: {exc}")
                    continue
            _unmark(db, "subnet", m.resource_id)
            pruned["subnets"] += 1

    desired_vids = {v["vlan_id"] for v in doc["vlans"]}
    for m in _managed(db, source, "vlan"):
        row = db.get(Vlan, m.resource_id)
        if row is None or row.vlan_id not in desired_vids:
            if row is not None:
                db.delete(row)
            _unmark(db, "vlan", m.resource_id)
            pruned["vlans"] += 1

    db.commit()
    return {"plan": p, "applied": applied, "pruned": pruned, "errors": errors}
