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
