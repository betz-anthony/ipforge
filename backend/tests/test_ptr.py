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
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", provider="bind01")
    assert r.name == "5"


def test_build_ptr_name_with_less_specific_zone():
    r = build_ptr_record("10.1.2.5", "web01", "1.10.in-addr.arpa", provider="bind01")
    assert r.name == "5.2"


def test_build_ptr_value_has_trailing_dot():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", provider="bind01")
    assert r.value == "web01."


def test_build_ptr_fqdn_value_gets_trailing_dot():
    r = build_ptr_record("10.1.2.5", "web01.example.com", "2.1.10.in-addr.arpa", provider="bind01")
    assert r.value == "web01.example.com."


def test_build_ptr_record_type_is_PTR():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", provider="bind01")
    assert r.record_type == "PTR"


def test_build_ptr_zone_is_reverse_zone():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", provider="bind01")
    assert r.zone == "2.1.10.in-addr.arpa"


def test_build_ptr_sets_provider():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", provider="bind01")
    assert r.source == "bind01"


def test_build_ptr_sets_ttl():
    r = build_ptr_record("10.1.2.5", "web01", "2.1.10.in-addr.arpa", provider="bind01", ttl=7200)
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
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
            "hostname": "web05",
            "register_dns": True,
            "register_ptr": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "provider_error"
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
        r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={
            "hostname": "web06",
            "register_dns": True,
            "register_ptr": True,
            "dns_zone": "example.com",
        })
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "provider_error"
    # A record rolled back
    mock_prov.delete_record.assert_called_once()
    # DB row rolled back
    addr = db.query(IPAddressModel).filter_by(hostname="web06").first()
    assert addr is None


# ── Task 4: DNS API PTR + delete-preview ──────────────────────────────────────

from app.models.cache import CachedDNSZone, CachedDNSRecord as CachedRow


def _add_zone(db, zone, source="bind01"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(CachedDNSZone(zone=zone, source=source, synced_at=now))
    db.commit()


def test_dns_create_record_register_ptr_creates_both(client, db):
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock()

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.post("/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
            "register_ptr": True,
        })
    assert r.status_code == 201
    assert mock_prov.add_record.call_count == 2
    ptr_call = mock_prov.add_record.call_args_list[1][0][0]
    assert ptr_call.record_type == "PTR"
    assert ptr_call.zone == "1.0.10.in-addr.arpa"
    assert ptr_call.value == "web01."


def test_dns_create_record_register_ptr_pihole_skips_ptr(client, db):
    # Pi-hole has no PTR support — register_ptr must be skipped, not 422'd.
    _add_zone(db, "example.com", source="pihole01")
    _add_zone(db, "1.0.10.in-addr.arpa", source="pihole01")
    from app.providers.dns.pihole import PiholeDNSProvider as RealPihole

    class FakePihole(RealPihole):
        source = "pihole01"
        def __init__(self): pass
        def add_record(self, r): pass
        def get_zones(self): return []
        def get_records(self, z): return []
        def delete_record(self, r): pass
        def update_record(self, o, n): pass

    fake = FakePihole()
    with patch("app.api.dns.get_dns_providers", return_value=[fake]):
        r = client.post("/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "pihole01",
            "register_ptr": True,
        })
    assert r.status_code == 201, r.text


def test_dns_create_record_register_ptr_no_reverse_zone_skips_ptr(client, db):
    _add_zone(db, "example.com")
    # No reverse zone — PTR is skipped, A record still created (no 422, no undo).
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock()
    mock_prov.delete_record = MagicMock()

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.post("/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
            "register_ptr": True,
        })
    assert r.status_code == 201, r.text
    assert mock_prov.add_record.call_count == 1   # A only
    mock_prov.delete_record.assert_not_called()   # A not rolled back


def test_dns_create_record_register_ptr_ptr_fail_keeps_a(client, db):
    # PTR registration is best-effort: a PTR provider failure must NOT roll back
    # the successfully-created A record.
    _add_zone(db, "example.com")
    _add_zone(db, "1.0.10.in-addr.arpa")
    add_count = 0

    def side_add(record):
        nonlocal add_count
        add_count += 1
        if add_count == 2:
            raise Exception("PTR server error")

    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock(side_effect=side_add)
    mock_prov.delete_record = MagicMock()

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.post("/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
            "register_ptr": True,
        })
    assert r.status_code == 201, r.text
    assert mock_prov.add_record.call_count == 2   # A + PTR attempt
    mock_prov.delete_record.assert_not_called()   # A kept


def test_dns_delete_record_delete_ptr_deletes_both(client, db):
    _add_zone(db, "1.0.10.in-addr.arpa")
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.delete_record = MagicMock()

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.request("DELETE", "/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
            "delete_ptr": True,
        })
    assert r.status_code == 204
    assert mock_prov.delete_record.call_count == 2
    ptr_call = mock_prov.delete_record.call_args_list[1][0][0]
    assert ptr_call.record_type == "PTR"
    assert ptr_call.zone == "1.0.10.in-addr.arpa"


def test_dns_delete_record_delete_ptr_no_reverse_zone_skips_ptr(client, db):
    _add_zone(db, "example.com")  # forward zone present, no reverse zone
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.delete_record = MagicMock()

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.request("DELETE", "/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
            "delete_ptr": True,
        })
    assert r.status_code == 204, r.text
    assert mock_prov.delete_record.call_count == 1   # A only — PTR skipped


def test_dns_delete_record_ptr_fail_keeps_a_deleted(client, db):
    # PTR delete is best-effort: an absent/failing PTR (record created outside its
    # reverse zone) must NOT revert the A deletion.
    _add_zone(db, "1.0.10.in-addr.arpa")
    del_count = 0

    def side_del(record):
        nonlocal del_count
        del_count += 1
        if del_count == 2:
            raise Exception("Remove-DnsServerResourceRecord: WIN32 9714 ObjectNotFound")

    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.delete_record = MagicMock(side_effect=side_del)
    mock_prov.add_record = MagicMock()

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.request("DELETE", "/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
            "delete_ptr": True,
        })
    assert r.status_code == 204, r.text
    assert mock_prov.delete_record.call_count == 2   # A + PTR attempt
    mock_prov.add_record.assert_not_called()         # A NOT re-added


def test_dns_create_record_commit_failure_undoes_provider(client, db, monkeypatch):
    _add_zone(db, "example.com")
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.add_record = MagicMock()
    mock_prov.delete_record = MagicMock()
    monkeypatch.setattr(db, "commit", MagicMock(side_effect=Exception("commit boom")))

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.post("/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
        })
    assert r.status_code == 502
    mock_prov.add_record.assert_called_once()
    mock_prov.delete_record.assert_called_once()  # A record undone on commit failure


def test_dns_delete_record_commit_failure_undoes_provider(client, db, monkeypatch):
    mock_prov = MagicMock()
    mock_prov.source = "bind01"
    mock_prov.delete_record = MagicMock()
    mock_prov.add_record = MagicMock()
    monkeypatch.setattr(db, "commit", MagicMock(side_effect=Exception("commit boom")))

    with patch("app.api.dns.get_dns_providers", return_value=[mock_prov]):
        r = client.request("DELETE", "/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "bind01",
        })
    assert r.status_code == 502
    mock_prov.delete_record.assert_called_once()
    mock_prov.add_record.assert_called_once()  # A record re-added on commit failure


def test_delete_preview_includes_ptr_when_ptr_zone_set(client, db):
    s = _subnet(db)
    a = _ip(db, s, address="10.0.1.2", hostname="web01",
            dns_provider="bind01", dns_zone="example.com",
            ptr_zone="1.0.10.in-addr.arpa")
    r = client.get(f"/api/v1/addresses/{a.id}/delete-preview")
    assert r.status_code == 200
    items = r.json()["items"]
    ptr_items = [i for i in items if i.get("record_type") == "PTR"]
    assert len(ptr_items) == 1
    pi = ptr_items[0]
    assert pi["zone"] == "1.0.10.in-addr.arpa"
    assert pi["provider"] == "bind01"
    assert pi["name"] == "2"   # host portion of 10.0.1.2 in 1.0.10.in-addr.arpa
    assert pi["value"] == "web01."


def test_delete_preview_no_ptr_item_when_ptr_zone_null(client, db):
    s = _subnet(db)
    a = _ip(db, s, address="10.0.1.2", hostname="web01",
            dns_provider="bind01", dns_zone="example.com")
    r = client.get(f"/api/v1/addresses/{a.id}/delete-preview")
    assert r.status_code == 200
    items = r.json()["items"]
    ptr_items = [i for i in items if i.get("record_type") == "PTR"]
    assert len(ptr_items) == 0


def test_dns_create_provider_error_returns_envelope(client, db):
    _add_zone(db, "example.com")
    prov = MagicMock()
    prov.source = "msdns"
    prov.supports_ptr = True
    prov.add_record = MagicMock(side_effect=Exception("WinRMTransportError: 401 Unauthorized"))
    with patch("app.api.dns.get_dns_providers", return_value=[prov]):
        r = client.post("/api/v1/dns/zones/example.com/records", json={
            "name": "web01", "record_type": "A", "value": "10.0.1.5",
            "zone": "example.com", "ttl": 3600, "source": "msdns"})
    assert r.status_code == 502
    d = r.json()["detail"]
    assert d["code"] == "provider_auth_failed"
    assert d["hint"]
    # client fixture user is admin -> raw detail present
    assert "WinRMTransportError" in d["detail"]
