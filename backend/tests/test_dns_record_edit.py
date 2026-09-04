"""DNS-DHCP-EDIT-001 P1 — PUT /api/v1/dns/zones/{zone}/records (DNS edit, no PTR follow)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.cache import CachedDNSZone, CachedDNSRecord as CRow


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _add_zone(db, zone, source="bind01"):
    db.add(CachedDNSZone(zone=zone, source=source, synced_at=_utcnow()))
    db.commit()


def _seed_record(db, **overrides):
    row = {
        "name": "web01", "record_type": "A", "value": "10.0.1.5",
        "zone": "example.com", "ttl": 3600, "source": "bind01",
        "synced_at": _utcnow(),
    }
    row.update(overrides)
    db.add(CRow(**row))
    db.commit()


OLD = {"name": "web01", "record_type": "A", "value": "10.0.1.5",
       "zone": "example.com", "ttl": 3600, "source": "bind01"}


def _put(client, old=None, new=None, **extra):
    body = {"old": old or OLD, "new": new or {**OLD, "value": "10.0.1.9"}, **extra}
    return client.request("PUT", "/api/v1/dns/zones/example.com/records", json=body)


def _provider():
    p = MagicMock()
    p.source = "bind01"
    p.update_record = MagicMock()
    p.supports_ptr = True
    return p


def test_update_record_changes_value(client, db):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    assert r.json()["value"] == "10.0.1.9"
    prov.update_record.assert_called_once()
    old_arg, new_arg = prov.update_record.call_args[0]
    assert old_arg.value == "10.0.1.5"
    assert new_arg.value == "10.0.1.9"
    row = db.query(CRow).filter_by(name="web01", record_type="A", zone="example.com").first()
    assert row.value == "10.0.1.9"


def test_update_record_changes_ttl(client, db):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "ttl": 60})
    assert r.status_code == 200, r.text
    row = db.query(CRow).filter_by(name="web01", record_type="A", zone="example.com").first()
    assert row.ttl == 60


def test_update_record_rejects_zone_change(client, db):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "zone": "other.com", "value": "10.0.1.9"})
    assert r.status_code == 422
    prov.update_record.assert_not_called()


def test_update_record_rejects_source_change(client, db):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "source": "other-prov", "value": "10.0.1.9"})
    assert r.status_code == 422
    prov.update_record.assert_not_called()


def test_update_record_unknown_record_404(client, db):
    _add_zone(db, "example.com")
    # no cache row seeded
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 404
    prov.update_record.assert_not_called()


def test_update_record_provider_failure_leaves_cache_untouched(client, db):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    prov.update_record = MagicMock(side_effect=Exception("DNS unreachable"))
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 502
    row = db.query(CRow).filter_by(name="web01", record_type="A", zone="example.com").first()
    assert row.value == "10.0.1.5"  # untouched


def test_update_record_commit_failure_reverses_provider(client, db, monkeypatch):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    monkeypatch.setattr(db, "commit", MagicMock(side_effect=Exception("commit boom")))
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 502
    assert prov.update_record.call_count == 2
    first_call, second_call = prov.update_record.call_args_list
    # forward: old -> new, then reversal: new -> old
    assert first_call[0][0].value == "10.0.1.5" and first_call[0][1].value == "10.0.1.9"
    assert second_call[0][0].value == "10.0.1.9" and second_call[0][1].value == "10.0.1.5"


def test_update_record_audit_has_before_and_after(client, db):
    from app.models.audit_log import AuditLog
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    entry = db.query(AuditLog).filter_by(action="update", resource_type="dns_record").first()
    assert entry is not None
    assert entry.before_state is not None and "10.0.1.5" in entry.before_state
    assert entry.after_state is not None and "10.0.1.9" in entry.after_state


def test_update_record_ptr_stale_true_when_reverse_zone_exists(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    assert r.json()["ptr_stale"] is True


def test_update_record_ptr_stale_false_without_reverse_zone(client, db):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client)
    assert r.status_code == 200, r.text
    assert r.json()["ptr_stale"] is False


def test_update_record_ptr_stale_false_for_non_address_record(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    _seed_record(db, name="txt01", record_type="TXT", value="hello", ttl=3600)
    prov = _provider()
    old = {"name": "txt01", "record_type": "TXT", "value": "hello", "zone": "example.com",
           "ttl": 3600, "source": "bind01"}
    new = {**old, "value": "goodbye"}
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, old=old, new=new)
    assert r.status_code == 200, r.text
    assert r.json()["ptr_stale"] is False


def test_update_record_ptr_stale_false_when_provider_lacks_ptr_support(client, db):
    _add_zone(db, "example.com", source="pihole01")
    _add_zone(db, "1.0.10.in-addr.arpa", source="pihole01")
    _seed_record(db, source="pihole01")
    prov = _provider()
    prov.source = "pihole01"
    prov.supports_ptr = False
    old = {**OLD, "source": "pihole01"}
    new = {**old, "value": "10.0.1.9"}
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, old=old, new=new)
    assert r.status_code == 200, r.text
    assert r.json()["ptr_stale"] is False


def test_update_record_requires_operator(client_gr, db):
    _add_zone(db, "example.com")
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client_gr)
    assert r.status_code == 403
