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
    data = r.json()["items"]
    assert len(data) == 2
    assert data[0]["username"] in ("alice", "bob")


def test_audit_filter_by_resource_type(client, db):
    write_audit(db, "alice", "create", "subnet",  "1", "10.0.0.0/24")
    write_audit(db, "alice", "create", "address", "2", "10.0.0.1")
    db.commit()
    r = client.get("/api/audit?resource_type=subnet")
    data = r.json()["items"]
    assert len(data) == 1
    assert data[0]["resource_type"] == "subnet"


def test_audit_filter_by_username(client, db):
    write_audit(db, "alice", "create", "subnet", "1", "10.0.0.0/24")
    write_audit(db, "bob",   "create", "subnet", "2", "10.1.0.0/24")
    db.commit()
    r = client.get("/api/audit?username=alice")
    data = r.json()["items"]
    assert len(data) == 1
    assert data[0]["username"] == "alice"


def test_audit_limit(client, db):
    for i in range(10):
        write_audit(db, "alice", "create", "subnet", str(i), f"10.{i}.0.0/24")
    db.commit()
    r = client.get("/api/audit?limit=3")
    assert len(r.json()["items"]) == 3


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
    data = r.json()["items"]
    assert data[0]["summary"] == "new"
    assert data[1]["summary"] == "old"


# ── Keyset pagination ─────────────────────────────────────────────────────


def test_audit_list_returns_cursor_envelope(client, db):
    write_audit(db, "alice", "create", "subnet", "1", "10.0.0.0/24", after={"id": 1})
    db.commit()
    r = client.get("/api/audit")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "next_cursor" in body
    assert "limit" in body


def test_audit_keyset_no_duplicates_no_gaps(client, db):
    from datetime import datetime, timezone, timedelta
    base = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(7):
        ts = base + timedelta(seconds=i)
        db.add(AuditLog(timestamp=ts, username="u", action="create",
                        resource_type="subnet", resource_id=str(i), summary=f"s{i}"))
    db.commit()

    page1 = client.get("/api/audit?limit=3").json()
    assert len(page1["items"]) == 3
    assert page1["next_cursor"] is not None

    page2 = client.get(f"/api/audit?limit=3&cursor={page1['next_cursor']}").json()
    assert len(page2["items"]) == 3
    assert page2["next_cursor"] is not None

    page3 = client.get(f"/api/audit?limit=3&cursor={page2['next_cursor']}").json()
    assert len(page3["items"]) == 1
    assert page3["next_cursor"] is None

    all_ids = (
        [e["id"] for e in page1["items"]] +
        [e["id"] for e in page2["items"]] +
        [e["id"] for e in page3["items"]]
    )
    assert len(all_ids) == len(set(all_ids)), "duplicate IDs across pages"
    assert len(all_ids) == 7, "missing entries across pages"


def test_audit_keyset_null_cursor_on_last_page(client, db):
    write_audit(db, "a", "create", "subnet", "1", "x")
    db.commit()
    body = client.get("/api/audit?limit=50").json()
    assert body["next_cursor"] is None


def test_audit_keyset_filters_still_apply(client, db):
    write_audit(db, "alice", "create", "subnet", "1", "x")
    write_audit(db, "bob", "create", "subnet", "2", "y")
    db.commit()
    body = client.get("/api/audit?username=alice").json()
    assert len(body["items"]) == 1
    assert body["items"][0]["username"] == "alice"
