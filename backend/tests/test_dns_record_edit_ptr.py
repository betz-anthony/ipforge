"""DNS-DHCP-EDIT-001 P2 — update_ptr=true PTR follow-through on record edit."""
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


def _seed_ptr(db, name, zone, value="web01.", source="bind01"):
    db.add(CRow(name=name, record_type="PTR", value=value, zone=zone,
                ttl=3600, source=source, synced_at=_utcnow()))
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
    p.delete_record = MagicMock()
    p.add_record = MagicMock()
    p.supports_ptr = True
    return p


def test_update_ptr_same_reverse_zone_updates_ptr(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    _seed_record(db)
    _seed_ptr(db, "5", "1.0.10.in-addr.arpa")
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, update_ptr=True)
    assert r.status_code == 200, r.text
    assert prov.update_record.call_count == 2  # forward + ptr
    ptr_old, ptr_new = prov.update_record.call_args_list[1][0]
    assert ptr_old.record_type == "PTR" and ptr_old.name == "5"
    assert ptr_new.record_type == "PTR" and ptr_new.name == "9"
    prov.delete_record.assert_not_called()
    prov.add_record.assert_not_called()
    ptr_row = db.query(CRow).filter_by(record_type="PTR", zone="1.0.10.in-addr.arpa").first()
    assert ptr_row.name == "9"


def test_update_ptr_different_reverse_zone_recreates(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    _add_zone(db, "2.0.10.in-addr.arpa")
    _seed_record(db)
    _seed_ptr(db, "5", "1.0.10.in-addr.arpa")
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "value": "10.0.2.9"}, update_ptr=True)
    assert r.status_code == 200, r.text
    prov.delete_record.assert_called_once()
    prov.add_record.assert_called_once()
    deleted = prov.delete_record.call_args[0][0]
    added = prov.add_record.call_args[0][0]
    assert deleted.zone == "1.0.10.in-addr.arpa"
    assert added.zone == "2.0.10.in-addr.arpa"
    assert db.query(CRow).filter_by(record_type="PTR", zone="1.0.10.in-addr.arpa").first() is None
    new_ptr_row = db.query(CRow).filter_by(record_type="PTR", zone="2.0.10.in-addr.arpa").first()
    assert new_ptr_row is not None and new_ptr_row.name == "9"


def test_update_ptr_new_reverse_zone_appears(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "2.0.10.in-addr.arpa")  # only the NEW value's reverse zone is cached
    _seed_record(db)
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "value": "10.0.2.9"}, update_ptr=True)
    assert r.status_code == 200, r.text
    prov.add_record.assert_called_once()
    prov.delete_record.assert_not_called()
    added = prov.add_record.call_args[0][0]
    assert added.zone == "2.0.10.in-addr.arpa" and added.record_type == "PTR"
    new_ptr_row = db.query(CRow).filter_by(record_type="PTR", zone="2.0.10.in-addr.arpa").first()
    assert new_ptr_row is not None


def test_update_ptr_old_reverse_zone_disappears(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")  # only the OLD value's reverse zone is cached
    _seed_record(db)
    _seed_ptr(db, "5", "1.0.10.in-addr.arpa")
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "value": "10.0.2.9"}, update_ptr=True)
    assert r.status_code == 200, r.text
    prov.delete_record.assert_called_once()
    prov.add_record.assert_not_called()
    deleted = prov.delete_record.call_args[0][0]
    assert deleted.zone == "1.0.10.in-addr.arpa"
    assert db.query(CRow).filter_by(record_type="PTR").first() is None


def test_update_ptr_reconciliation_failure_reverses_forward(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    _seed_record(db)
    _seed_ptr(db, "5", "1.0.10.in-addr.arpa")
    prov = _provider()
    prov.update_record = MagicMock(side_effect=[None, Exception("ptr update failed"), None])
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, update_ptr=True)
    assert r.status_code == 502
    assert prov.update_record.call_count == 3  # forward, ptr (fails), forward-reversal
    reversal = prov.update_record.call_args_list[2][0]
    assert reversal[0].value == "10.0.1.9" and reversal[1].value == "10.0.1.5"
    row = db.query(CRow).filter_by(name="web01", record_type="A").first()
    assert row.value == "10.0.1.5"  # forward cache untouched


def test_update_ptr_cache_commit_failure_reverses_both(client, db, monkeypatch):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    _add_zone(db, "2.0.10.in-addr.arpa")
    _seed_record(db)
    _seed_ptr(db, "5", "1.0.10.in-addr.arpa")
    prov = _provider()
    monkeypatch.setattr(db, "commit", MagicMock(side_effect=Exception("commit boom")))
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, new={**OLD, "value": "10.0.2.9"}, update_ptr=True)
    assert r.status_code == 502
    # forward reversed
    assert prov.update_record.call_count == 2
    reversal = prov.update_record.call_args_list[1][0]
    assert reversal[0].value == "10.0.2.9" and reversal[1].value == "10.0.1.5"
    # ptr recreate (delete old / add new) reversed: delete new / add old
    assert prov.delete_record.call_count == 2
    assert prov.add_record.call_count == 2
    assert prov.delete_record.call_args_list[1][0][0].zone == "2.0.10.in-addr.arpa"
    assert prov.add_record.call_args_list[1][0][0].zone == "1.0.10.in-addr.arpa"


def test_update_ptr_rejected_for_non_address_record(client, db):
    _add_zone(db, "example.com")
    _seed_record(db, name="txt01", record_type="TXT", value="hello")
    prov = _provider()
    old = {"name": "txt01", "record_type": "TXT", "value": "hello",
           "zone": "example.com", "ttl": 3600, "source": "bind01"}
    new = {**old, "value": "goodbye"}
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, old=old, new=new, update_ptr=True)
    assert r.status_code == 400
    prov.update_record.assert_not_called()


def test_update_ptr_rejected_when_provider_lacks_ptr_support(client, db):
    _add_zone(db, "example.com", source="pihole01")
    _seed_record(db, source="pihole01")
    prov = _provider()
    prov.source = "pihole01"
    prov.supports_ptr = False
    old = {**OLD, "source": "pihole01"}
    new = {**old, "value": "10.0.1.9"}
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, old=old, new=new, update_ptr=True)
    assert r.status_code == 400
    prov.update_record.assert_not_called()
