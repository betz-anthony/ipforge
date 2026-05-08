import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.cache import (
    CachedDNSZone, CachedDNSRecord,
    CachedDHCPScope, CachedDHCPLease,
    SyncStatus,
)
from app.utils import ip_in_cidr as _ip_in_cidr

logger = logging.getLogger(__name__)

_dns_lock  = threading.Lock()
_dhcp_lock = threading.Lock()


def _auto_populate_from_cache(db) -> None:
    """Upsert IPAM address records for IPs found in DNS/DHCP cache that match a known subnet."""
    from app.models.address import IPAddress, AddressStatus
    from app.models.subnet import Subnet

    subnets = db.query(Subnet).all()
    if not subnets:
        return

    existing_map: dict[str, IPAddress] = {
        row.address: row for row in db.query(IPAddress).all()
    }

    # Collect candidates: {ip -> {hostname, mac_address}}
    # DNS first, DHCP overwrites (richer data)
    candidates: dict[str, dict] = {}
    for r in db.query(CachedDNSRecord).filter(
        CachedDNSRecord.record_type.in_(["A", "AAAA"])
    ).all():
        ip = r.value.strip()
        if ip not in candidates:
            candidates[ip] = {"hostname": r.name, "mac_address": None}

    for l in db.query(CachedDHCPLease).all():
        ip = l.ip_address.strip()
        candidates[ip] = {
            "hostname": l.name or candidates.get(ip, {}).get("hostname"),
            "mac_address": l.mac_address,
        }

    now = _utcnow()
    created = 0

    for ip, meta in candidates.items():
        if ip in existing_map:
            addr = existing_map[ip]
            changed = False
            if not addr.hostname and meta["hostname"]:
                addr.hostname = meta["hostname"]
                changed = True
            if not addr.mac_address and meta["mac_address"]:
                addr.mac_address = meta["mac_address"]
                changed = True
            if changed:
                addr.updated_at = now
            continue

        subnet = next((s for s in subnets if _ip_in_cidr(ip, s.cidr)), None)
        if subnet is None:
            continue

        db.add(IPAddress(
            address=ip,
            subnet_id=subnet.id,
            hostname=meta["hostname"],
            mac_address=meta["mac_address"],
            status=AddressStatus.assigned,
        ))
        existing_map[ip] = None  # type: ignore[assignment]  # prevent duplicate inserts
        created += 1

    db.commit()
    if created:
        logger.info("Auto-populated %d IPAM address records from DNS/DHCP cache", created)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _set_status(db, key: str, status: str, error: str | None = None) -> None:
    row = db.get(SyncStatus, key)
    if row is None:
        row = SyncStatus(key=key)
        db.add(row)
    row.synced_at = _utcnow()
    row.status = status
    row.error = error
    db.commit()


def sync_dns() -> None:
    if not _dns_lock.acquire(blocking=False):
        logger.info("DNS sync already running, skipping")
        return
    db = SessionLocal()
    try:
        _set_status(db, "dns", "running")
        from app.providers.registry import get_dns_providers
        providers = get_dns_providers()

        def _fetch_provider(p):
            zones = p.get_zones()
            results: list[tuple[str, list]] = []
            with ThreadPoolExecutor(max_workers=min(len(zones), 8) or 1) as zex:
                fmap = {zex.submit(p.get_records, z): z for z in zones}
                for f in as_completed(fmap):
                    zone = fmap[f]
                    try:
                        results.append((zone, f.result()))
                    except Exception as e:
                        logger.error("DNS %s get_records(%s): %s", p.source, zone, e)
            return len(zones), results

        now = _utcnow()
        with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
            fmap = {ex.submit(_fetch_provider, p): p for p in providers}
            for f in as_completed(fmap):
                p = fmap[f]
                try:
                    zones_count, zone_records = f.result()
                except Exception as e:
                    logger.error("DNS %s sync: %s", p.source, e)
                    continue
                if zones_count > 0 and not zone_records:
                    logger.warning("DNS %s: %d zones listed but 0 records fetched, preserving cache", p.source, zones_count)
                    continue
                db.query(CachedDNSZone).filter_by(source=p.source).delete()
                db.query(CachedDNSRecord).filter_by(source=p.source).delete()
                for zone, records in zone_records:
                    db.add(CachedDNSZone(zone=zone, source=p.source, synced_at=now))
                    for r in records:
                        db.add(CachedDNSRecord(
                            name=r.name, record_type=r.record_type, value=r.value,
                            zone=zone, ttl=r.ttl, source=p.source, synced_at=now,
                        ))
                db.commit()

        _auto_populate_from_cache(db)
        _set_status(db, "dns", "ok")
    except Exception as e:
        logger.error("DNS sync failed: %s", e, exc_info=True)
        _set_status(db, "dns", "error", str(e))
    finally:
        db.close()
        _dns_lock.release()


def sync_dhcp() -> None:
    if not _dhcp_lock.acquire(blocking=False):
        logger.info("DHCP sync already running, skipping")
        return
    db = SessionLocal()
    try:
        _set_status(db, "dhcp", "running")
        from app.providers.registry import get_dhcp_providers
        providers = get_dhcp_providers()

        now = _utcnow()
        scope_list: list[tuple] = []  # (provider, scope_id)

        with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
            fmap = {ex.submit(p.get_scopes): p for p in providers}
            for f in as_completed(fmap):
                p = fmap[f]
                try:
                    scopes = f.result()
                except Exception as e:
                    logger.error("DHCP %s get_scopes: %s", p.source, e)
                    continue
                db.query(CachedDHCPScope).filter_by(source=p.source).delete()
                for s in scopes:
                    db.add(CachedDHCPScope(
                        scope_id=s.scope_id, name=s.name, subnet_mask=s.subnet_mask,
                        start_range=s.start_range, end_range=s.end_range,
                        description=s.description, active=s.active,
                        ip_version=s.ip_version, source=p.source, synced_at=now,
                    ))
                    scope_list.append((p, s.scope_id))
                db.commit()

        def _fetch_leases(p, scope_id):
            return p, scope_id, p.get_leases(scope_id)

        with ThreadPoolExecutor(max_workers=min(len(scope_list), 8) or 1) as ex:
            fmap = {ex.submit(_fetch_leases, p, sid): (p, sid) for p, sid in scope_list}
            for f in as_completed(fmap):
                try:
                    p, scope_id, leases = f.result()
                except Exception as e:
                    p, scope_id = fmap[f]
                    logger.error("DHCP %s get_leases(%s): %s", p.source, scope_id, e)
                    continue
                db.query(CachedDHCPLease).filter_by(scope_id=scope_id, source=p.source).delete()
                for l in leases:
                    db.add(CachedDHCPLease(
                        scope_id=scope_id, ip_address=l.ip_address,
                        mac_address=l.mac_address, client_duid=l.client_duid,
                        iaid=l.iaid, name=l.name, description=l.description,
                        source=p.source, synced_at=now,
                    ))
                db.commit()

        _auto_populate_from_cache(db)
        _set_status(db, "dhcp", "ok")
    except Exception as e:
        logger.error("DHCP sync failed: %s", e, exc_info=True)
        _set_status(db, "dhcp", "error", str(e))
    finally:
        db.close()
        _dhcp_lock.release()


def sync_all() -> None:
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(sync_dns)
        f2 = ex.submit(sync_dhcp)
        f1.result()
        f2.result()


def start_background_sync(interval: int = 300) -> None:
    def _loop():
        while True:
            try:
                sync_all()
            except Exception as e:
                logger.error("Background sync error: %s", e)
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True, name="ipam-sync").start()
    logger.info("Background sync started (interval=%ds)", interval)
