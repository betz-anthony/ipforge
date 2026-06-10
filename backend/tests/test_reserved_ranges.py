from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.subnet_range import SubnetRange


def _subnet(db, cidr="10.0.1.0/24"):
    s = Subnet(name="N", cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    return s


def test_allocate_skips_reserved_range(client, db):
    s = _subnet(db)
    # reserve .2 through .5; lowest non-reserved non-.1 is .6
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.0.1.2", end_ip="10.0.1.5", kind="reserved"))
    db.commit()
    r = client.post(f"/api/v1/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    assert r.json()["address"] == "10.0.1.6"


def test_utilization_reserved_count(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.50", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.0.1.10", end_ip="10.0.1.12", kind="reserved"))
    db.commit()
    row = next(x for x in client.get("/api/v1/subnets").json() if x["id"] == s.id)
    assert row["used_count"] == 1
    assert row["reserved_count"] == 3


def test_reserved_count_dedupes_used(client, db):
    s = _subnet(db)
    # .20 is both used (address row) and inside a reserved range -> counted once as used
    db.add(IPAddress(address="10.0.1.20", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.0.1.20", end_ip="10.0.1.22", kind="reserved"))
    db.commit()
    row = next(x for x in client.get("/api/v1/subnets").json() if x["id"] == s.id)
    assert row["used_count"] == 1
    assert row["reserved_count"] == 2  # .21, .22 (.20 excluded, already used)
