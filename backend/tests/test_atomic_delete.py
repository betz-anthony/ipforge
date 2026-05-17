from app.models.address import IPAddress
from app.models.subnet import Subnet


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
