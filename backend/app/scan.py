import ipaddress
import json
import logging
import platform
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.database import SessionLocal
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord, SyncStatus
from app.models.scan import Collision, CollisionType, ScanResult, ScanHistoryDay, AlertEvent, SubnetUtilizationDay
from app.models.subnet import Subnet
from app.core.time import utcnow
from app.utils import ip_in_cidr
from app.alerting.emit import emit

logger = logging.getLogger(__name__)

_subnet_locks: dict[int, threading.Lock] = {}
_locks_mu = threading.Lock()


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
    row.synced_at = utcnow()
    row.status = status
    row.error = error
    db.commit()


def _scan_host(ip: str) -> dict:
    system = platform.system()
    is_v6 = ":" in ip
    if is_v6:
        cmd = (
            ["ping", "-6", "-c", "1", "-W", "1000", ip] if system == "Darwin"
            else ["ping6", "-c", "1", "-W", "1", ip]
        )
    else:
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


# IPv6 equivalent of /24 is /120 (256 addresses). Scheduler uses this to guard
# auto-scan without explicit range — larger subnets require start_ip/end_ip.
_MAX_AUTO_PREFIXLEN = {4: 24, 6: 120}


def _get_host_list(subnet: Subnet, start_ip: str | None, end_ip: str | None) -> list[str]:
    network = ipaddress.ip_network(subnet.cidr, strict=False)
    min_prefix = _MAX_AUTO_PREFIXLEN[network.version]

    if start_ip is None and end_ip is None:
        if network.prefixlen < min_prefix:
            raise ValueError(
                f"Subnet {subnet.cidr} is larger than /{min_prefix}. Provide start_ip and end_ip."
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


def _update_last_seen(db, reachable_ips: set[str], now: datetime) -> None:
    if not reachable_ips:
        return
    db.query(IPAddress).filter(
        IPAddress.address.in_(reachable_ips)
    ).update({"last_seen": now}, synchronize_session=False)


def _upsert_daily_history(db, subnet_id: int, results: list[dict], now: datetime) -> None:
    today = now.date()
    for r in results:
        row = db.query(ScanHistoryDay).filter_by(
            ip_address=r["ip"], date=today
        ).first()
        if row is None:
            row = ScanHistoryDay(
                ip_address=r["ip"], subnet_id=subnet_id, date=today,
                up_count=0, total_count=0, avg_latency_ms=None, uptime_pct=0.0,
            )
            db.add(row)
        row.total_count += 1
        if r["reachable"]:
            prev_up = row.up_count
            row.up_count += 1
            if r["latency_ms"] is not None:
                if row.avg_latency_ms is None:
                    row.avg_latency_ms = r["latency_ms"]
                else:
                    row.avg_latency_ms = (
                        (row.avg_latency_ms * prev_up + r["latency_ms"]) / row.up_count
                    )
        row.uptime_pct = row.up_count / row.total_count * 100


def _detect_reachability_changes(db, subnet_id: int, now: datetime) -> None:
    current_results = (
        db.query(ScanResult)
        .filter_by(subnet_id=subnet_id)
        .filter(ScanResult.scanned_at == now)
        .all()
    )
    current_reachable = {r.ip_address for r in current_results if r.reachable}
    current_scanned   = {r.ip_address for r in current_results}

    prev_time_row = (
        db.query(ScanResult.scanned_at)
        .filter_by(subnet_id=subnet_id)
        .filter(ScanResult.scanned_at < now)
        .order_by(ScanResult.scanned_at.desc())
        .first()
    )
    if prev_time_row is None:
        return

    prev_results = (
        db.query(ScanResult)
        .filter_by(subnet_id=subnet_id)
        .filter(ScanResult.scanned_at == prev_time_row.scanned_at)
        .all()
    )
    prev_reachable = {r.ip_address for r in prev_results if r.reachable}
    prev_scanned   = {r.ip_address for r in prev_results}

    for ip in current_scanned & prev_scanned:
        was_up = ip in prev_reachable
        is_up  = ip in current_reachable
        if was_up and not is_up:
            addr = db.query(IPAddress).filter_by(address=ip).first()
            db.add(AlertEvent(
                event_type="went_unreachable",
                ip_address=ip,
                subnet_id=subnet_id,
                detected_at=now,
                details=json.dumps({"hostname": addr.hostname if addr else None}),
            ))
        elif not was_up and is_up:
            db.add(AlertEvent(
                event_type="came_back",
                ip_address=ip,
                subnet_id=subnet_id,
                detected_at=now,
                details=None,
            ))


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
        now   = utcnow()

        existing_ips = {row.address for row in db.query(IPAddress.address).all()}

        all_results: list[dict] = []
        reachable_ips: set[str] = set()

        with ThreadPoolExecutor(max_workers=50) as ex:
            futures = {ex.submit(_scan_host, ip): ip for ip in hosts}
            for future in as_completed(futures):
                result = future.result()
                ip = result["ip"]
                all_results.append(result)
                if result["reachable"]:
                    reachable_ips.add(ip)
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
                    emit("rogue", f"ip:{ip}",
                         {"ip": ip, "subnet_id": subnet_id})

        db.commit()
        _update_last_seen(db, reachable_ips, now)
        _upsert_daily_history(db, subnet_id, all_results, now)
        db.commit()
        _detect_reachability_changes(db, subnet_id, now)
        db.commit()
        from app.drift import detect_drift
        detect_drift(db, subnet_id)
        from app.drift_remediation import remediate_drift
        remediate_drift(db, subnet_id)
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
        subnets = db.query(Subnet).all()
    finally:
        if own_db:
            db.close()

    for s in subnets:
        net = ipaddress.ip_network(s.cidr, strict=False)
        if net.prefixlen >= _MAX_AUTO_PREFIXLEN[net.version]:
            scan_subnet(s.id)


_USED_STATUSES = [AddressStatus.assigned, AddressStatus.reserved, AddressStatus.discovered]


def subnet_total_count(cidr: str) -> int:
    net = ipaddress.ip_network(cidr, strict=False)
    if net.version == 6 or net.prefixlen >= 31:
        return net.num_addresses
    return max(1, net.num_addresses - 2)


def _snapshot_utilization(db, now: datetime) -> None:
    today = now.date()
    counts = dict(
        db.query(IPAddress.subnet_id, func.count(IPAddress.id))
        .filter(IPAddress.status.in_(_USED_STATUSES))
        .group_by(IPAddress.subnet_id)
        .all()
    )
    for s in db.query(Subnet).all():
        used = counts.get(s.id, 0)
        total = subnet_total_count(s.cidr)
        row = db.query(SubnetUtilizationDay).filter_by(subnet_id=s.id, date=today).first()
        if row is None:
            row = SubnetUtilizationDay(subnet_id=s.id, date=today)
            db.add(row)
        row.used_count = used
        row.total_count = total


def _get_global_scan_interval(db) -> int:
    from app.config import settings
    return settings.scan_interval_minutes


_SCAN_RESULT_RETENTION_DAYS = 7


_DRIFT_EVERY_TICKS = 5  # global drift pass cadence (~5 min at the 60s tick)


def scan_scheduler_loop() -> None:
    tick = 0
    while True:
        time.sleep(60)
        tick += 1
        db = SessionLocal()
        try:
            now = utcnow()
            cutoff = now - timedelta(days=_SCAN_RESULT_RETENTION_DAYS)
            deleted = db.query(ScanResult).filter(ScanResult.scanned_at < cutoff).delete(synchronize_session=False)
            if deleted:
                logger.info("Pruned %d old scan results (older than %d days)", deleted, _SCAN_RESULT_RETENTION_DAYS)
            db.commit()

            _snapshot_utilization(db, now)
            db.commit()

            global_interval = _get_global_scan_interval(db)
            subnets = db.query(Subnet).all()
            for s in subnets:
                net = ipaddress.ip_network(s.cidr, strict=False)
                if net.prefixlen < _MAX_AUTO_PREFIXLEN[net.version]:
                    continue  # too large for auto-scan; requires explicit start_ip/end_ip
                interval = s.scan_interval_minutes or global_interval
                status_row = db.get(SyncStatus, f"scan:{s.id}")
                if status_row and status_row.status == "running":
                    continue
                last = status_row.synced_at if status_row else None
                if last is None or (now - last).total_seconds() >= interval * 60:
                    threading.Thread(
                        target=scan_subnet, args=(s.id,), daemon=True,
                        name=f"ipam-scan-{s.id}",
                    ).start()

            if tick % _DRIFT_EVERY_TICKS == 0:
                from app.drift import detect_drift
                detect_drift(db)
        except Exception:
            logger.exception("scan_scheduler_loop error")
        finally:
            db.close()
