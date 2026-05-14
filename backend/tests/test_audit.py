import json
from app.models.audit_log import AuditLog
from app.core.audit import write_audit


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
