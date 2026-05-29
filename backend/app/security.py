"""SECURITY-001 — security event detection + quarantine support.

Turns SNMP-discovery (and scan) signal into security events: rogue devices,
MAC moves, IP conflicts, new MACs. Read sources: discovered_endpoints,
mac_last_seen, ip_addresses.
"""
import json
import logging

from app.core.time import utcnow
from app.database import SessionLocal
from app.models.address import IPAddress
from app.models.network_device import DiscoveredEndpoint
from app.models.security import SecurityEvent, MacLastSeen

logger = logging.getLogger(__name__)

SEVERITY = {
    "ip_conflict":  "error",
    "rogue_device": "warning",
    "mac_move":     "warning",
    "new_mac":      "info",
}


def emit_security_event(db, event_type: str, *, mac: str | None, ip: str | None,
                        severity: str | None = None, details: dict | None = None) -> SecurityEvent:
    """Create or refresh (dedupe) an un-acknowledged event for (type, mac, ip)."""
    existing = (
        db.query(SecurityEvent)
        .filter_by(event_type=event_type, mac=mac, ip=ip, acknowledged=False)
        .first()
    )
    now = utcnow()
    if existing:
        existing.detected_at = now
        if details is not None:
            existing.details = json.dumps(details)
        return existing
    evt = SecurityEvent(
        event_type=event_type, severity=severity or SEVERITY.get(event_type, "warning"),
        mac=mac, ip=ip, details=json.dumps(details or {}), detected_at=now,
        acknowledged=False, quarantined=False,
    )
    db.add(evt)
    db.flush()  # so subsequent dedupe lookups see it (sessions may not autoflush)
    return evt


def detect_security(db) -> None:
    endpoints = db.query(DiscoveredEndpoint).all()
    addr_ips = {a.address for a in db.query(IPAddress.address).all()}
    last_seen = {m.mac: m for m in db.query(MacLastSeen).all()}
    now = utcnow()

    # per-MAC: new_mac / mac_move + upsert mac_last_seen
    for ep in endpoints:
        prev = last_seen.get(ep.mac)
        if prev is None:
            emit_security_event(db, "new_mac", mac=ep.mac, ip=ep.ip,
                                details={"port": ep.port_name, "device_id": ep.device_id})
            row = MacLastSeen(mac=ep.mac, device_id=ep.device_id, port_name=ep.port_name,
                              ip=ep.ip, last_seen=now)
            db.add(row)
            last_seen[ep.mac] = row
        else:
            if ep.port_name and prev.port_name and ep.port_name != prev.port_name:
                emit_security_event(db, "mac_move", mac=ep.mac, ip=ep.ip,
                                    details={"from_port": prev.port_name, "to_port": ep.port_name,
                                             "from_device": prev.device_id, "to_device": ep.device_id})
            prev.device_id, prev.port_name, prev.ip, prev.last_seen = ep.device_id, ep.port_name, ep.ip, now

    # ip_conflict: one IP, ≥2 distinct MACs
    by_ip: dict[str, set[str]] = {}
    for ep in endpoints:
        if ep.ip:
            by_ip.setdefault(ep.ip, set()).add(ep.mac)
    for ip, macs in by_ip.items():
        if len(macs) > 1:
            emit_security_event(db, "ip_conflict", mac=None, ip=ip,
                                details={"macs": sorted(macs)})

    # rogue_device: discovered IP with no IPAM record
    for ep in endpoints:
        if ep.ip and ep.ip not in addr_ips:
            emit_security_event(db, "rogue_device", mac=ep.mac, ip=ep.ip,
                                details={"port": ep.port_name, "device_id": ep.device_id, "source": "discovery"})

    db.commit()


def detect_security_bg() -> None:
    db = SessionLocal()
    try:
        detect_security(db)
    except Exception:
        logger.exception("detect_security_bg failed")
    finally:
        db.close()
