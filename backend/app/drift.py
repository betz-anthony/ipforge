"""DRIFT-001 — reconciliation / drift detection.

Generalizes the former collision detection into a multi-way diff between IPAM
(intended state) and the DNS/DHCP sync cache + live scan (actual state).
"""
import json
import logging
from datetime import timedelta

from sqlalchemy import func

from app.database import SessionLocal
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord
from app.models.scan import (
    DriftItem, DriftCategory, ScanResult, DRIFT_SEVERITY, _CONFLICT_CATEGORIES,
)
from app.models.subnet import Subnet
from app.core.time import utcnow
from app.core.mac import normalize_mac_optional
from app.utils import ip_in_cidr
from app.alerting.emit import emit

logger = logging.getLogger(__name__)

_USED_STATUSES = (AddressStatus.assigned, AddressStatus.reserved)

# Scans older than this are too stale to flag unreachable_assigned.
_UNREACHABLE_STALE_HOURS = 25


def _ptr_arpa_name(ip: str) -> str | None:
    """Return the in-addr.arpa name for an IPv4 address, or None for IPv6."""
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(reversed(parts)) + ".in-addr.arpa"
    return None


def _subnet_for_ip(subnets: list[Subnet], ip: str) -> int | None:
    for s in subnets:
        if ip_in_cidr(ip, s.cidr):
            return s.id
    return None


def detect_drift(db, subnet_id: int | None = None) -> None:
    """Detect all drift categories. If subnet_id is given, scope to that subnet;
    otherwise evaluate every subnet's address space and all cached records."""
    now = utcnow()

    if subnet_id is not None:
        scope_subnets = [s for s in [db.get(Subnet, subnet_id)] if s is not None]
    else:
        scope_subnets = db.query(Subnet).all()
    if not scope_subnets:
        return
    scope_ids = {s.id for s in scope_subnets}

    def in_scope(ip: str) -> bool:
        return any(ip_in_cidr(ip, s.cidr) for s in scope_subnets)

    detected: set[tuple[str, str]] = set()

    def _upsert(ip: str, category: DriftCategory, details: dict, sid: int | None) -> None:
        cat = category.value
        if (ip, cat) in detected:
            return  # already handled this pass (e.g. multiple leases for one IP)
        detected.add((ip, cat))
        details_str = json.dumps(details)
        existing = db.query(DriftItem).filter_by(ip_address=ip, category=cat).first()
        is_new_or_reopened = False
        if existing:
            existing.detected_at = now
            existing.details = details_str
            existing.severity = DRIFT_SEVERITY[category]
            existing.subnet_id = sid
            if existing.resolved:
                existing.resolved = False
                existing.resolved_at = None
                is_new_or_reopened = True
        else:
            db.add(DriftItem(
                ip_address=ip, category=cat, severity=DRIFT_SEVERITY[category],
                subnet_id=sid, details=details_str, detected_at=now, resolved=False,
            ))
            is_new_or_reopened = True

        if is_new_or_reopened:
            # "collision" kept for alerting back-compat (3 conflict categories);
            # "drift" fires for every category and drives automation rules.
            if category in _CONFLICT_CATEGORIES:
                emit("collision", f"ip:{ip}:{cat}", {"ip": ip, "type": cat, "subnet_id": sid})
            emit("drift", f"ip:{ip}:{cat}", {"ip": ip, "category": cat, "subnet_id": sid})

    # ── address-keyed data ──────────────────────────────────────────────────
    addr_q = db.query(IPAddress)
    if subnet_id is not None:
        addr_q = addr_q.filter(IPAddress.subnet_id == subnet_id)
    addresses = addr_q.all()
    addr_by_ip = {a.address: a for a in addresses}
    all_addr_ips = {a.address for a in db.query(IPAddress.address).all()}

    dns_records = db.query(CachedDNSRecord).filter(
        CachedDNSRecord.record_type.in_(["A", "AAAA"])
    ).all()
    dns_by_value: dict[str, CachedDNSRecord] = {}
    for r in dns_records:
        dns_by_value.setdefault(r.value, r)

    leases = db.query(CachedDHCPLease).all()
    lease_by_ip: dict[str, CachedDHCPLease] = {}
    for l in leases:
        lease_by_ip.setdefault(l.ip_address, l)

    # ── active_but_available (latest scan reachable, IPAM available) ─────────
    latest_scan_by_ip: dict[str, ScanResult] = {}
    sr_q = db.query(ScanResult).order_by(ScanResult.scanned_at.desc())
    if subnet_id is not None:
        sr_q = sr_q.filter(ScanResult.subnet_id == subnet_id)
    for r in sr_q.all():
        latest_scan_by_ip.setdefault(r.ip_address, r)
    for ip, sr in latest_scan_by_ip.items():
        a = addr_by_ip.get(ip)
        if sr.reachable and a is not None and a.status == AddressStatus.available:
            _upsert(ip, DriftCategory.active_but_available,
                    {"ipam_status": "available", "latency_ms": sr.latency_ms}, a.subnet_id)

    # ── multi_dhcp_scope ─────────────────────────────────────────────────────
    multi = (
        db.query(CachedDHCPLease.ip_address)
        .group_by(CachedDHCPLease.ip_address)
        .having(func.count(CachedDHCPLease.source.distinct()) > 1)
        .all()
    )
    for (ip,) in multi:
        if not in_scope(ip):
            continue
        sources = sorted({l.source for l in leases if l.ip_address == ip})
        _upsert(ip, DriftCategory.multi_dhcp_scope, {"sources": sources},
                _subnet_for_ip(scope_subnets, ip))

    # ── hostname_mismatch ────────────────────────────────────────────────────
    for a in addresses:
        if not a.hostname:
            continue
        ipam_name = a.hostname.lower()
        lease = lease_by_ip.get(a.address)
        dhcp_name = lease.name.lower() if (lease and lease.name) else None
        rec = dns_by_value.get(a.address)
        dns_name = rec.name.lower() if (rec and rec.name) else None
        if (dhcp_name and dhcp_name != ipam_name) or (dns_name and dns_name != ipam_name):
            _upsert(a.address, DriftCategory.hostname_mismatch, {
                "ipam": a.hostname,
                "dhcp": lease.name if (lease and lease.name) else None,
                "dns":  rec.name if (rec and rec.name) else None,
            }, a.subnet_id)

    # ── missing_dns ──────────────────────────────────────────────────────────
    for a in addresses:
        if a.status not in _USED_STATUSES:
            continue
        if a.address not in dns_by_value:
            _upsert(a.address, DriftCategory.missing_dns,
                    {"hostname": a.hostname, "status": a.status.value}, a.subnet_id)

    # ── orphan_dns ───────────────────────────────────────────────────────────
    for r in dns_records:
        if r.value in all_addr_ips or not in_scope(r.value):
            continue
        _upsert(r.value, DriftCategory.orphan_dns,
                {"name": r.name, "zone": r.zone, "source": r.source},
                _subnet_for_ip(scope_subnets, r.value))

    # ── orphan_dhcp ──────────────────────────────────────────────────────────
    for l in leases:
        if l.ip_address in all_addr_ips or not in_scope(l.ip_address):
            continue
        _upsert(l.ip_address, DriftCategory.orphan_dhcp,
                {"name": l.name, "mac": l.mac_address, "scope_id": l.scope_id, "source": l.source},
                _subnet_for_ip(scope_subnets, l.ip_address))

    # ── mac_mismatch ─────────────────────────────────────────────────────────
    for a in addresses:
        if not a.mac_address:
            continue
        lease = lease_by_ip.get(a.address)
        if lease is None or not lease.mac_address:
            continue
        if normalize_mac_optional(a.mac_address) != normalize_mac_optional(lease.mac_address):
            _upsert(a.address, DriftCategory.mac_mismatch,
                    {"ipam_mac": a.mac_address, "dhcp_mac": lease.mac_address}, a.subnet_id)

    # ── missing_dhcp ─────────────────────────────────────────────────────────
    for a in addresses:
        if a.status not in _USED_STATUSES:
            continue
        if a.address not in lease_by_ip:
            _upsert(a.address, DriftCategory.missing_dhcp,
                    {"hostname": a.hostname, "status": a.status.value}, a.subnet_id)

    # ── ptr_mismatch ──────────────────────────────────────────────────────────
    # Only flagged when a PTR record EXISTS in the cache but its value doesn't
    # match the A record name for that IP.
    all_ptr = db.query(CachedDNSRecord).filter_by(record_type="PTR").all()
    ptr_by_arpa: dict[str, CachedDNSRecord] = {}
    for r in all_ptr:
        ptr_by_arpa[r.name.lower().rstrip(".")] = r

    for a in addresses:
        rec = dns_by_value.get(a.address)
        if rec is None:
            continue  # no A record — can't evaluate PTR
        arpa_name = _ptr_arpa_name(a.address)
        if arpa_name is None:
            continue
        ptr_rec = ptr_by_arpa.get(arpa_name)
        if ptr_rec is None:
            continue  # no PTR — absence is not flagged here
        a_name = rec.name.lower().rstrip(".")
        ptr_val = ptr_rec.value.lower().rstrip(".")
        # OK if PTR equals the A name or if A name is the first label of the PTR FQDN.
        if ptr_val != a_name and not ptr_val.startswith(a_name + "."):
            _upsert(a.address, DriftCategory.ptr_mismatch,
                    {"a_name": rec.name, "ptr_value": ptr_rec.value}, a.subnet_id)

    # ── unreachable_assigned ──────────────────────────────────────────────────
    stale_threshold = now - timedelta(hours=_UNREACHABLE_STALE_HOURS)
    for ip, sr in latest_scan_by_ip.items():
        if sr.reachable or sr.scanned_at < stale_threshold:
            continue
        a = addr_by_ip.get(ip)
        if a is None or a.status != AddressStatus.assigned:
            continue
        _upsert(ip, DriftCategory.unreachable_assigned,
                {"last_scanned": sr.scanned_at.isoformat()}, a.subnet_id)

    # ── auto-resolve cleared items in scope ──────────────────────────────────
    for d in db.query(DriftItem).filter(DriftItem.resolved.is_(False)).all():
        if (d.ip_address, d.category) in detected:
            continue
        if subnet_id is not None and not in_scope(d.ip_address):
            continue
        d.resolved = True
        d.resolved_at = now

    db.commit()


def detect_drift_bg() -> None:
    db = SessionLocal()
    try:
        detect_drift(db)
        from app.drift_remediation import remediate_drift
        remediate_drift(db)
    except Exception:
        logger.exception("detect_drift_bg failed")
    finally:
        db.close()
