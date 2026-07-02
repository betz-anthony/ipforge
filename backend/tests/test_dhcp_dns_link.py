"""DHCP-DNS-LINK-001 — 'also create DNS record' on standalone DHCP reservation."""
from unittest.mock import MagicMock, patch

from app.models.subnet import Subnet
from app.models.cache import CachedDNSRecord, CachedDHCPLease


def _subnet(db, cidr="10.0.0.0/24", dns_provider_name=None):
    s = Subnet(name="N", cidr=cidr, ip_version=4, dns_provider_name=dns_provider_name)
    db.add(s)
    db.commit()
    return s


def _dhcp():
    p = MagicMock()
    p.source = "msdhcp"
    p.add_reservation = MagicMock()
    p.delete_reservation = MagicMock()
    return p


def _dns(source="msdns"):
    p = MagicMock()
    p.source = source
    p.add_record = MagicMock()
    return p


def _post(client, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return client.post(
        f"/api/v1/dhcp/scopes/10.0.0.0/reservations?{qs}",
        json={"scope_id": "10.0.0.0", "ip_address": "10.0.0.5",
              "mac_address": "aa:bb:cc:dd:ee:ff", "name": "host1"},
    )


def test_reservation_register_dns_success(client, db):
    _subnet(db)
    dhcp, dns = _dhcp(), _dns()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[dns]):
        r = _post(client, source="msdhcp", register_dns="true", dns_zone="example.com")
    assert r.status_code == 201
    dns.add_record.assert_called_once()
    rec = dns.add_record.call_args[0][0]
    assert rec.name == "host1" and rec.record_type == "A"
    assert rec.value == "10.0.0.5" and rec.zone == "example.com"


def test_reservation_register_dns_writes_cache_row(client, db):
    _subnet(db)
    dhcp, dns = _dhcp(), _dns(source="bind01")
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[dns]):
        r = _post(client, source="msdhcp", register_dns="true", dns_zone="example.com")
    assert r.status_code == 201
    row = db.query(CachedDNSRecord).filter_by(name="host1", zone="example.com").first()
    assert row is not None and row.value == "10.0.0.5" and row.source == "bind01"


def test_reservation_uses_subnet_default_dns_provider(client, db):
    _subnet(db, dns_provider_name="preferred")
    dhcp = _dhcp()
    preferred, other = _dns(source="preferred"), _dns(source="other")
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[other, preferred]):
        r = _post(client, source="msdhcp", register_dns="true", dns_zone="example.com")
    assert r.status_code == 201
    preferred.add_record.assert_called_once()
    other.add_record.assert_not_called()


def test_reservation_register_dns_requires_zone(client, db):
    _subnet(db)
    dhcp, dns = _dhcp(), _dns()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[dns]):
        r = _post(client, source="msdhcp", register_dns="true")
    assert r.status_code == 422
    dhcp.add_reservation.assert_not_called()


def test_reservation_register_dns_requires_name(client, db):
    _subnet(db)
    dhcp, dns = _dhcp(), _dns()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[dns]):
        r = client.post(
            "/api/v1/dhcp/scopes/10.0.0.0/reservations?source=msdhcp&register_dns=true&dns_zone=example.com",
            json={"scope_id": "10.0.0.0", "ip_address": "10.0.0.5",
                  "mac_address": "aa:bb:cc:dd:ee:ff", "name": ""},
        )
    assert r.status_code == 422


def test_reservation_register_dns_no_provider(client, db):
    _subnet(db)
    dhcp = _dhcp()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[]):
        r = _post(client, source="msdhcp", register_dns="true", dns_zone="example.com")
    assert r.status_code == 400
    dhcp.add_reservation.assert_not_called()


def test_reservation_dns_failure_rolls_back_dhcp(client, db):
    _subnet(db)
    dhcp = _dhcp()
    dns = _dns()
    dns.add_record = MagicMock(side_effect=Exception("DNS timeout"))
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[dns]):
        r = _post(client, source="msdhcp", register_dns="true", dns_zone="example.com")
    assert r.status_code == 502
    # DHCP reservation must be undone, and no cache lease persisted.
    dhcp.delete_reservation.assert_called_once()
    assert db.query(CachedDHCPLease).filter_by(ip_address="10.0.0.5").count() == 0


def test_reservation_without_register_dns_ignores_dns(client, db):
    _subnet(db)
    dhcp, dns = _dhcp(), _dns()
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[dhcp]), \
         patch("app.api.dhcp.get_dns_providers", return_value=[dns]):
        r = _post(client, source="msdhcp")
    assert r.status_code == 201
    dns.add_record.assert_not_called()
