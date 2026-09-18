"""PUT /api/v1/dhcp/scopes/{scope_id}/reserved-sync — opt a scope out of the
Reserved Ranges auto-sync without touching its lease/pool syncing."""
from datetime import datetime, timezone

from app.models.cache import CachedDHCPScope
from app.models.dhcp_scope_override import DHCPScopeReservedSyncExclusion
from app.models.audit_log import AuditLog


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_scope(db, **overrides):
    row = {
        "scope_id": "10.10.0.0", "name": "test-monitor", "subnet_mask": "/22",
        "start_range": "10.10.0.31", "end_range": "10.10.3.254",
        "description": "", "active": True, "ip_version": 4,
        "source": "dhcp1-t", "synced_at": _utcnow(),
    }
    row.update(overrides)
    db.add(CachedDHCPScope(**row))
    db.commit()


def test_list_scopes_defaults_sync_reserved_ranges_true(client, db):
    _seed_scope(db)
    r = client.get("/api/v1/dhcp/scopes")
    assert r.status_code == 200, r.text
    scope = next(s for s in r.json() if s["scope_id"] == "10.10.0.0")
    assert scope["sync_reserved_ranges"] is True


def test_disable_reserved_sync_creates_exclusion_row(client, db):
    _seed_scope(db)
    r = client.request(
        "PUT", "/api/v1/dhcp/scopes/10.10.0.0/reserved-sync?source=dhcp1-t",
        json={"enabled": False},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"source": "dhcp1-t", "scope_id": "10.10.0.0", "sync_reserved_ranges": False}

    row = db.query(DHCPScopeReservedSyncExclusion).filter_by(source="dhcp1-t", scope_id="10.10.0.0").first()
    assert row is not None

    audit = db.query(AuditLog).filter_by(resource_type="dhcp_scope_reserved_sync").first()
    assert audit is not None
    assert "disabled" in audit.summary


def test_list_scopes_reflects_disabled_exclusion(client, db):
    _seed_scope(db)
    db.add(DHCPScopeReservedSyncExclusion(source="dhcp1-t", scope_id="10.10.0.0"))
    db.commit()

    r = client.get("/api/v1/dhcp/scopes")
    scope = next(s for s in r.json() if s["scope_id"] == "10.10.0.0")
    assert scope["sync_reserved_ranges"] is False


def test_reenable_reserved_sync_removes_exclusion_row(client, db):
    _seed_scope(db)
    db.add(DHCPScopeReservedSyncExclusion(source="dhcp1-t", scope_id="10.10.0.0"))
    db.commit()

    r = client.request(
        "PUT", "/api/v1/dhcp/scopes/10.10.0.0/reserved-sync?source=dhcp1-t",
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sync_reserved_ranges"] is True

    row = db.query(DHCPScopeReservedSyncExclusion).filter_by(source="dhcp1-t", scope_id="10.10.0.0").first()
    assert row is None


def test_disable_is_idempotent(client, db):
    _seed_scope(db)
    r1 = client.request(
        "PUT", "/api/v1/dhcp/scopes/10.10.0.0/reserved-sync?source=dhcp1-t",
        json={"enabled": False},
    )
    r2 = client.request(
        "PUT", "/api/v1/dhcp/scopes/10.10.0.0/reserved-sync?source=dhcp1-t",
        json={"enabled": False},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    rows = db.query(DHCPScopeReservedSyncExclusion).filter_by(source="dhcp1-t", scope_id="10.10.0.0").all()
    assert len(rows) == 1


def test_toggle_distinguishes_by_source_same_scope_id(client, db):
    """Two different providers can use the same scope_id string — an
    exclusion set for one must not affect the other."""
    _seed_scope(db, source="dhcp1-t")
    _seed_scope(db, source="dhcpdc-p")

    client.request(
        "PUT", "/api/v1/dhcp/scopes/10.10.0.0/reserved-sync?source=dhcp1-t",
        json={"enabled": False},
    )

    r = client.get("/api/v1/dhcp/scopes")
    by_source = {s["source"]: s["sync_reserved_ranges"] for s in r.json()}
    assert by_source["dhcp1-t"] is False
    assert by_source["dhcpdc-p"] is True


def test_requester_role_cannot_toggle_reserved_sync(client_requester, db):
    _seed_scope(db)
    r = client_requester.request(
        "PUT", "/api/v1/dhcp/scopes/10.10.0.0/reserved-sync?source=dhcp1-t",
        json={"enabled": False},
    )
    assert r.status_code == 403
