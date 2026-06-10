from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus


def test_subnet_list_includes_utilization_fields(client, db):
    db.add(Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4))
    db.commit()
    r = client.get("/api/v1/subnets")
    assert r.status_code == 200
    s = r.json()[0]
    assert "used_count" in s
    assert "total_count" in s
    assert "utilization_pct" in s


def test_utilization_counts_correct_statuses(client, db):
    subnet = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(subnet)
    db.flush()
    db.add(IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.assigned))
    db.add(IPAddress(address="10.0.0.2", subnet_id=subnet.id, status=AddressStatus.reserved))
    db.add(IPAddress(address="10.0.0.3", subnet_id=subnet.id, status=AddressStatus.discovered))
    db.add(IPAddress(address="10.0.0.4", subnet_id=subnet.id, status=AddressStatus.available))
    db.add(IPAddress(address="10.0.0.5", subnet_id=subnet.id, status=AddressStatus.deprecated))
    db.commit()
    r = client.get("/api/v1/subnets")
    s = r.json()[0]
    assert s["used_count"] == 3
    assert s["total_count"] == 254


def test_utilization_empty_subnet(client, db):
    db.add(Subnet(name="Empty", cidr="10.0.1.0/24", ip_version=4))
    db.commit()
    r = client.get("/api/v1/subnets")
    s = r.json()[0]
    assert s["used_count"] == 0
    assert s["utilization_pct"] == 0.0


def test_utilization_cidr_math_slash32(client, db):
    db.add(Subnet(name="Host", cidr="10.0.2.1/32", ip_version=4))
    db.commit()
    r = client.get("/api/v1/subnets")
    s = r.json()[0]
    assert s["total_count"] == 1


def test_utilization_cidr_math_slash31(client, db):
    db.add(Subnet(name="P2P", cidr="10.0.3.0/31", ip_version=4))
    db.commit()
    r = client.get("/api/v1/subnets")
    s = r.json()[0]
    assert s["total_count"] == 2


def test_utilization_pct_capped_at_100(client, db):
    subnet = Subnet(name="Over", cidr="10.0.4.0/30", ip_version=4)  # 2 usable hosts
    db.add(subnet)
    db.flush()
    for i in range(5):
        db.add(IPAddress(address=f"10.0.4.{i + 1}", subnet_id=subnet.id, status=AddressStatus.assigned))
    db.commit()
    r = client.get("/api/v1/subnets")
    s = r.json()[0]
    assert s["utilization_pct"] == 100.0


def test_utilization_ipv6_subnet(client, db):
    db.add(Subnet(name="IPv6", cidr="2001:db8::/126", ip_version=6))  # /126 = 4 addresses
    db.commit()
    r = client.get("/api/v1/subnets")
    s = r.json()[0]
    assert s["total_count"] == 4  # all 4 addresses usable in IPv6 (no broadcast)
