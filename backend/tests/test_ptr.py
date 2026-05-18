from app.models.address import IPAddress
from app.models.subnet import Subnet
from app.schemas.address import AddressRead


def _subnet(db, cidr="10.0.1.0/24"):
    s = Subnet(name="test", cidr=cidr, ip_version=4)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _ip(db, subnet, address="10.0.1.2", **kw):
    a = IPAddress(address=address, subnet_id=subnet.id, **kw)
    db.add(a); db.commit(); db.refresh(a)
    return a


# ── Task 1: Data model ────────────────────────────────────────────────────────

def test_ptr_zone_column_nullable(db):
    s = _subnet(db)
    a = _ip(db, s)
    assert a.ptr_zone is None


def test_ptr_zone_column_writable(db):
    s = _subnet(db)
    a = _ip(db, s)
    a.ptr_zone = "1.0.10.in-addr.arpa"
    db.commit(); db.refresh(a)
    assert a.ptr_zone == "1.0.10.in-addr.arpa"


def test_ptr_zone_in_schema(db):
    s = _subnet(db)
    a = _ip(db, s)
    r = AddressRead.model_validate(a)
    assert hasattr(r, "ptr_zone")
    assert r.ptr_zone is None


def test_ptr_zone_in_schema_populated(db):
    s = _subnet(db)
    a = _ip(db, s, ptr_zone="1.0.10.in-addr.arpa")
    r = AddressRead.model_validate(a)
    assert r.ptr_zone == "1.0.10.in-addr.arpa"


# ── Task 2: ptr.py utility ───────────────────────────────────────────────────

from app.core.ptr import find_reverse_zone, build_ptr_record


def test_find_zone_returns_most_specific():
    zones = ["2.1.10.in-addr.arpa", "1.10.in-addr.arpa", "10.in-addr.arpa"]
    assert find_reverse_zone("10.1.2.5", zones) == "2.1.10.in-addr.arpa"


def test_find_zone_falls_back_to_less_specific():
    zones = ["1.10.in-addr.arpa", "10.in-addr.arpa"]
    assert find_reverse_zone("10.1.2.5", zones) == "1.10.in-addr.arpa"


def test_find_zone_returns_none_when_no_match():
    zones = ["example.com", "example.net"]
    assert find_reverse_zone("10.1.2.5", zones) is None


def test_find_zone_empty_list():
    assert find_reverse_zone("10.1.2.5", []) is None


def test_find_zone_ipv6():
    # Zone covers the first 12 nibbles of 2001:db8::/32
    zones = ["0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa"]
    result = find_reverse_zone("2001:db8::1", zones)
    assert result == "0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa"


def test_build_ptr_name_is_host_portion_of_zone():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa")
    assert r.name == "5"


def test_build_ptr_name_with_less_specific_zone():
    r = build_ptr_record("10.1.2.5", "web01", "1.10.in-addr.arpa")
    assert r.name == "5.2"


def test_build_ptr_value_has_trailing_dot():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa")
    assert r.value == "web01."


def test_build_ptr_fqdn_value_gets_trailing_dot():
    r = build_ptr_record("10.1.2.5", "web01.example.com", "2.1.10.in-addr.arpa")
    assert r.value == "web01.example.com."


def test_build_ptr_record_type_is_PTR():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa")
    assert r.record_type == "PTR"


def test_build_ptr_zone_is_reverse_zone():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa")
    assert r.zone == "2.1.10.in-addr.arpa"


def test_build_ptr_sets_provider():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", provider="bind01")
    assert r.source == "bind01"


def test_build_ptr_sets_ttl():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", ttl=7200)
    assert r.ttl == 7200


# ── Task 3: Allocation PTR ────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch
from app.models.subnet import Subnet as SubnetModel
from app.models.address import IPAddress as IPAddressModel


def _alloc_subnet(db, cidr="10.0.1.0/24"):
    s = SubnetModel(name="alloc-test", cidr=cidr, ip_version=4)
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_allocation_register_ptr_requires_register_dns(client, db):
    s = _alloc_subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={
        "hostname": "web01",
        "register_dns": False,
        "register_ptr": True,
    })
    assert r.status_code == 422
    assert "register_dns" in r.json()["detail"]


def test_allocation_register_ptr_with_pihole_returns_422(client, db):
    s = _alloc_subnet(db)
    from app.providers.dns.pihole import PiholeDNSProvider as RealPihole

    class FakePihole(RealPihole):
        source = "pihole01"
        def __init__(self): pass
        def add_record(self, record): raise NotImplementedError()
        def get_zones(self): return []
        def get_records(self, zone): return []
        def delete_record(self, record): pass
        def update_record(self, old, new): pass

    fake = FakePihole()
    with patch("app.api.allocation.get_dns_providers", return_value=[fake]), \
         patch("app.api.allocation.get_dhcp_providers", return_value=[]):
        r = client.post(f"/api/subnets/{s.id}/allocate", json={
            "hostname": "web02",
            "register_dns": True,
            "register_ptr": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 422
    assert "does not support PTR" in r.json()["detail"]


def test_allocation_register_ptr_no_reverse_zone_rolls_back_a(client, db):
    s = _alloc_subnet(db)
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock()
    mock_prov.delete_record = MagicMock()
    mock_prov.get_zones = MagicMock(return_value=["example.com"])

    with patch("app.api.allocation.get_dns_providers", return_value=[mock_prov]), \
         patch("app.api.allocation.get_dhcp_providers", return_value=[]):
        r = client.post(f"/api/subnets/{s.id}/allocate", json={
            "hostname": "web03",
            "register_dns": True,
            "register_ptr": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 422
    assert "reverse zone" in r.json()["detail"].lower()
    mock_prov.delete_record.assert_called_once()
    # DB row was rolled back (is_new path)
    addr = db.query(IPAddressModel).filter_by(hostname="web03").first()
    assert addr is None


def test_allocation_register_ptr_success_sets_ptr_zone(client, db):
    s = _alloc_subnet(db)
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock()
    mock_prov.delete_record = MagicMock()
    mock_prov.get_zones = MagicMock(return_value=["example.com", "1.0.10.in-addr.arpa"])

    with patch("app.api.allocation.get_dns_providers", return_value=[mock_prov]), \
         patch("app.api.allocation.get_dhcp_providers", return_value=[]):
        r = client.post(f"/api/subnets/{s.id}/allocate", json={
            "hostname": "web04",
            "register_dns": True,
            "register_ptr": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 201
    assert mock_prov.add_record.call_count == 2
    ptr_call = mock_prov.add_record.call_args_list[1]
    ptr_rec = ptr_call[0][0]
    assert ptr_rec.record_type == "PTR"
    assert ptr_rec.zone == "1.0.10.in-addr.arpa"
    assert r.json()["ptr_registered"] is True
    addr = db.query(IPAddressModel).filter_by(address=r.json()["address"]).first()
    assert addr.ptr_zone == "1.0.10.in-addr.arpa"


def test_allocation_register_ptr_failure_rolls_back_a(client, db):
    s = _alloc_subnet(db)
    add_call_count = 0

    def side_effect_add(record):
        nonlocal add_call_count
        add_call_count += 1
        if add_call_count == 2:
            raise Exception("PTR server error")

    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock(side_effect=side_effect_add)
    mock_prov.delete_record = MagicMock()
    mock_prov.get_zones = MagicMock(return_value=["example.com", "1.0.10.in-addr.arpa"])

    with patch("app.api.allocation.get_dns_providers", return_value=[mock_prov]), \
         patch("app.api.allocation.get_dhcp_providers", return_value=[]):
        r = client.post(f"/api/subnets/{s.id}/allocate", json={
            "hostname": "web05",
            "register_dns": True,
            "register_ptr": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 502
    assert "PTR registration failed" in r.json()["detail"]
    mock_prov.delete_record.assert_called_once()
    addr = db.query(IPAddressModel).filter_by(hostname="web05").first()
    assert addr is None


def test_allocation_register_ptr_get_zones_failure_rolls_back_a(client, db):
    s = _alloc_subnet(db)
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock()
    mock_prov.delete_record = MagicMock()
    mock_prov.get_zones = MagicMock(side_effect=Exception("zones fetch error"))

    with patch("app.api.allocation.get_dns_providers", return_value=[mock_prov]), \
         patch("app.api.allocation.get_dhcp_providers", return_value=[]):
        r = client.post(f"/api/subnets/{s.id}/allocate", json={
            "hostname": "web06",
            "register_dns": True,
            "register_ptr": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 502
    assert "zones" in r.json()["detail"].lower()
    # A record rolled back
    mock_prov.delete_record.assert_called_once()
    # DB row rolled back
    addr = db.query(IPAddressModel).filter_by(hostname="web06").first()
    assert addr is None
