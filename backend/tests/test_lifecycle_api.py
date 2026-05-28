from datetime import datetime, timedelta

from app.core.audit import write_audit
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.audit_log import AuditLog


def _seed(db):
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web")
    db.add(a)
    db.commit()
    return s, a


def _audit(db, action, ip, after=None, ts=None):
    write_audit(db, "alice", action, "address", "1", ip, after=after)
    db.flush()
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    if ts:
        last.timestamp = ts
    db.commit()


def test_history_by_id(client, db):
    s, a = _seed(db)
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5", "hostname": "web"}, ts=datetime(2026, 1, 1))
    r = client.get(f"/api/addresses/{a.id}/history")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ip"] == "10.0.0.5"
    assert any(e["kind"] == "change" for e in body["timeline"])


def test_history_by_ip_point_in_time(client, db):
    _seed(db)
    _audit(db, "create", "10.0.0.5", after={"address": "10.0.0.5", "hostname": "web01"}, ts=datetime(2026, 1, 1))
    _audit(db, "update", "10.0.0.5", after={"address": "10.0.0.5", "hostname": "web02"}, ts=datetime(2026, 1, 10))
    r = client.get("/api/addresses/by-ip/10.0.0.5/history", params={"as_of": "2026-01-05"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["point_in_time"]["hostname"] == "web01"
    assert body["point_in_time"]["state"] == "allocated"


def test_history_by_ip_untracked(client, db):
    # IP never in IPAM but has audit history (e.g. deleted long ago)
    _audit(db, "create", "192.0.2.9", after={"address": "192.0.2.9"}, ts=datetime(2026, 1, 1))
    r = client.get("/api/addresses/by-ip/192.0.2.9/history")
    assert r.status_code == 200
    assert any(e["kind"] == "change" for e in r.json()["timeline"])
