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


def test_suggest_parent_returns_containing_subnets(client, db):
    db.add(Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4))
    db.add(Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4))
    db.add(Subnet(name="Unrelated", cidr="192.168.0.0/16", ip_version=4))
    db.commit()

    r = client.get("/api/subnets/suggest-parent", params={"cidr": "10.1.1.0/24"})
    assert r.status_code == 200
    names = [s["name"] for s in r.json()]
    assert "Corp" in names
    assert "Prod" in names
    assert "Unrelated" not in names


def test_suggest_parent_sorted_most_specific_first(client, db):
    db.add(Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4))
    db.add(Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4))
    db.commit()

    r = client.get("/api/subnets/suggest-parent", params={"cidr": "10.1.1.0/24"})
    names = [s["name"] for s in r.json()]
    assert names[0] == "Prod"   # /16 before /8


def test_suggest_parent_invalid_cidr_returns_empty(client, db):
    r = client.get("/api/subnets/suggest-parent", params={"cidr": "notacidr"})
    assert r.status_code == 200
    assert r.json() == []


def test_create_subnet_with_valid_parent(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.commit()

    r = client.post("/api/subnets", json={
        "name": "Prod", "cidr": "10.1.0.0/16", "parent_id": parent.id
    })
    assert r.status_code == 201
    assert r.json()["parent_id"] == parent.id


def test_create_subnet_parent_not_found_returns_404(client, db):
    r = client.post("/api/subnets", json={
        "name": "Prod", "cidr": "10.1.0.0/16", "parent_id": 9999
    })
    assert r.status_code == 404


def test_create_subnet_parent_cidr_mismatch_returns_422(client, db):
    parent = Subnet(name="Unrelated", cidr="192.168.0.0/16", ip_version=4)
    db.add(parent)
    db.commit()

    r = client.post("/api/subnets", json={
        "name": "Prod", "cidr": "10.1.0.0/16", "parent_id": parent.id
    })
    assert r.status_code == 422


def test_delete_subnet_with_children_returns_409(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.flush()
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4, parent_id=parent.id)
    db.add(child)
    db.commit()

    r = client.delete(f"/api/subnets/{parent.id}")
    assert r.status_code == 409


def test_delete_subnet_leaf_succeeds(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.flush()
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4, parent_id=parent.id)
    db.add(child)
    db.commit()

    r = client.delete(f"/api/subnets/{child.id}")
    assert r.status_code == 204


def test_update_subnet_reparent(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.flush()
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4)
    db.add(child)
    db.commit()

    r = client.put(f"/api/subnets/{child.id}", json={"parent_id": parent.id})
    assert r.status_code == 200
    assert r.json()["parent_id"] == parent.id


def test_update_subnet_make_root(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.flush()
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4, parent_id=parent.id)
    db.add(child)
    db.commit()

    # Explicit null = make root
    r = client.put(f"/api/subnets/{child.id}", json={"parent_id": None})
    assert r.status_code == 200
    assert r.json()["parent_id"] is None


def test_update_subnet_omit_parent_id_leaves_unchanged(client, db):
    parent = Subnet(name="Corp", cidr="10.0.0.0/8", ip_version=4)
    db.add(parent)
    db.flush()
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4, parent_id=parent.id)
    db.add(child)
    db.commit()

    # No parent_id in body = leave unchanged
    r = client.put(f"/api/subnets/{child.id}", json={"name": "Production"})
    assert r.status_code == 200
    assert r.json()["parent_id"] == parent.id


def test_cycle_detection_rejects_descendant_as_parent(client, db):
    root = Subnet(name="Root", cidr="10.0.0.0/8", ip_version=4)
    db.add(root)
    db.flush()
    child = Subnet(name="Child", cidr="10.1.0.0/16", ip_version=4, parent_id=root.id)
    db.add(child)
    db.flush()
    grandchild = Subnet(name="GrandChild", cidr="10.1.1.0/24", ip_version=4, parent_id=child.id)
    db.add(grandchild)
    db.commit()

    # Try to set root's parent to grandchild (cycle)
    r = client.put(f"/api/subnets/{root.id}", json={"parent_id": grandchild.id})
    assert r.status_code == 422


def test_self_parent_returns_422(client, db):
    subnet = Subnet(name="Net", cidr="10.0.0.0/8", ip_version=4)
    db.add(subnet)
    db.commit()

    r = client.put(f"/api/subnets/{subnet.id}", json={"parent_id": subnet.id})
    assert r.status_code == 422


def test_update_subnet_reparent_cidr_mismatch_returns_422(client, db):
    child = Subnet(name="Prod", cidr="10.1.0.0/16", ip_version=4)
    unrelated = Subnet(name="Other", cidr="192.168.0.0/16", ip_version=4)
    db.add(child)
    db.add(unrelated)
    db.commit()

    r = client.put(f"/api/subnets/{child.id}", json={"parent_id": unrelated.id})
    assert r.status_code == 422


def test_subnet_stores_provider_names(client, db):
    r = client.post("/api/subnets", json={
        "name": "test", "cidr": "10.9.0.0/24",
        "dns_provider_name": "msdns-prod",
        "dhcp_provider_name": "msdhcp-prod",
    })
    assert r.status_code == 201
    assert r.json()["dns_provider_name"] == "msdns-prod"
    assert r.json()["dhcp_provider_name"] == "msdhcp-prod"
