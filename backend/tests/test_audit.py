import json
from app.models.audit_log import AuditLog
from app.core.audit import write_audit
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus


def test_write_audit_create(db):
    write_audit(db, "alice", "create", "subnet", "42", "10.0.0.0/24 (corp)",
                after={"id": 42, "cidr": "10.0.0.0/24"})
    db.commit()
    entry = db.query(AuditLog).first()
    assert entry is not None
    assert entry.username == "alice"
    assert entry.action == "create"
    assert entry.resource_type == "subnet"
    assert entry.resource_id == "42"
    assert entry.summary == "10.0.0.0/24 (corp)"
    assert entry.before_state is None
    assert json.loads(entry.after_state) == {"id": 42, "cidr": "10.0.0.0/24"}


def test_write_audit_update_captures_before_after(db):
    write_audit(db, "bob", "update", "address", "7", "10.0.0.1",
                before={"status": "available"}, after={"status": "assigned"})
    db.commit()
    entry = db.query(AuditLog).first()
    assert entry.action == "update"
    assert json.loads(entry.before_state)["status"] == "available"
    assert json.loads(entry.after_state)["status"] == "assigned"


def test_write_audit_delete_has_no_after(db):
    write_audit(db, "carol", "delete", "dns_record", "web.corp.com/A", "web.corp.com A 10.0.0.1",
                before={"name": "web.corp.com", "record_type": "A", "value": "10.0.0.1"})
    db.commit()
    entry = db.query(AuditLog).first()
    assert entry.action == "delete"
    assert entry.after_state is None
    assert json.loads(entry.before_state)["name"] == "web.corp.com"


# ── Subnet audit ──────────────────────────────────────────────────────────


def test_create_subnet_writes_audit(client, db):
    r = client.post("/api/subnets", json={"name": "Corp", "cidr": "10.0.0.0/24", "description": None, "vlan_id": None, "notes": None})
    assert r.status_code == 201
    entries = db.query(AuditLog).all()
    assert len(entries) == 1
    e = entries[0]
    assert e.action == "create"
    assert e.resource_type == "subnet"
    assert e.username == "test_admin"
    assert json.loads(e.after_state)["cidr"] == "10.0.0.0/24"
    assert e.before_state is None


def test_update_subnet_writes_audit_with_before_after(client, db):
    db.add(Subnet(name="Old", cidr="10.1.0.0/24", ip_version=4))
    db.commit()
    sid = db.query(Subnet).first().id
    client.put(f"/api/subnets/{sid}", json={"name": "New"})
    e = db.query(AuditLog).first()
    assert e.action == "update"
    assert json.loads(e.before_state)["name"] == "Old"
    assert json.loads(e.after_state)["name"] == "New"


def test_delete_subnet_writes_audit(client, db):
    db.add(Subnet(name="Gone", cidr="10.2.0.0/24", ip_version=4))
    db.commit()
    sid = db.query(Subnet).first().id
    client.delete(f"/api/subnets/{sid}")
    e = db.query(AuditLog).first()
    assert e.action == "delete"
    assert json.loads(e.before_state)["cidr"] == "10.2.0.0/24"
    assert e.after_state is None


# ── Address audit ─────────────────────────────────────────────────────────


def test_create_address_writes_audit(client, db):
    subnet = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(subnet)
    db.commit()
    r = client.post("/api/addresses", json={
        "address": "10.0.0.1", "subnet_id": subnet.id,
        "status": "assigned", "hostname": None, "mac_address": None,
        "description": None, "notes": None,
    })
    assert r.status_code == 201
    e = db.query(AuditLog).first()
    assert e.action == "create"
    assert e.resource_type == "address"
    assert e.username == "test_admin"
    assert json.loads(e.after_state)["address"] == "10.0.0.1"
    assert e.before_state is None


def test_update_address_writes_audit(client, db):
    subnet = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(subnet)
    db.flush()
    addr = IPAddress(address="10.0.0.2", subnet_id=subnet.id, status=AddressStatus.available)
    db.add(addr)
    db.commit()
    client.put(f"/api/addresses/{addr.id}", json={"status": "assigned"})
    e = db.query(AuditLog).first()
    assert e.action == "update"
    assert json.loads(e.before_state)["status"] == "available"
    assert json.loads(e.after_state)["status"] == "assigned"


def test_delete_address_writes_audit(client, db):
    subnet = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(subnet)
    db.flush()
    addr = IPAddress(address="10.0.0.3", subnet_id=subnet.id, status=AddressStatus.available)
    db.add(addr)
    db.commit()
    client.delete(f"/api/addresses/{addr.id}")
    e = db.query(AuditLog).first()
    assert e.action == "delete"
    assert e.resource_type == "address"
    assert json.loads(e.before_state)["address"] == "10.0.0.3"
    assert e.after_state is None


# ── Audit API endpoint ────────────────────────────────────────────────────


def test_audit_list_returns_entries(client, db):
    write_audit(db, "alice", "create", "subnet", "1", "10.0.0.0/24", after={"id": 1})
    write_audit(db, "bob",   "delete", "address", "5", "10.0.0.1",   before={"id": 5})
    db.commit()
    r = client.get("/api/audit")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["username"] in ("alice", "bob")


def test_audit_filter_by_resource_type(client, db):
    write_audit(db, "alice", "create", "subnet",  "1", "10.0.0.0/24")
    write_audit(db, "alice", "create", "address", "2", "10.0.0.1")
    db.commit()
    r = client.get("/api/audit?resource_type=subnet")
    data = r.json()
    assert len(data) == 1
    assert data[0]["resource_type"] == "subnet"


def test_audit_filter_by_username(client, db):
    write_audit(db, "alice", "create", "subnet", "1", "10.0.0.0/24")
    write_audit(db, "bob",   "create", "subnet", "2", "10.1.0.0/24")
    db.commit()
    r = client.get("/api/audit?username=alice")
    data = r.json()
    assert len(data) == 1
    assert data[0]["username"] == "alice"


def test_audit_limit(client, db):
    for i in range(10):
        write_audit(db, "alice", "create", "subnet", str(i), f"10.{i}.0.0/24")
    db.commit()
    r = client.get("/api/audit?limit=3")
    assert len(r.json()) == 3


def test_audit_ordered_newest_first(client, db):
    from datetime import datetime, timezone, timedelta
    t1 = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    t2 = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(AuditLog(timestamp=t1, username="a", action="create", resource_type="subnet",
                    resource_id="1", summary="old"))
    db.add(AuditLog(timestamp=t2, username="a", action="create", resource_type="subnet",
                    resource_id="2", summary="new"))
    db.commit()
    r = client.get("/api/audit")
    data = r.json()
    assert data[0]["summary"] == "new"
    assert data[1]["summary"] == "old"
