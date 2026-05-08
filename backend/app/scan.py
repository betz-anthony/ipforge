import ipaddress
import json
import logging
import platform
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import func

from app.database import SessionLocal
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord, SyncStatus
from app.models.scan import Collision, CollisionType, ScanResult
from app.models.subnet import Subnet
from app.utils import ip_in_cidr

logger = logging.getLogger(__name__)

_subnet_locks: dict[int, threading.Lock] = {}
_locks_mu = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_subnet_lock(subnet_id: int) -> threading.Lock:
    with _locks_mu:
        if subnet_id not in _subnet_locks:
            _subnet_locks[subnet_id] = threading.Lock()
        return _subnet_locks[subnet_id]


def _set_scan_status(db, subnet_id: int, status: str, error: str | None = None) -> None:
    key = f"scan:{subnet_id}"
    row = db.get(SyncStatus, key)
    if row is None:
        row = SyncStatus(key=key)
        db.add(row)
    row.synced_at = _utcnow()
    row.status = status
    row.error = error
    db.commit()


def _scan_host(ip: str) -> dict:
    system = platform.system()
    cmd = (
        ["ping", "-c", "1", "-W", "1000", ip] if system == "Darwin"
        else ["ping", "-c", "1", "-W", "1", ip]
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        output = result.stdout + result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"ip": ip, "reachable": False, "latency_ms": None}

    loss_m = re.search(r'(\d+)%\s+packet loss', output)
    loss_pct = int(loss_m.group(1)) if loss_m else 100
    reachable = loss_pct < 100

    rtt_m = re.search(
        r'(?:round-trip|rtt)\s+min/avg/max/\S+\s+=\s+([\d.]+)/([\d.]+)/([\d.]+)', output
    )
    latency_ms = float(rtt_m.group(2)) if rtt_m else None

    return {"ip": ip, "reachable": reachable, "latency_ms": latency_ms}


def _get_host_list(subnet: Subnet, start_ip: str | None, end_ip: str | None) -> list[str]:
    network = ipaddress.ip_network(subnet.cidr, strict=False)

    if start_ip is None and end_ip is None:
        if network.prefixlen < 24:
            raise ValueError(
                f"Subnet {subnet.cidr} is larger than /24. Provide start_ip and end_ip."
            )
        return [str(h) for h in network.hosts()]

    start = ipaddress.ip_address(start_ip)
    end   = ipaddress.ip_address(end_ip)
    if start not in network or end not in network:
        raise ValueError("start_ip and end_ip must both be within the subnet CIDR")
    if start > end:
        raise ValueError("start_ip must be less than or equal to end_ip")

    hosts: list[str] = []
    current = start
    while current <= end and len(hosts) < 1024:
        hosts.append(str(current))
        current += 1
    return hosts


def _detect_collisions(db, subnet_id: int) -> None:
    subnet = db.get(Subnet, subnet_id)
    if subnet is None:
        return

    now = _utcnow()

    latest_scan = (
        db.query(ScanResult)
        .filter_by(subnet_id=subnet_id)
        .order_by(ScanResult.scanned_at.desc())
        .first()
    )
    if latest_scan is None:
        return
    scan_time = latest_scan.scanned_at

    def _upsert(ip: str, ctype: str, details: dict) -> None:
        details_str = json.dumps(details)
        existing = db.query(Collision).filter_by(ip_address=ip, collision_type=ctype).first()
        if existing:
            existing.detected_at = now
            existing.details = details_str
            if existing.resolved:
                existing.resolved = False
                existing.resolved_at = None
        else:
            db.add(Collision(
                ip_address=ip,
                collision_type=ctype,
                details=details_str,
                detected_at=now,
                resolved=False,
            ))

    # Pass 1: active_but_available
    reachable_ips = {
        r.ip_address
        for r in db.query(ScanResult)
        .filter_by(subnet_id=subnet_id, reachable=True)
        .filter(ScanResult.scanned_at == scan_time)
        .all()
    }
    for ip in reachable_ips:
        addr = db.query(IPAddress).filter_by(address=ip, status=AddressStatus.available).first()
        if addr:
            latency = (
                db.query(ScanResult.latency_ms)
                .filter_by(subnet_id=subnet_id, ip_address=ip)
                .filter(ScanResult.scanned_at == scan_time)
                .scalar()
            )
            _upsert(ip, CollisionType.active_but_available, {
                "ipam_status": "available", "latency_ms": latency,
            })

    # Pass 2: multi_dhcp_scope
    rows = (
        db.query(CachedDHCPLease.ip_address,
                 func.count(CachedDHCPLease.source.distinct()).label("cnt"))
        .group_by(CachedDHCPLease.ip_address)
        .having(func.count(CachedDHCPLease.source.distinct()) > 1)
        .all()
    )
    for row in rows:
        if not ip_in_cidr(row.ip_address, subnet.cidr):
            continue
        sources = list({l.source for l in
                        db.query(CachedDHCPLease).filter_by(ip_address=row.ip_address).all()})
        _upsert(row.ip_address, CollisionType.multi_dhcp_scope, {"sources": sources})

    # Pass 3: hostname_mismatch
    for addr in db.query(IPAddress).all():
        if not addr.hostname or not ip_in_cidr(addr.address, subnet.cidr):
            continue
        ipam_name = addr.hostname.lower()

        lease = db.query(CachedDHCPLease).filter_by(ip_address=addr.address).first()
        dhcp_name = lease.name.lower() if (lease and lease.name) else None

        dns_rec = (
            db.query(CachedDNSRecord)
            .filter(
                CachedDNSRecord.record_type.in_(["A", "AAAA"]),
                CachedDNSRecord.value == addr.address,
            )
            .first()
        )
        dns_name = dns_rec.name.lower() if (dns_rec and dns_rec.name) else None

        if (dhcp_name and dhcp_name != ipam_name) or (dns_name and dns_name != ipam_name):
            _upsert(addr.address, CollisionType.hostname_mismatch, {
                "ipam": addr.hostname,
                "dhcp": lease.name if (lease and lease.name) else None,
                "dns":  dns_rec.name if (dns_rec and dns_rec.name) else None,
            })

    db.commit()


def scan_subnet(
    subnet_id: int,
    start_ip: str | None = None,
    end_ip:   str | None = None,
    _db=None,
) -> None:
    lock = _get_subnet_lock(subnet_id)
    if not lock.acquire(blocking=False):
        logger.info("Scan already running for subnet %d, skipping", subnet_id)
        return

    own_db = _db is None
    db = SessionLocal() if own_db else _db
    try:
        _set_scan_status(db, subnet_id, "running")

        subnet = db.get(Subnet, subnet_id)
        if subnet is None:
            raise ValueError(f"Subnet {subnet_id} not found")

        hosts = _get_host_list(subnet, start_ip, end_ip)
        now   = _utcnow()

        existing_ips = {row.address for row in db.query(IPAddress.address).all()}

        with ThreadPoolExecutor(max_workers=50) as ex:
            futures = {ex.submit(_scan_host, ip): ip for ip in hosts}
            for future in as_completed(futures):
                result = future.result()
                ip = result["ip"]
                db.add(ScanResult(
                    subnet_id=subnet_id,
                    ip_address=ip,
                    reachable=result["reachable"],
                    latency_ms=result["latency_ms"],
                    scanned_at=now,
                ))
                if result["reachable"] and ip not in existing_ips:
                    db.add(IPAddress(
                        address=ip,
                        subnet_id=subnet_id,
                        status=AddressStatus.discovered,
                    ))
                    existing_ips.add(ip)

        db.commit()
        _detect_collisions(db, subnet_id)
        _set_scan_status(db, subnet_id, "ok")

    except Exception as e:
        logger.error("Scan failed for subnet %d: %s", subnet_id, e, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        _set_scan_status(db, subnet_id, "error", str(e))
    finally:
        lock.release()
        if own_db:
            db.close()


def scan_all_eligible(_db=None) -> None:
    own_db = _db is None
    db = SessionLocal() if own_db else _db
    try:
        subnets = db.query(Subnet).filter(Subnet.ip_version == 4).all()
    finally:
        if own_db:
            db.close()

    for s in subnets:
        net = ipaddress.ip_network(s.cidr, strict=False)
        if net.prefixlen >= 24:
            scan_subnet(s.id)
