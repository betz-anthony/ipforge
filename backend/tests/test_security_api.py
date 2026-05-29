from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.security import SecurityEvent
from app.core.time import utcnow
from app.core.custom_fields import load_tags


def _evt(db, event_type="rogue_device", ip="10.0.0.99", mac=None, sev="warning"):
    e = SecurityEvent(event_type=event_type, severity=sev, mac=mac, ip=ip,
                      details="{}", detected_at=utcnow(), acknowledged=False, quarantined=False)
    db.add(e)
    db.commit()
    return e


def test_list_and_filter(client, db):
    _evt(db, "rogue_device", ip="10.0.0.99")
    _evt(db, "ip_conflict", ip="10.0.0.5", sev="error")
    assert len(client.get("/api/security/events").json()) == 2
    only = client.get("/api/security/events", params={"event_type": "ip_conflict"}).json()
    assert [e["event_type"] for e in only] == ["ip_conflict"]


def test_acknowledge(client, db):
    e = _evt(db)
    assert client.post(f"/api/security/events/{e.id}/ack").status_code == 200
    db.refresh(e)
    assert e.acknowledged is True


def test_quarantine_imports_tags_sets_status(client, db):
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s); db.commit()
    e = _evt(db, ip="10.0.0.50")
    r = client.post(f"/api/security/events/{e.id}/quarantine")
    assert r.status_code == 200, r.text
    a = db.query(IPAddress).filter_by(address="10.0.0.50").first()
    assert a is not None and a.status == AddressStatus.deprecated
    assert "quarantined" in load_tags(db, "address", a.id)
    db.refresh(e)
    assert e.quarantined is True and e.acknowledged is True


def test_quarantine_existing_address(client, db):
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s); db.flush()
    a = IPAddress(address="10.0.0.50", subnet_id=s.id, status=AddressStatus.assigned)
    db.add(a); db.commit()
    e = _evt(db, ip="10.0.0.50")
    client.post(f"/api/security/events/{e.id}/quarantine")
    db.refresh(a)
    assert a.status == AddressStatus.deprecated


def test_quarantine_requires_operator(client_gr, db):
    e = _evt(db)
    assert client_gr.post(f"/api/security/events/{e.id}/quarantine").status_code == 403


def test_ack_requires_operator(client_gr, db):
    e = _evt(db)
    assert client_gr.post(f"/api/security/events/{e.id}/ack").status_code == 403
