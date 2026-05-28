"""Discovery poller: build a source from a device, poll, persist endpoints."""
import logging
import threading
import time

from app.core.crypto import decrypt_secret
from app.core.time import utcnow
from app.database import SessionLocal
from app.discovery.base import DiscoverySource
from app.discovery.snmp import SnmpDiscovery
from app.models.cache import SyncStatus
from app.models.network_device import NetworkDevice, DiscoveredEndpoint

logger = logging.getLogger(__name__)


def build_source(device: NetworkDevice) -> DiscoverySource:
    cfg = {
        "host": device.host,
        "snmp_version": device.snmp_version,
        "community": decrypt_secret(device.community) if device.community else "",
        "v3_user": device.v3_user or "",
        "auth_protocol": device.auth_protocol,
        "auth_key": decrypt_secret(device.auth_key) if device.auth_key else "",
        "priv_protocol": device.priv_protocol,
        "priv_key": decrypt_secret(device.priv_key) if device.priv_key else "",
        "security_level": device.security_level,
    }
    return SnmpDiscovery(cfg, device.name)


def _set_status(db, device_id: int, status: str, error: str | None = None) -> None:
    key = f"discovery:{device_id}"
    row = db.get(SyncStatus, key)
    if row is None:
        row = SyncStatus(key=key)
        db.add(row)
    row.synced_at = utcnow()
    row.status = status
    row.error = error
    db.commit()


def poll_device(device_id: int, _db=None) -> None:
    own = _db is None
    db = SessionLocal() if own else _db
    try:
        device = db.get(NetworkDevice, device_id)
        if device is None:
            return
        _set_status(db, device_id, "running")
        source = build_source(device)
        endpoints = source.poll()
        now = utcnow()
        db.query(DiscoveredEndpoint).filter_by(device_id=device_id).delete(synchronize_session=False)
        for e in endpoints:
            db.add(DiscoveredEndpoint(
                device_id=device_id, ip=e.ip, mac=e.mac, ifindex=e.ifindex,
                port_name=e.port_name, vlan=e.vlan, last_seen=now, source=device.name,
            ))
        db.commit()
        _set_status(db, device_id, "ok")
    except Exception as exc:
        logger.error("Discovery poll failed for device %d: %s", device_id, exc, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        _set_status(db, device_id, "error", str(exc))
    finally:
        if own:
            db.close()


def discovery_poller_loop() -> None:
    while True:
        time.sleep(60)
        db = SessionLocal()
        try:
            now = utcnow()
            for d in db.query(NetworkDevice).filter_by(enabled=True).all():
                status = db.get(SyncStatus, f"discovery:{d.id}")
                if status and status.status == "running":
                    continue
                last = status.synced_at if status else None
                if last is None or (now - last).total_seconds() >= d.poll_interval_minutes * 60:
                    threading.Thread(target=poll_device, args=(d.id,), daemon=True,
                                     name=f"ipam-discovery-{d.id}").start()
        except Exception:
            logger.exception("discovery_poller_loop error")
        finally:
            db.close()
