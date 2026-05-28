from app.models.subnet_range import SubnetRange
from app.models.subnet import Subnet


def test_create_range(db):
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    r = SubnetRange(subnet_id=s.id, start_ip="10.0.0.10", end_ip="10.0.0.20", kind="dhcp_pool", label="pool")
    db.add(r)
    db.commit()
    assert r.id is not None
    assert r.kind == "dhcp_pool"


def test_range_cascade_delete(db):
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.0.0.1", end_ip="10.0.0.1", kind="gateway"))
    db.commit()
    db.delete(s)
    db.commit()
    assert db.query(SubnetRange).count() == 0
