"""DNS-DHCP-EDIT-001 P3 — PUT /api/v1/dhcp/scopes/{scope_id}/reservations/{ip}."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.cache import CachedDHCPLease, CachedDNSRecord
from app.models.audit_log import AuditLog


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_lease(db, **overrides):
    row = {
        "scope_id": "10.0.0.0", "ip_address": "10.0.0.5",
        "mac_address": "aa:bb:cc:dd:ee:ff", "client_duid": "", "iaid": 0,
        "name": "host01", "description": "", "source": "kea01",
        "synced_at": _utcnow(),
    }
    row.update(overrides)
    db.add(CachedDHCPLease(**row))
    db.commit()


OLD = {"scope_id": "10.0.0.0", "ip_address": "10.0.0.5",
       "mac_address": "aa:bb:cc:dd:ee:ff", "client_duid": "", "iaid": 0,
       "name": "host01", "description": ""}


def _put(client, old=None, new=None, source="kea01"):
    body = {"old": old or OLD, "new": new or {**OLD, "name": "host02"}}
    return client.request(
        "PUT", f"/api/v1/dhcp/scopes/10.0.0.0/reservations/10.0.0.5?source={source}",
        json=body,
    )


def _provider():
    p = MagicMock()
    p.source = "kea01"
    p.update_reservation = MagicMock()
    return p


def test_update_reservation_changes_name(client, db):
    _seed_lease(db)
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "host02"
    prov.update_reservation.assert_called_once()
    old_arg, new_arg = prov.update_reservation.call_args[0]
    assert old_arg.name == "host01" and new_arg.name == "host02"
    lease = db.query(CachedDHCPLease).filter_by(ip_address="10.0.0.5").first()
    assert lease.name == "host02"


def test_update_reservation_changes_mac(client, db):
    _seed_lease(db)
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "mac_address": "11:22:33:44:55:66"})
    assert r.status_code == 200, r.text
    lease = db.query(CachedDHCPLease).filter_by(ip_address="10.0.0.5").first()
    assert lease.mac_address == "11:22:33:44:55:66"


def test_update_reservation_rejects_ip_change(client, db):
    _seed_lease(db)
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "ip_address": "10.0.0.9"})
    assert r.status_code == 422
    prov.update_reservation.assert_not_called()


def test_update_reservation_unknown_404(client, db):
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 404
    prov.update_reservation.assert_not_called()


def test_update_reservation_provider_failure_leaves_cache_untouched(client, db):
    _seed_lease(db)
    prov = _provider()
    prov.update_reservation = MagicMock(side_effect=Exception("DHCP unreachable"))
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 502
    lease = db.query(CachedDHCPLease).filter_by(ip_address="10.0.0.5").first()
    assert lease.name == "host01"


def test_update_reservation_commit_failure_reverses_provider(client, db, monkeypatch):
    _seed_lease(db)
    prov = _provider()
    monkeypatch.setattr(db, "commit", MagicMock(side_effect=Exception("commit boom")))
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 502
    assert prov.update_reservation.call_count == 2
    first_call, second_call = prov.update_reservation.call_args_list
    assert first_call[0][0].name == "host01" and first_call[0][1].name == "host02"
    assert second_call[0][0].name == "host02" and second_call[0][1].name == "host01"


def test_update_reservation_audit_has_before_and_after(client, db):
    _seed_lease(db)
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    entry = db.query(AuditLog).filter_by(action="update", resource_type="dhcp_reservation").first()
    assert entry is not None
    assert entry.before_state is not None and "host01" in entry.before_state
    assert entry.after_state is not None and "host02" in entry.after_state


def test_update_reservation_dns_stale_true_when_linked_record_exists(client, db):
    _seed_lease(db)
    db.add(CachedDNSRecord(name="host01", record_type="A", value="10.0.0.5",
                           zone="example.com", ttl=3600, source="bind01", synced_at=_utcnow()))
    db.commit()
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    assert r.json()["dns_stale"] is True


def test_update_reservation_dns_stale_false_without_linked_record(client, db):
    _seed_lease(db)
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    assert r.json()["dns_stale"] is False


def test_update_reservation_dns_stale_false_when_name_unchanged(client, db):
    _seed_lease(db)
    db.add(CachedDNSRecord(name="host01", record_type="A", value="10.0.0.5",
                           zone="example.com", ttl=3600, source="bind01", synced_at=_utcnow()))
    db.commit()
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "description": "updated"})
    assert r.status_code == 200, r.text
    assert r.json()["dns_stale"] is False


def test_update_reservation_requires_operator(client_gr, db):
    _seed_lease(db)
    prov = _provider()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = _put(client_gr)
    assert r.status_code == 403
