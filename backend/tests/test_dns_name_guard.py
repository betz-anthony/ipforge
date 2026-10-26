"""DNSNAME-001 — block record names that repeat their own zone."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.cache import CachedDNSZone, CachedDNSRecord as CRow


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _provider():
    p = MagicMock()
    p.source = "bind01"
    p.supports_ptr = False
    return p


def _create(client, name, **extra):
    return client.post("/api/v1/dns/zones/example.com/records", json={
        "name": name, "record_type": "A", "value": "10.0.1.5",
        "ttl": 3600, "source": "bind01", **extra,
    })


# ── create / update guard ────────────────────────────────────────────────────

def test_create_blocks_name_ending_in_zone(client, db):
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _create(client, "web01.example.com")
    assert r.status_code == 422, r.text
    assert "web01" in r.json()["detail"]
    prov.add_record.assert_not_called()


def test_create_allows_override(client, db):
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _create(client, "web01.example.com", allow_zone_suffix=True)
    assert r.status_code == 201, r.text
    prov.add_record.assert_called_once()
    assert prov.add_record.call_args[0][0].name == "web01.example.com"


def test_create_trailing_dot_name_is_absolute_and_allowed(client, db):
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _create(client, "web01.example.com.")
    assert r.status_code == 201, r.text


def test_create_short_name_unaffected(client, db):
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _create(client, "web01")
    assert r.status_code == 201, r.text


def _seed(db, name):
    db.add(CachedDNSZone(zone="example.com", source="bind01", synced_at=_utcnow()))
    db.add(CRow(name=name, record_type="A", value="10.0.1.5", zone="example.com",
                ttl=3600, source="bind01", synced_at=_utcnow()))
    db.commit()


def _old(name):
    return {"name": name, "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01"}


def _put(client, old, new, **extra):
    return client.request("PUT", "/api/v1/dns/zones/example.com/records",
                          json={"old": old, "new": new, **extra})


def test_update_blocks_rename_into_zone_suffix(client, db):
    _seed(db, "web01")
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, _old("web01"), _old("web01.example.com"))
    assert r.status_code == 422, r.text
    prov.update_record.assert_not_called()


def test_update_allows_override(client, db):
    _seed(db, "web01")
    prov = _provider()
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, _old("web01"), _old("web01.example.com"), allow_zone_suffix=True)
    assert r.status_code == 200, r.text


def test_update_existing_bad_name_unchanged_is_allowed(client, db):
    # A legacy doubled record must stay editable (e.g. TTL change) until removed.
    _seed(db, "web01.example.com")
    prov = _provider()
    new = {**_old("web01.example.com"), "ttl": 60}
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = _put(client, _old("web01.example.com"), new)
    assert r.status_code == 200, r.text
