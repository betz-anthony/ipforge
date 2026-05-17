from unittest.mock import MagicMock, patch

from app.models.address import IPAddress
from app.models.subnet import Subnet
from app.providers.dhcp.base import DHCPScope


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
    r = client.get("/api/addresses")
    assert r.status_code == 200
    row = next(x for x in r.json() if x["address"] == "10.1.0.2")
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
        r = client.post(f"/api/subnets/{s.id}/allocate", json={
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
        r = client.post(f"/api/subnets/{s.id}/allocate", json={
            "hostname": "web02",
            "register_dhcp": True,
            "mac_address": "aa:bb:cc:dd:ee:ff",
        })
    assert r.status_code == 201
    addr = db.query(IPAddress).filter_by(address=r.json()["address"]).first()
    assert addr.dhcp_provider == "pihole"
    assert addr.dhcp_scope_id == "pihole"
