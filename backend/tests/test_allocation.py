import ipaddress
from unittest.mock import MagicMock, patch
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDNSRecord, CachedDHCPLease
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
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["address"] == "10.0.1.2"  # .1 skipped
    assert body["hostname"] == "web-01"
    assert body["status"] == "reserved"
    assert body["is_new"] is True
    assert body["subnet_cidr"] == "10.0.1.0/24"


def test_allocate_skips_dot_one(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert not r.json()["address"].endswith(".1")


def test_allocate_skips_dot_255(client, db):
    # Use /16 so .255 is a valid host. Fill .2-.254 to force candidate into .255 range.
    s = _subnet(db, cidr="10.0.0.0/16")
    for b in range(2, 255):
        db.add(IPAddress(address=f"10.0.0.{b}", subnet_id=s.id, status=AddressStatus.reserved))
    db.commit()
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    # 10.0.0.255 is skipped; next candidate is 10.0.1.0
    assert r.json()["address"] == "10.0.1.0"


def test_allocate_skips_discovered(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id, status=AddressStatus.discovered))
    db.commit()
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    assert r.json()["address"] == "10.0.1.3"  # .1 and .2(discovered) skipped


def test_allocate_reuses_available_record(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id, status=AddressStatus.available))
    db.commit()
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    assert r.json()["address"] == "10.0.1.2"
    addr = db.query(IPAddress).filter_by(address="10.0.1.2").first()
    assert addr.status == AddressStatus.reserved


def test_allocate_hostname_stored_lowercase(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "Web-01"})
    assert r.json()["hostname"] == "web-01"


def test_allocate_subnet_exhausted(client, db):
    # /30: hosts = .1,.2 → skip .1 → only .2 allocatable
    s = _subnet(db, cidr="10.0.0.0/30")
    db.add(IPAddress(address="10.0.0.2", subnet_id=s.id, status=AddressStatus.reserved))
    db.commit()
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "new"})
    assert r.status_code == 409


def test_allocate_subnet_not_found(client, db):
    r = client.post("/api/v1/subnets/9999/allocate", json={"hostname": "web-01"})
    assert r.status_code == 404


def test_allocate_missing_hostname(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": ""})
    assert r.status_code == 422


# ── idempotency ───────────────────────────────────────────────────────────────

def test_allocate_idempotent_returns_same_ip(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    r2 = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["address"] == r2.json()["address"]
    assert r2.json()["is_new"] is False
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 1


def test_allocate_idempotent_case_insensitive(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "Web-01"})
    r2 = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "WEB-01"})
    assert r1.json()["address"] == r2.json()["address"]
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 1


def test_allocate_idempotent_updates_mac_if_blank(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    client.post(f"/api/v1/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "aa:bb:cc:dd:ee:ff"})
    addr = db.query(IPAddress).filter_by(address=r1.json()["address"]).first()
    db.refresh(addr)
    assert addr.mac_address == "aa:bb:cc:dd:ee:ff"


def test_allocate_idempotent_does_not_overwrite_existing_mac(client, db):
    s = _subnet(db)
    client.post(f"/api/v1/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "11:22:33:44:55:66"})
    client.post(f"/api/v1/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "aa:bb:cc:dd:ee:ff"})
    addr = db.query(IPAddress).filter_by(hostname="web-01").first()
    db.refresh(addr)
    assert addr.mac_address == "11:22:33:44:55:66"  # original preserved


def test_allocate_deprecated_hostname_gets_new_ip(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id,
                     hostname="web-01", status=AddressStatus.deprecated))
    db.commit()
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r.status_code == 201
    assert r.json()["is_new"] is True
    assert r.json()["address"] == "10.0.1.3"  # deprecated is in _INELIGIBLE, so .2 is skipped


# ── DNS registration ──────────────────────────────────────────────────────────

def test_allocate_register_dns_missing_zone(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                    json={"hostname": "web-01", "register_dns": True})
    assert r.status_code == 422
    assert "dns_zone" in r.json()["detail"]


def test_allocate_register_dns_no_provider(client, db):
    s = _subnet(db)
    with patch("app.api.allocation.get_dns_providers", return_value=[]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 400


def test_allocate_register_dns_success(client, db):
    s = _subnet(db)
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock()
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
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


def test_allocate_register_dns_writes_cache_row(client, db):
    # Allocation must reflect the pushed record into the DNS cache immediately, so
    # the DNS page shows it without waiting for the next background sync.
    s = _subnet(db)
    mock_dns = MagicMock()
    mock_dns.source = "bind01"
    mock_dns.add_record = MagicMock()
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 201
    row = db.query(CachedDNSRecord).filter_by(name="web-01", zone="example.com").first()
    assert row is not None
    assert row.record_type == "A"
    assert row.value == "10.0.1.2"
    assert row.source == "bind01"


def test_allocate_register_dhcp_writes_cache_lease(client, db):
    s = _subnet(db)
    mock_dhcp = _mock_dhcp(source="kea01")
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:01"})
    assert r.status_code == 201
    lease = db.query(CachedDHCPLease).filter_by(ip_address="10.0.1.2", source="kea01").first()
    assert lease is not None
    assert lease.name == "web-01"
    assert lease.mac_address == "aa:bb:cc:dd:ee:01"


def test_allocate_register_dns_failure_rolls_back_ip(client, db):
    s = _subnet(db)
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock(side_effect=Exception("DNS timeout"))
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com"})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "provider_unreachable"
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 0


def test_allocate_dns_failure_idempotent_hit_keeps_ip(client, db):
    # Idempotent hit: existing IP should NOT be deleted on DNS failure
    s = _subnet(db)
    client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock(side_effect=Exception("DNS timeout"))
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dns": True,
                              "dns_zone": "example.com",
                              "dns_provider": "explicit-provider"})
    assert r.status_code == 201
    mock_override.add_record.assert_called_once()
    mock_default.add_record.assert_not_called()


# ── DHCP registration ─────────────────────────────────────────────────────────

def _mock_dhcp(source="msdhcp", scope_start="10.0.1.1", scope_end="10.0.1.254",
               scope_id="10.0.1.0", subnet_mask="/24"):
    mock = MagicMock()
    mock.source = source
    mock.get_scopes.return_value = [
        DHCPScope(
            scope_id=scope_id, name="test", subnet_mask=subnet_mask,
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True})
    assert r.status_code == 422
    assert "mac_address" in r.json()["detail"]


def test_allocate_register_dhcp_no_provider(client, db):
    s = _subnet(db)
    with patch("app.api.allocation.get_dhcp_providers", return_value=[]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 400


def test_allocate_register_dhcp_success(client, db):
    s = _subnet(db)
    mock_dhcp = _mock_dhcp()
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
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
    # Scope is a different network than the allocated IP → 400, IP rolled back
    s = _subnet(db)  # 10.0.1.0/24
    mock_dhcp = _mock_dhcp(scope_id="192.168.1.0", subnet_mask="/24",
                           scope_start="192.168.1.1", scope_end="192.168.1.254")
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 400
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 0


def test_allocate_dhcp_failure_rolls_back_ip(client, db):
    s = _subnet(db)
    mock_dhcp = _mock_dhcp()
    mock_dhcp.add_reservation = MagicMock(side_effect=Exception("DHCP error"))
    with patch("app.api.allocation.get_dhcp_providers", return_value=[mock_dhcp]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "provider_error"
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate",
                        json={"hostname": "web-01", "register_dhcp": True,
                              "mac_address": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 201
    mock_preferred.add_reservation.assert_called_once()
    mock_other.add_reservation.assert_not_called()

def test_allocation_dns_failure_returns_envelope(client, db):
    s = _subnet(db)   # reuse the module's subnet helper
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.add_record = MagicMock(side_effect=Exception("401 Unauthorized"))
    with patch("app.api.allocation.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
            "hostname": "web01", "register_dns": True, "dns_zone": "example.com"})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "provider_auth_failed"


# ── DHCP scope matching (regression: reservations outside the dynamic pool) ──
def test_scope_contains_cidr_outside_pool():
    import ipaddress
    from app.api.allocation import _scope_contains
    # kea-style: scope_id is a CIDR, narrow pool. A reservation OUTSIDE the pool
    # but inside the subnet must still match (static reservations are normal).
    s = DHCPScope(scope_id="10.99.0.0/24", name="x", subnet_mask="",
                  start_range="10.99.0.100", end_range="10.99.0.150")
    assert _scope_contains(s, ipaddress.ip_address("10.99.0.5"))      # outside pool, in CIDR
    assert _scope_contains(s, ipaddress.ip_address("10.99.0.120"))    # in pool
    assert not _scope_contains(s, ipaddress.ip_address("10.88.0.5"))  # other subnet


def test_scope_contains_msdhcp_network_plus_mask():
    import ipaddress
    from app.api.allocation import _scope_contains
    # MS DHCP v4: bare network + dotted mask.
    s = DHCPScope(scope_id="10.0.1.0", name="x", subnet_mask="255.255.255.0",
                  start_range="10.0.1.100", end_range="10.0.1.150")
    assert _scope_contains(s, ipaddress.ip_address("10.0.1.5"))
    assert not _scope_contains(s, ipaddress.ip_address("10.0.2.5"))


def test_scope_contains_range_fallback_for_non_network_scope():
    import ipaddress
    from app.api.allocation import _scope_contains
    # Pi-hole-style: scope_id is not a network -> fall back to the pool range.
    s = DHCPScope(scope_id="pihole", name="x", subnet_mask="",
                  start_range="10.5.0.10", end_range="10.5.0.20")
    assert _scope_contains(s, ipaddress.ip_address("10.5.0.15"))
    assert not _scope_contains(s, ipaddress.ip_address("10.5.0.99"))
