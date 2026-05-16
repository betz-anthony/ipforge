import pytest
from datetime import datetime, timezone, timedelta
from app.models.address import IPAddress, AddressStatus
from app.models.subnet import Subnet
from app.config import settings as app_settings


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── autouse fixture: reset stale_reclaim_days between tests ──────────────────

@pytest.fixture(autouse=True)
def reset_stale_days():
    original = app_settings.stale_reclaim_days
    yield
    app_settings.stale_reclaim_days = original


# ── helpers ───────────────────────────────────────────────────────────────────

def _subnet(db, cidr="10.0.1.0/24", name="test"):
    s = Subnet(name=name, cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _ip(db, subnet_id, address, status=AddressStatus.assigned,
        last_seen_days_ago=None, dismissed_until=None):
    now = _utcnow()
    last_seen = (now - timedelta(days=last_seen_days_ago)) if last_seen_days_ago is not None else None
    a = IPAddress(
        address=address,
        subnet_id=subnet_id,
        status=status,
        last_seen=last_seen,
        reclaim_dismissed_until=dismissed_until,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ── column existence ──────────────────────────────────────────────────────────

def test_reclaim_dismissed_until_column_exists(db):
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", last_seen_days_ago=40)
    assert hasattr(a, "reclaim_dismissed_until")
    assert a.reclaim_dismissed_until is None


# ── settings ──────────────────────────────────────────────────────────────────

def test_settings_returns_stale_reclaim_days_default(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["stale_reclaim_days"] == 30


def test_settings_update_stale_reclaim_days(client):
    r = client.put("/api/settings", json={"stale_reclaim_days": 60})
    assert r.status_code == 200
    assert r.json()["stale_reclaim_days"] == 60


def test_settings_stale_reclaim_days_zero_allowed(client):
    r = client.put("/api/settings", json={"stale_reclaim_days": 0})
    assert r.status_code == 200
    assert r.json()["stale_reclaim_days"] == 0


# ── stale query logic ─────────────────────────────────────────────────────────

def test_stale_list_returns_qualifying_ips(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    r = client.get("/api/addresses/stale")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["address"] == "10.0.1.2"
    assert data[0]["days_stale"] >= 40


def test_stale_list_excludes_available_status(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.available, last_seen_days_ago=40)
    r = client.get("/api/addresses/stale")
    assert r.json() == []


def test_stale_list_excludes_discovered_status(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.discovered, last_seen_days_ago=40)
    r = client.get("/api/addresses/stale")
    assert r.json() == []


def test_stale_list_excludes_deprecated_status(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.deprecated, last_seen_days_ago=40)
    r = client.get("/api/addresses/stale")
    assert r.json() == []


def test_stale_list_excludes_null_last_seen(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=None)
    r = client.get("/api/addresses/stale")
    assert r.json() == []


def test_stale_list_excludes_recently_seen(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=10)
    r = client.get("/api/addresses/stale")
    assert r.json() == []


def test_stale_list_excludes_active_dismissal(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    future = now + timedelta(days=10)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned,
        last_seen_days_ago=40, dismissed_until=future)
    r = client.get("/api/addresses/stale")
    assert r.json() == []


def test_stale_list_includes_expired_dismissal(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    past = now - timedelta(days=5)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned,
        last_seen_days_ago=40, dismissed_until=past)
    r = client.get("/api/addresses/stale")
    assert len(r.json()) == 1


def test_stale_list_disabled_when_zero(client, db):
    app_settings.stale_reclaim_days = 0
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=400)
    r = client.get("/api/addresses/stale")
    assert r.json() == []


def test_stale_list_filter_by_subnet(client, db):
    app_settings.stale_reclaim_days = 30
    s1 = _subnet(db, cidr="10.0.1.0/24", name="s1")
    s2 = _subnet(db, cidr="10.0.2.0/24", name="s2")
    _ip(db, s1.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    _ip(db, s2.id, "10.0.2.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    r = client.get(f"/api/addresses/stale?subnet_id={s1.id}")
    data = r.json()
    assert len(data) == 1
    assert data[0]["address"] == "10.0.1.2"


def test_stale_list_reserved_status_included(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.reserved, last_seen_days_ago=40)
    r = client.get("/api/addresses/stale")
    assert len(r.json()) == 1


def test_stale_list_response_fields(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    item = client.get("/api/addresses/stale").json()[0]
    for field in ("id", "address", "subnet_id", "subnet_cidr", "hostname",
                  "status", "mac_address", "last_seen", "days_stale"):
        assert field in item, f"missing field: {field}"
    assert item["subnet_cidr"] == s.cidr


# ── count endpoint ────────────────────────────────────────────────────────────

def test_stale_count_returns_correct_number(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    _ip(db, s.id, "10.0.1.3", status=AddressStatus.assigned, last_seen_days_ago=40)
    _ip(db, s.id, "10.0.1.4", status=AddressStatus.assigned, last_seen_days_ago=5)
    r = client.get("/api/addresses/stale/count")
    assert r.status_code == 200
    assert r.json() == {"count": 2}


def test_stale_count_zero_when_disabled(client, db):
    app_settings.stale_reclaim_days = 0
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=400)
    r = client.get("/api/addresses/stale/count")
    assert r.json() == {"count": 0}


# ── reclaim action endpoint ───────────────────────────────────────────────────

def test_reclaim_deprecate_sets_status(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    r = client.put(f"/api/addresses/{a.id}/reclaim", json={"action": "deprecate"})
    assert r.status_code == 200
    db.refresh(a)
    assert a.status == AddressStatus.deprecated


def test_reclaim_deprecate_creates_audit_log(client, db):
    from app.models.audit_log import AuditLog
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    client.put(f"/api/addresses/{a.id}/reclaim", json={"action": "deprecate"})
    log = db.query(AuditLog).filter_by(resource_type="address").first()
    assert log is not None
    assert log.action == "update"
    assert "deprecate" in (log.summary or "")


def test_reclaim_extend_sets_dismissed_until_90d(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    r = client.put(f"/api/addresses/{a.id}/reclaim", json={"action": "extend"})
    assert r.status_code == 200
    db.refresh(a)
    assert a.reclaim_dismissed_until is not None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = a.reclaim_dismissed_until - now
    assert 88 <= delta.days <= 91


def test_reclaim_dismiss_sets_far_future(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    r = client.put(f"/api/addresses/{a.id}/reclaim", json={"action": "dismiss"})
    assert r.status_code == 200
    db.refresh(a)
    assert a.reclaim_dismissed_until is not None
    assert a.reclaim_dismissed_until.year == 9999


def test_reclaim_action_404_for_missing_address(client):
    r = client.put("/api/addresses/9999/reclaim", json={"action": "deprecate"})
    assert r.status_code == 404


def test_reclaim_action_invalid_action(client, db):
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    r = client.put(f"/api/addresses/{a.id}/reclaim", json={"action": "invalid"})
    assert r.status_code == 422


def test_reclaim_dismissed_ip_excluded_from_stale(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    client.put(f"/api/addresses/{a.id}/reclaim", json={"action": "dismiss"})
    assert client.get("/api/addresses/stale").json() == []


def test_reclaim_extend_ip_excluded_from_stale(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    client.put(f"/api/addresses/{a.id}/reclaim", json={"action": "extend"})
    assert client.get("/api/addresses/stale").json() == []


# ── bulk deprecate endpoint ───────────────────────────────────────────────────

def test_bulk_deprecate_depreciates_stale_in_subnet(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    a1 = _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    a2 = _ip(db, s.id, "10.0.1.3", status=AddressStatus.reserved, last_seen_days_ago=40)
    r = client.post("/api/addresses/stale/bulk-deprecate", json={"subnet_id": s.id})
    assert r.status_code == 200
    assert r.json()["deprecated"] == 2
    db.refresh(a1); db.refresh(a2)
    assert a1.status == AddressStatus.deprecated
    assert a2.status == AddressStatus.deprecated


def test_bulk_deprecate_skips_non_stale(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned, last_seen_days_ago=40)
    a_fresh = _ip(db, s.id, "10.0.1.3", status=AddressStatus.assigned, last_seen_days_ago=5)
    r = client.post("/api/addresses/stale/bulk-deprecate", json={"subnet_id": s.id})
    assert r.json()["deprecated"] == 1
    db.refresh(a_fresh)
    assert a_fresh.status == AddressStatus.assigned


def test_bulk_deprecate_skips_dismissed(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    future = now + timedelta(days=10)
    _ip(db, s.id, "10.0.1.2", status=AddressStatus.assigned,
        last_seen_days_ago=40, dismissed_until=future)
    r = client.post("/api/addresses/stale/bulk-deprecate", json={"subnet_id": s.id})
    assert r.json()["deprecated"] == 0


def test_bulk_deprecate_returns_zero_when_nothing_stale(client, db):
    app_settings.stale_reclaim_days = 30
    s = _subnet(db)
    r = client.post("/api/addresses/stale/bulk-deprecate", json={"subnet_id": s.id})
    assert r.status_code == 200
    assert r.json()["deprecated"] == 0
