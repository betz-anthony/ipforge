import ipaddress
from unittest.mock import MagicMock, patch
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.providers.dhcp.base import DHCPScope


def _subnet(db, cidr="10.0.1.0/24", name="test", **kwargs):
    s = Subnet(name=name, cidr=cidr, ip_version=4, **kwargs)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ── basic allocation ──────────────────────────────────────────────────────────

def test_allocate_returns_lowest_available(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["address"] == "10.0.1.2"  # .1 skipped
    assert body["hostname"] == "web-01"
    assert body["status"] == "reserved"
    assert body["is_new"] is True
    assert body["subnet_cidr"] == "10.0.1.0/24"


def test_allocate_skips_dot_one(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert not r.json()["address"].endswith(".1")


def test_allocate_skips_dot_255(client, db):
    # Use /16 so .255 is a valid host. Fill .2-.254 to force candidate into .255 range.
    s = _subnet(db, cidr="10.0.0.0/16")
    for b in range(2, 255):
        db.add(IPAddress(address=f"10.0.0.{b}", subnet_id=s.id, status=AddressStatus.reserved))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    # 10.0.0.255 is skipped; next candidate is 10.0.1.2
    assert r.json()["address"] == "10.0.1.2"


def test_allocate_skips_discovered(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id, status=AddressStatus.discovered))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    assert r.json()["address"] == "10.0.1.3"  # .1 and .2(discovered) skipped


def test_allocate_reuses_available_record(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id, status=AddressStatus.available))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    assert r.json()["address"] == "10.0.1.2"
    addr = db.query(IPAddress).filter_by(address="10.0.1.2").first()
    assert addr.status == AddressStatus.reserved


def test_allocate_hostname_stored_lowercase(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "Web-01"})
    assert r.json()["hostname"] == "web-01"


def test_allocate_subnet_exhausted(client, db):
    # /30: hosts = .1,.2 → skip .1 → only .2 allocatable
    s = _subnet(db, cidr="10.0.0.0/30")
    db.add(IPAddress(address="10.0.0.2", subnet_id=s.id, status=AddressStatus.reserved))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "new"})
    assert r.status_code == 409


def test_allocate_subnet_not_found(client, db):
    r = client.post("/api/subnets/9999/allocate", json={"hostname": "web-01"})
    assert r.status_code == 404


def test_allocate_missing_hostname(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": ""})
    assert r.status_code == 422


# ── idempotency ───────────────────────────────────────────────────────────────

def test_allocate_idempotent_returns_same_ip(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    r2 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["address"] == r2.json()["address"]
    assert r2.json()["is_new"] is False
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 1


def test_allocate_idempotent_case_insensitive(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "Web-01"})
    r2 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "WEB-01"})
    assert r1.json()["address"] == r2.json()["address"]
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 1


def test_allocate_idempotent_updates_mac_if_blank(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    client.post(f"/api/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "aa:bb:cc:dd:ee:ff"})
    addr = db.query(IPAddress).filter_by(address=r1.json()["address"]).first()
    db.refresh(addr)
    assert addr.mac_address == "aa:bb:cc:dd:ee:ff"


def test_allocate_idempotent_does_not_overwrite_existing_mac(client, db):
    s = _subnet(db)
    client.post(f"/api/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "11:22:33:44:55:66"})
    client.post(f"/api/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "aa:bb:cc:dd:ee:ff"})
    addr = db.query(IPAddress).filter_by(hostname="web-01").first()
    db.refresh(addr)
    assert addr.mac_address == "11:22:33:44:55:66"  # original preserved


def test_allocate_deprecated_hostname_gets_new_ip(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id,
                     hostname="web-01", status=AddressStatus.deprecated))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r.status_code == 201
    assert r.json()["is_new"] is True
    assert r.json()["address"] == "10.0.1.3"  # deprecated is in _INELIGIBLE, so .2 is skipped


# ── DNS registration ──────────────────────────────────────────────────────────

def test_allocate_register_dns_missing_zone(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate",
                    json={"hostname": "web-01", "register_dns": True})
    assert r.status_code == 422
    assert "dns_zone" in r.json()["detail"]


def test_allocate_register_dns_no_provider(client, db):
    s = _subnet(db)
    with patch("app.api.allocation.get_dns_providers", return_value=[]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 400


def test_allocate_register_dns_success(client, db):
    s = _subnet(db)
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock()
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 201
    assert r.json()["dns_registered"] is True
    mock_dns.add_record.assert_called_once()
    call_record = mock_dns.add_record.call_args[0][0]
    assert call_record.name == "web-01"
    assert call_record.record_type == "A"
    assert call_record.zone == "example.com"
    assert call_record.value == "10.0.1.2"


def test_allocate_register_dns_failure_rolls_back_ip(client, db):
    s = _subnet(db)
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock(side_effect=Exception("DNS timeout"))
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 502
    assert "DNS registration failed" in r.json()["detail"]
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 0


def test_allocate_dns_failure_idempotent_hit_keeps_ip(client, db):
    # Idempotent hit: existing IP should NOT be deleted on DNS failure
    s = _subnet(db)
    client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock(side_effect=Exception("DNS timeout"))
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 502
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 1  # still exists


def test_allocate_uses_subnet_dns_provider(client, db):
    s = _subnet(db, dns_provider_name="preferred-dns")
    mock_preferred = MagicMock()
    mock_preferred.source = "preferred-dns"
    mock_preferred.add_record = MagicMock()
    mock_other = MagicMock()
    mock_other.source = "other-dns"
    with patch("app.api.allocation.get_dns_providers",
               return_value=[mock_other, mock_preferred]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 201
    mock_preferred.add_record.assert_called_once()
    mock_other.add_record.assert_not_called()


def test_allocate_request_overrides_subnet_dns_provider(client, db):
    s = _subnet(db, dns_provider_name="subnet-default")
    mock_override = MagicMock()
    mock_override.source = "explicit-provider"
    mock_override.add_record = MagicMock()
    mock_default = MagicMock()
    mock_default.source = "subnet-default"
    with patch("app.api.allocation.get_dns_providers",
               return_value=[mock_default, mock_override]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com",
                              "dns_provider": "explicit-provider"})
    assert r.status_code == 201
    mock_override.add_record.assert_called_once()
    mock_default.add_record.assert_not_called()


# ── DHCP registration ─────────────────────────────────────────────────────────

def _mock_dhcp(source="msdhcp", scope_start="10.0.1.1", scope_end="10.0.1.254"):
    mock = MagicMock()
    mock.source = source
    mock.get_scopes.return_value = [
        DHCPScope(
            scope_id="10.0.1.0", name="test", subnet_mask="/24",
            start_range=scope_start, end_range=scope_end,
        )
    ]
    mock.add_reservation = MagicMock()
    mock.delete_reservation = MagicMock()
    return mock


def test_allocate_register_dhcp_missing_mac(client, db):
    s = _subnet(db)
    mock_dhcp = _mock_dhcp()
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True})
    assert r.status_code == 422
    assert "mac_address" in r.json()["detail"]


def test_allocate_register_dhcp_no_provider(client, db):
    s = _subnet(db)
    with patch("app.api.allocation.get_dhcp_providers", return_value=[]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 400


def test_allocate_register_dhcp_success(client, db):
    s = _subnet(db)
    mock_dhcp = _mock_dhcp()
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 201
    assert r.json()["dhcp_registered"] is True
    mock_dhcp.add_reservation.assert_called_once()
    call_res = mock_dhcp.add_reservation.call_args[0][0]
    assert call_res.ip_address == "10.0.1.2"
    assert call_res.mac_address == "aa:bb:cc:dd:ee:ff"
    assert call_res.name == "web-01"


def test_allocate_dhcp_no_matching_scope(client, db):
    # Scope doesn't contain the allocated IP → 400, IP rolled back
    s = _subnet(db)
    mock_dhcp = _mock_dhcp(scope_start="192.168.1.1", scope_end="192.168.1.254")
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 400
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 0


def test_allocate_dhcp_failure_rolls_back_ip(client, db):
    s = _subnet(db)
    mock_dhcp = _mock_dhcp()
    mock_dhcp.add_reservation = MagicMock(side_effect=Exception("DHCP error"))
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 502
    assert "DHCP registration failed" in r.json()["detail"]
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 0


def test_allocate_dhcp_failure_rolls_back_ip_and_dns(client, db):
    s = _subnet(db)
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock()
    mock_dns.delete_record = MagicMock()
    mock_dhcp = _mock_dhcp()
    mock_dhcp.add_reservation = MagicMock(side_effect=Exception("DHCP error"))
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]), \
         patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 502
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 0
    mock_dns.delete_record.assert_called_once()
    deleted = mock_dns.delete_record.call_args[0][0]
    assert deleted.name == "web-01"
    assert deleted.zone == "example.com"


def test_allocate_uses_subnet_dhcp_provider(client, db):
    s = _subnet(db, dhcp_provider_name="preferred-dhcp")
    mock_preferred = _mock_dhcp(source="preferred-dhcp")
    mock_other = _mock_dhcp(source="other-dhcp")
    with patch("app.api.allocation.get_dhcp_providers",
               return_value=[mock_other, mock_preferred]):
        r = client.post(f"/api/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 201
    mock_preferred.add_reservation.assert_called_once()
    mock_other.add_reservation.assert_not_called()
