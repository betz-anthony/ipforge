from datetime import datetime, timedelta

from app.core.lifecycle import ip_timeline, ip_point_in_time
from app.core.audit import write_audit
from app.models.scan import DriftItem, AlertEvent, DriftCategory


def _audit(db, action, ip, after=None, before=None, ts=None):
    write_audit(db, "alice", action, "address", "1", ip, before=before, after=after)
    db.flush()
    # set timestamp on the most recent audit row for deterministic ordering
    from app.models.audit_log import AuditLog
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    if ts is not None:
        last.timestamp = ts
    db.commit()
    return last


def test_timeline_merges_sources(db):
    base = datetime(2026, 1, 1, 0, 0, 0)
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5", "status": "assigned", "hostname": "web"}, ts=base)
    db.add(DriftItem(ip_address="10.0.0.5", category=DriftCategory.missing_dns.value, severity="warning",
                     detected_at=base + timedelta(days=1), resolved=False))
    db.add(AlertEvent(event_type="went_unreachable", ip_address="10.0.0.5", subnet_id=1,
                      detected_at=base + timedelta(days=2)))
    db.commit()
    tl = ip_timeline(db, "10.0.0.5")
    kinds = [e["kind"] for e in tl]
    assert set(kinds) == {"change", "drift", "reachability"}
    # newest first
    assert tl[0]["kind"] == "reachability"


def test_point_in_time_reconstructs(db):
    base = datetime(2026, 1, 1)
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5", "status": "assigned", "hostname": "web01"}, ts=base)
    _audit(db, "update", "10.0.0.5", after={"address": "10.0.0.5", "status": "assigned", "hostname": "web02"},
           ts=base + timedelta(days=10))
    # between the two updates -> first snapshot
    snap = ip_point_in_time(db, "10.0.0.5", base + timedelta(days=5))
    assert snap["state"] == "allocated" and snap["hostname"] == "web01"
    # after the second -> updated snapshot
    snap2 = ip_point_in_time(db, "10.0.0.5", base + timedelta(days=20))
    assert snap2["hostname"] == "web02"


def test_point_in_time_after_delete_unallocated(db):
    base = datetime(2026, 1, 1)
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5", "status": "assigned"}, ts=base)
    _audit(db, "delete", "10.0.0.5", before={"address": "10.0.0.5"}, after=None, ts=base + timedelta(days=5))
    assert ip_point_in_time(db, "10.0.0.5", base + timedelta(days=10))["state"] == "unallocated"


def test_point_in_time_before_first_is_none(db):
    base = datetime(2026, 1, 1)
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5"}, ts=base)
    assert ip_point_in_time(db, "10.0.0.5", base - timedelta(days=1)) is None


def test_cross_address_row_history(db):
    base = datetime(2026, 1, 1)
    # IP created, deleted, recreated (different address rows, same IP/summary)
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5", "hostname": "old"}, ts=base)
    _audit(db, "delete", "10.0.0.5", before={"address": "10.0.0.5"}, ts=base + timedelta(days=1))
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5", "hostname": "new"}, ts=base + timedelta(days=2))
    tl = [e for e in ip_timeline(db, "10.0.0.5") if e["kind"] == "change"]
    assert len(tl) == 3
