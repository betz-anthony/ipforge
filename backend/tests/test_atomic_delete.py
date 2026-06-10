from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.address import IPAddress
from app.models.cache import CachedDNSRecord, CachedDHCPLease
from app.models.subnet import Subnet
from app.providers.dhcp.base import DHCPScope
from app.sync import _backfill_dns_providers, _backfill_dhcp_providers


def _subnet(db, cidr="10.1.0.0/24"):
    s = Subnet(name="test", cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _ip(db, subnet, address="10.1.0.2", **kw):
    a = IPAddress(address=address, subnet_id=subnet.id, **kw)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_address_model_has_provider_fields(db):
    s = _subnet(db)
    a = _ip(db, s)
    assert hasattr(a, "dns_provider")
    assert hasattr(a, "dns_zone")
    assert hasattr(a, "dhcp_provider")
    assert hasattr(a, "dhcp_scope_id")
    assert a.dns_provider is None
    assert a.dns_zone is None
    assert a.dhcp_provider is None
    assert a.dhcp_scope_id is None


def test_address_read_schema_exposes_provider_fields(client, db):
    s = _subnet(db)
    _ip(db, s, dns_provider="bind01", dns_zone="example.com",
        dhcp_provider="pihole", dhcp_scope_id="pihole")
    r = client.get("/api/v1/addresses")
    assert r.status_code == 200
    row = next(x for x in r.json()["items"] if x["address"] == "10.1.0.2")
    assert row["dns_provider"] == "bind01"
    assert row["dns_zone"] == "example.com"
    assert row["dhcp_provider"] == "pihole"
    assert row["dhcp_scope_id"] == "pihole"


def test_allocation_sets_dns_provider(client, db):
    s = _subnet(db)
    mock_dns = MagicMock()
    mock_dns.source = "bind01"
    mock_dns.add_record = MagicMock()
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
            "hostname": "web01",
            "register_dns": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 201
    addr = db.query(IPAddress).filter_by(address=r.json()["address"]).first()
    assert addr.dns_provider == "bind01"
    assert addr.dns_zone == "example.com"


def test_allocation_sets_dhcp_provider(client, db):
    s = _subnet(db)
    mock_dhcp = MagicMock()
    mock_dhcp.source = "pihole"
    mock_dhcp.add_reservation = MagicMock()
    mock_dhcp.get_scopes = MagicMock(return_value=[
        DHCPScope(scope_id="pihole", name="pihole", subnet_mask="", start_range="10.1.0.1",
                  end_range="10.1.0.254", description="", active=True),
    ])
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
            "hostname": "web02",
            "register_dhcp": True,
            "mac_address": "aa:bb:cc:dd:ee:ff",
        })
    assert r.status_code == 201
    addr = db.query(IPAddress).filter_by(address=r.json()["address"]).first()
    assert addr.dhcp_provider == "pihole"
    assert addr.dhcp_scope_id == "pihole"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_sync_backfills_dns_provider(db):
    s = _subnet(db, "10.2.0.0/24")
    a = _ip(db, s, "10.2.0.2")
    assert a.dns_provider is None
    db.add(CachedDNSRecord(
        name="host1", record_type="A", value="10.2.0.2",
        zone="example.com", ttl=3600, source="bind01", synced_at=_utcnow(),
    ))
    db.commit()
    _backfill_dns_providers(db)
    db.refresh(a)
    assert a.dns_provider == "bind01"
    assert a.dns_zone == "example.com"


def test_sync_backfill_does_not_overwrite_existing(db):
    s = _subnet(db, "10.3.0.0/24")
    a = _ip(db, s, "10.3.0.2", dns_provider="original", dns_zone="orig.com")
    db.add(CachedDNSRecord(
        name="host1", record_type="A", value="10.3.0.2",
        zone="new.com", ttl=3600, source="newprov", synced_at=_utcnow(),
    ))
    db.commit()
    _backfill_dns_providers(db)
    db.refresh(a)
    assert a.dns_provider == "original"
    assert a.dns_zone == "orig.com"


def test_sync_backfills_dhcp_provider(db):
    s = _subnet(db, "10.4.0.0/24")
    a = _ip(db, s, "10.4.0.2")
    assert a.dhcp_provider is None
    db.add(CachedDHCPLease(
        scope_id="lan", ip_address="10.4.0.2", mac_address="aa:bb:cc:00:00:01",
        name="host1", source="pihole", synced_at=_utcnow(),
    ))
    db.commit()
    _backfill_dhcp_providers(db)
    db.refresh(a)
    assert a.dhcp_provider == "pihole"
    assert a.dhcp_scope_id == "lan"


def test_delete_preview_returns_stored_fields(client, db):
    s = _subnet(db, "10.5.0.0/24")
    _ip(db, s, "10.5.0.2", hostname="web01",
        dns_provider="bind01", dns_zone="example.com",
        dhcp_provider="pihole", dhcp_scope_id="lan")
    a = db.query(IPAddress).filter_by(address="10.5.0.2").first()
    r = client.get(f"/api/v1/addresses/{a.id}/delete-preview")
    assert r.status_code == 200
    body = r.json()
    assert body["address"] == "10.5.0.2"
    assert body["hostname"] == "web01"
    keys = {item["key"] for item in body["items"]}
    assert any("bind01" in k and "example.com" in k for k in keys)
    assert any("pihole" in k and "lan" in k for k in keys)


def test_delete_preview_returns_cache_hits(client, db):
    s = _subnet(db, "10.6.0.0/24")
    _ip(db, s, "10.6.0.2", hostname="web02")
    a = db.query(IPAddress).filter_by(address="10.6.0.2").first()
    db.add(CachedDNSRecord(
        name="web02", record_type="A", value="10.6.0.2",
        zone="test.local", ttl=300, source="msdns", synced_at=_utcnow(),
    ))
    db.add(CachedDHCPLease(
        scope_id="scope1", ip_address="10.6.0.2", mac_address="",
        name="web02", source="msdhcp", synced_at=_utcnow(),
    ))
    db.commit()
    r = client.get(f"/api/v1/addresses/{a.id}/delete-preview")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    types = {i["type"] for i in items}
    assert types == {"dns", "dhcp"}


def test_delete_preview_deduplicates_stored_and_cache(client, db):
    s = _subnet(db, "10.7.0.0/24")
    _ip(db, s, "10.7.0.2", hostname="web03",
        dns_provider="bind01", dns_zone="example.com")
    a = db.query(IPAddress).filter_by(address="10.7.0.2").first()
    # cache has same record as stored fields
    db.add(CachedDNSRecord(
        name="web03", record_type="A", value="10.7.0.2",
        zone="example.com", ttl=300, source="bind01", synced_at=_utcnow(),
    ))
    db.commit()
    r = client.get(f"/api/v1/addresses/{a.id}/delete-preview")
    assert r.status_code == 200
    dns_items = [i for i in r.json()["items"] if i["type"] == "dns"]
    assert len(dns_items) == 1


def test_delete_with_no_cleanup_removes_db_row(client, db):
    s = _subnet(db, "10.8.0.0/24")
    a = _ip(db, s, "10.8.0.2")
    r = client.delete(f"/api/v1/addresses/{a.id}")
    assert r.status_code == 204
    assert db.get(IPAddress, a.id) is None


def test_delete_with_cleanup_keys_calls_providers(client, db):
    s = _subnet(db, "10.9.0.0/24")
    a = _ip(db, s, "10.9.0.2", hostname="web04",
            dns_provider="bind01", dns_zone="example.com",
            dhcp_provider="pihole", dhcp_scope_id="lan")
    mock_dns = MagicMock()
    mock_dns.source = "bind01"
    mock_dns.delete_record = MagicMock()
    mock_dhcp = MagicMock()
    mock_dhcp.source = "pihole"
    mock_dhcp.delete_reservation = MagicMock()
    dns_key = f"dns-bind01-example.com-web04-A-10.9.0.2"
    dhcp_key = f"dhcp-pihole-lan-10.9.0.2"
    with patch("app.api.addresses.get_dns_providers", return_value=[mock_dns]), \
         patch("app.api.addresses.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.request("DELETE", f"/api/v1/addresses/{a.id}",
                           json={"cleanup_keys": [dns_key, dhcp_key]})
    assert r.status_code == 204
    mock_dns.delete_record.assert_called_once()
    mock_dhcp.delete_reservation.assert_called_once()
    assert db.get(IPAddress, a.id) is None


def test_delete_rollback_on_provider_failure(client, db):
    s = _subnet(db, "10.10.0.0/24")
    a = _ip(db, s, "10.10.0.2", hostname="web05",
            dns_provider="bind01", dns_zone="example.com")
    addr_id = a.id
    mock_dns = MagicMock()
    mock_dns.source = "bind01"
    mock_dns.delete_record = MagicMock(side_effect=Exception("DNS unreachable"))
    mock_dns.add_record = MagicMock()
    dns_key = f"dns-bind01-example.com-web05-A-10.10.0.2"
    with patch("app.api.addresses.get_dns_providers", return_value=[mock_dns]), \
         patch("app.api.addresses.get_dhcp_providers", return_value=[]):
        r = client.request("DELETE", f"/api/v1/addresses/{addr_id}",
                           json={"cleanup_keys": [dns_key]})
    assert r.status_code == 502
    assert db.get(IPAddress, addr_id) is not None  # DB row intact


def test_subnet_delete_blocked_when_has_addresses(client, db):
    s = _subnet(db, "10.11.0.0/24")
    _ip(db, s, "10.11.0.2")
    r = client.delete(f"/api/v1/subnets/{s.id}")
    assert r.status_code == 409
    assert "1 addresses remain" in r.json()["detail"]
    assert db.get(Subnet, s.id) is not None


def test_subnet_delete_succeeds_when_empty(client, db):
    s = _subnet(db, "10.12.0.0/24")
    r = client.delete(f"/api/v1/subnets/{s.id}")
    assert r.status_code == 204
    assert db.get(Subnet, s.id) is None
