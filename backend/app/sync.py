import ipaddress
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.alerting.emit import emit
from app.database import SessionLocal
from app.models.cache import (
    CachedDNSZone, CachedDNSRecord,
    CachedDHCPScope, CachedDHCPLease, CachedDHCPScopePool,
    SyncStatus,
)
from app.core.mac import normalize_mac
from app.core.time import utcnow
from app.models.subnet import Subnet
from app.models.subnet_range import SubnetRange
from app.utils import ip_in_cidr as _ip_in_cidr

logger = logging.getLogger(__name__)

_dns_lock  = threading.Lock()
_dhcp_lock = threading.Lock()
# Serializes the IPAM-write phase: sync_dns and sync_dhcp run in parallel and
# both upsert IPAddress rows, so concurrent inserts of the same newly-seen IP
# would collide on the unique address constraint.
_ipam_write_lock = threading.Lock()


def _pools_for_scope(p, scope) -> list[tuple[str, str]]:
    """Every pool range for this scope. Providers that expose multiple
    pools (Kea) implement get_scope_pools; everyone else's one range is
    already on the DHCPScope object itself from get_scopes()."""
    get_pools = getattr(p, "get_scope_pools", None)
    if callable(get_pools):
        return get_pools(scope.scope_id)
    if scope.start_range and scope.end_range:
        return [(scope.start_range, scope.end_range)]
    return []


def _resolve_subnet_id(subnets, scope) -> int | None:
    """Most-specific (longest-prefix) subnet whose CIDR contains the scope's
    start_range. Subnet hierarchy means a scope can sit inside both a
    supernet and a child subnet — the child is the correct match."""
    if not scope.start_range:
        return None
    best_id: int | None = None
    best_prefixlen = -1
    for s in subnets:
        if not _ip_in_cidr(scope.start_range, s.cidr):
            continue
        prefixlen = ipaddress.ip_network(s.cidr, strict=False).prefixlen
        if prefixlen > best_prefixlen:
            best_prefixlen = prefixlen
            best_id = s.id
    return best_id


def _fetch_reserved_range_data(p, scope):
    return p, scope, p.get_scope_gateway(scope.scope_id), p.get_scope_exclusions(scope.scope_id)


def _write_reserved_ranges(db, subnet_id, source, gateway, exclusions) -> None:
    subnet = db.get(Subnet, subnet_id)
    if subnet is None:
        # Resolved earlier this same sync pass, but the row could theoretically be
        # gone by the time we get here — nothing sane to validate against.
        logger.warning("DHCP %s: subnet_id %s not found, skipping reserved-range write", source, subnet_id)
        return
    network = ipaddress.ip_network(subnet.cidr, strict=False)

    candidates: list[tuple[str, str, str]] = []  # (kind, start_ip, end_ip)
    if gateway:
        candidates.append(("gateway", gateway, gateway))
    for start, end in exclusions:
        candidates.append(("excluded", start, end))

    # Provider-sourced values are untrusted input — validate before writing, the
    # same way the manual create-range API endpoint does. A malformed value from
    # one provider must not land in start_ip/end_ip unparsed: readers across the
    # app (subnet_map, reserved_ip_set, allocation candidate search) assume every
    # SubnetRange row parses cleanly as an IP and 500 the whole subnet list
    # otherwise.
    new_rows: list[tuple[str, str, str]] = []
    for kind, start_ip, end_ip in candidates:
        try:
            start = ipaddress.ip_address(start_ip)
            end = ipaddress.ip_address(end_ip)
        except ValueError:
            logger.warning(
                "DHCP %s: dropping unparseable %s range %r-%r for subnet %s",
                source, kind, start_ip, end_ip, subnet.cidr,
            )
            continue
        if start.version != subnet.ip_version or end.version != subnet.ip_version:
            logger.warning(
                "DHCP %s: dropping %s range %s-%s — IP version mismatch with subnet %s",
                source, kind, start_ip, end_ip, subnet.cidr,
            )
            continue
        if start not in network or end not in network:
            logger.warning(
                "DHCP %s: dropping %s range %s-%s — outside subnet %s",
                source, kind, start_ip, end_ip, subnet.cidr,
            )
            continue
        new_rows.append((kind, start_ip, end_ip))

    manual_ranges = {
        (r.start_ip, r.end_ip)
        for r in db.query(SubnetRange).filter_by(subnet_id=subnet_id, source=None).all()
    }

    db.query(SubnetRange).filter_by(subnet_id=subnet_id, source=source).delete()
    for kind, start_ip, end_ip in new_rows:
        if (start_ip, end_ip) in manual_ranges:
            continue  # operator already has an identical manual range — don't clutter
        db.add(SubnetRange(subnet_id=subnet_id, start_ip=start_ip, end_ip=end_ip, kind=kind, source=source))
    db.commit()


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
        mac = None
        if l.mac_address:
            try:
                mac = normalize_mac(l.mac_address)
            except ValueError:
                logger.warning("sync: skipping malformed MAC %r for %s", l.mac_address, ip)
        candidates[ip] = {
            "hostname": l.name or candidates.get(ip, {}).get("hostname"),
            "mac_address": mac,
        }

    now = utcnow()
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


def _backfill_dns_providers(db) -> None:
    from app.models.address import IPAddress
    addr_map: dict[str, IPAddress] = {
        a.address: a
        for a in db.query(IPAddress).filter(IPAddress.dns_provider.is_(None)).all()
    }
    for r in db.query(CachedDNSRecord).filter(CachedDNSRecord.record_type.in_(["A", "AAAA"])).all():
        addr = addr_map.get(r.value.strip())
        if addr is not None:
            addr.dns_provider = r.source
            addr.dns_zone = r.zone
    db.commit()


def _backfill_dhcp_providers(db) -> None:
    from app.models.address import IPAddress
    addr_map: dict[str, IPAddress] = {
        a.address: a
        for a in db.query(IPAddress).filter(IPAddress.dhcp_provider.is_(None)).all()
    }
    for l in db.query(CachedDHCPLease).all():
        addr = addr_map.get(l.ip_address.strip())
        if addr is not None:
            addr.dhcp_provider = l.source
            addr.dhcp_scope_id = l.scope_id
    db.commit()


def _set_status(db, key: str, status: str, error: str | None = None) -> None:
    # Callers include the sync error handlers, where a prior flush may have left
    # the session's transaction in a doomed state. Roll back first so the status
    # write itself can't raise PendingRollbackError and mask the original error.
    db.rollback()
    row = db.get(SyncStatus, key)
    if row is None:
        row = SyncStatus(key=key)
        db.add(row)
    row.synced_at = utcnow()
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

        now = utcnow()
        with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
            fmap = {ex.submit(_fetch_provider, p): p for p in providers}
            for f in as_completed(fmap):
                p = fmap[f]
                try:
                    zones_count, zone_records = f.result()
                except Exception as e:
                    logger.error("DNS %s sync: %s", p.source, e)
                    emit("sync_error", f"sync:{p.source}",
                         {"provider": p.source, "error": str(e)})
                    continue
                if zones_count > 0 and not zone_records:
                    logger.warning("DNS %s: %d zones listed but 0 records fetched, preserving cache", p.source, zones_count)
                    continue
                if len(zone_records) < zones_count:
                    logger.warning(
                        "DNS %s: %d/%d zones fetched successfully — leaving the rest as last-known-good",
                        p.source, len(zone_records), zones_count,
                    )
                # Scope the delete to zones that actually fetched this pass — a zone whose
                # get_records() failed keeps its last-known-good cache instead of being wiped
                # with nothing to replace it.
                synced_zones = [zone for zone, _ in zone_records]
                db.query(CachedDNSZone).filter(
                    CachedDNSZone.source == p.source, CachedDNSZone.zone.in_(synced_zones)
                ).delete(synchronize_session=False)
                db.query(CachedDNSRecord).filter(
                    CachedDNSRecord.source == p.source, CachedDNSRecord.zone.in_(synced_zones)
                ).delete(synchronize_session=False)
                for zone, records in zone_records:
                    db.add(CachedDNSZone(zone=zone, source=p.source, synced_at=now))
                    for r in records:
                        db.add(CachedDNSRecord(
                            name=r.name, record_type=r.record_type, value=r.value,
                            zone=zone, ttl=r.ttl, source=p.source, synced_at=now,
                        ))
                db.commit()

        with _ipam_write_lock:
            _auto_populate_from_cache(db)
            _backfill_dns_providers(db)
        _set_status(db, "dns", "ok")
    except Exception as e:
        logger.error("DNS sync failed: %s", e, exc_info=True)
        emit("sync_error", "sync:dns", {"provider": "dns", "error": str(e)})
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

        now = utcnow()
        scope_list: list[tuple] = []  # (provider, DHCPScope)

        with ThreadPoolExecutor(max_workers=len(providers) or 1) as ex:
            fmap = {ex.submit(p.get_scopes): p for p in providers}
            for f in as_completed(fmap):
                p = fmap[f]
                try:
                    scopes = f.result()
                except Exception as e:
                    logger.error("DHCP %s get_scopes: %s", p.source, e)
                    emit("sync_error", f"sync:{p.source}",
                         {"provider": p.source, "error": str(e)})
                    continue
                db.query(CachedDHCPScope).filter_by(source=p.source).delete()
                for s in scopes:
                    db.add(CachedDHCPScope(
                        scope_id=s.scope_id, name=s.name, subnet_mask=s.subnet_mask,
                        start_range=s.start_range, end_range=s.end_range,
                        description=s.description, active=s.active,
                        ip_version=s.ip_version, source=p.source, synced_at=now,
                    ))
                    scope_list.append((p, s))
                    try:
                        pools = _pools_for_scope(p, s)
                    except Exception as e:
                        logger.error("DHCP %s get_scope_pools(%s): %s", p.source, s.scope_id, e)
                    else:
                        db.query(CachedDHCPScopePool).filter_by(scope_id=s.scope_id, source=p.source).delete()
                        for pool_start, pool_end in pools:
                            db.add(CachedDHCPScopePool(
                                scope_id=s.scope_id, source=p.source,
                                start_ip=pool_start, end_ip=pool_end,
                            ))
                db.commit()

        def _fetch_leases(p, scope_id):
            return p, scope_id, p.get_leases(scope_id)

        with ThreadPoolExecutor(max_workers=min(len(scope_list), 8) or 1) as ex:
            fmap = {ex.submit(_fetch_leases, p, s.scope_id): (p, s) for p, s in scope_list}
            for f in as_completed(fmap):
                try:
                    p, scope_id, leases = f.result()
                except Exception as e:
                    p, s = fmap[f]
                    logger.error("DHCP %s get_leases(%s): %s", p.source, s.scope_id, e)
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

        subnets = db.query(Subnet).all()
        # Resolve each scope's subnet once (not per as_completed callback) and carry it
        # forward in fmap, so a scope's subnet_id is only ever computed one time.
        scope_subnets = [(p, s, _resolve_subnet_id(subnets, s)) for p, s in scope_list]

        # Multiple scopes (e.g. split pools, or two scopes from the same provider that
        # both land in the same subnet) can resolve to the same (subnet_id, source).
        # Aggregate every scope's contribution before writing anything, so the second
        # scope's write can't clobber the first's — a delete-then-insert per scope
        # would otherwise make the surviving rows depend on as_completed() ordering.
        aggregated: dict[tuple[int, str], dict] = {}
        with ThreadPoolExecutor(max_workers=min(len(scope_list), 8) or 1) as ex:
            fmap = {
                ex.submit(_fetch_reserved_range_data, p, s): (p, s, subnet_id)
                for p, s, subnet_id in scope_subnets if subnet_id is not None
            }
            for f in as_completed(fmap):
                p, s, subnet_id = fmap[f]
                try:
                    _, _, gateway, exclusions = f.result()
                except Exception as e:
                    logger.error("DHCP %s get_scope_gateway/exclusions(%s): %s", p.source, s.scope_id, e)
                    continue
                agg = aggregated.setdefault((subnet_id, p.source), {"gateway": None, "exclusions": []})
                if gateway:
                    # If two scopes for the same subnet both report a gateway, last one
                    # observed wins (as_completed order) — exclusions never lose data
                    # this way since they're concatenated, not overwritten.
                    agg["gateway"] = gateway
                agg["exclusions"].extend(exclusions)

        for (subnet_id, source), agg in aggregated.items():
            _write_reserved_ranges(db, subnet_id, source, agg["gateway"], agg["exclusions"])

        with _ipam_write_lock:
            _auto_populate_from_cache(db)
            _backfill_dhcp_providers(db)
        _set_status(db, "dhcp", "ok")
    except Exception as e:
        logger.error("DHCP sync failed: %s", e, exc_info=True)
        emit("sync_error", "sync:dhcp", {"provider": "dhcp", "error": str(e)})
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
    # Recompute drift now that the cache reflects current actual state. Run it in
    # a detached daemon thread so a slow drift pass can never delay or wedge the
    # sync cadence.
    try:
        from app.drift import detect_drift_bg
        threading.Thread(target=detect_drift_bg, daemon=True, name="ipam-postsync-drift").start()
    except Exception:
        logger.exception("post-sync drift detection failed to start")


def start_background_sync(interval: int = 300) -> None:
    def _loop():
        while True:
            try:
                logger.info("Background sync starting")
                sync_all()
                logger.info("Background sync finished")
            except Exception as e:
                logger.error("Background sync error: %s", e, exc_info=True)
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True, name="ipam-sync").start()
    logger.info("Background sync started (interval=%ds)", interval)
