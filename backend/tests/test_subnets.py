from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus


def test_subnet_list_includes_hierarchy_fields(client, db):
    db.add(Subnet(name="Root", cidr="10.0.0.0/8", ip_version=4))
    db.commit()
    r = client.get("/api/subnets")
    assert r.status_code == 200
    s = r.json()[0]
    assert "parent_id" in s
    assert "rollup_used_count" in s
    assert "rollup_total_count" in s
    assert "rollup_utilization_pct" in s


def test_rollup_leaf_equals_own_stats(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.flush()
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4, parent_id=parent.id)
    db.add(child)
    db.flush()
    db.add(IPAddress(address="10.1.0.1", subnet_id=child.id, status=AddressStatus.assigned))
    db.commit()

    r = client.get("/api/subnets")
    assert r.status_code == 200
    by_id = {s["id"]: s for s in r.json()}

    child_row = by_id[child.id]
    assert child_row["rollup_used_count"] == child_row["used_count"]
    assert child_row["rollup_total_count"] == child_row["total_count"]


def test_rollup_parent_includes_children(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.flush()
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4, parent_id=parent.id)
    db.add(child)
    db.flush()
    db.add(IPAddress(address="10.1.0.1", subnet_id=child.id, status=AddressStatus.assigned))
    db.add(IPAddress(address="10.1.0.2", subnet_id=child.id, status=AddressStatus.reserved))
    db.commit()

    r = client.get("/api/subnets")
    by_id = {s["id"]: s for s in r.json()}

    parent_row = by_id[parent.id]
    child_row  = by_id[child.id]
    assert parent_row["rollup_used_count"] == parent_row["used_count"] + child_row["used_count"]
    assert parent_row["rollup_total_count"] == parent_row["total_count"] + child_row["total_count"]


def test_rollup_utilization_pct(client, db):
    subnet = Subnet(name="Single", cidr="10.0.0.0/24", ip_version=4)
    db.add(subnet)
    db.commit()

    r = client.get("/api/subnets")
    s = r.json()[0]
    assert s["rollup_utilization_pct"] == s["utilization_pct"]
