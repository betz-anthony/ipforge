"""VLAN-001 — API tests."""
import pytest


def test_list_empty(client_admin):
    r = client_admin.get("/api/v1/vlans")
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_list(client_admin):
    r = client_admin.post("/api/v1/vlans", json={"vlan_id": 100, "name": "Prod"})
    assert r.status_code == 201
    body = r.json()
    assert body["vlan_id"] == 100
    assert body["name"] == "Prod"
    assert body["subnet_count"] == 0
    assert "id" in body

    r = client_admin.get("/api/v1/vlans")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["vlan_id"] == 100


def test_create_duplicate_vlan_id_rejected(client_admin):
    client_admin.post("/api/v1/vlans", json={"vlan_id": 200, "name": "A"})
    r = client_admin.post("/api/v1/vlans", json={"vlan_id": 200, "name": "B"})
    assert r.status_code == 409


@pytest.mark.parametrize("bad", [0, 4095, 5000, -1])
def test_vlan_id_range_validated(client_admin, bad):
    r = client_admin.post("/api/v1/vlans", json={"vlan_id": bad, "name": "x"})
    assert r.status_code == 422


def test_update_vlan(client_admin):
    created = client_admin.post("/api/v1/vlans", json={"vlan_id": 10, "name": "Old"}).json()
    r = client_admin.put(f"/api/v1/vlans/{created['id']}", json={"name": "New", "description": "renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "New"
    assert r.json()["description"] == "renamed"
    assert r.json()["vlan_id"] == 10  # unchanged


def test_update_vlan_id_clash_rejected(client_admin):
    a = client_admin.post("/api/v1/vlans", json={"vlan_id": 1, "name": "A"}).json()
    client_admin.post("/api/v1/vlans", json={"vlan_id": 2, "name": "B"})
    r = client_admin.put(f"/api/v1/vlans/{a['id']}", json={"vlan_id": 2})
    assert r.status_code == 409


def test_delete_vlan(client_admin):
    created = client_admin.post("/api/v1/vlans", json={"vlan_id": 50, "name": "Drop"}).json()
    r = client_admin.delete(f"/api/v1/vlans/{created['id']}")
    assert r.status_code == 204
    assert client_admin.get(f"/api/v1/vlans/{created['id']}").status_code == 404


def test_subnet_count_aggregated(client_admin):
    # Create VLAN + two subnets carrying that vlan_id; expect count = 2.
    client_admin.post("/api/v1/vlans", json={"vlan_id": 42, "name": "X"})
    client_admin.post("/api/v1/subnets", json={"name": "s1", "cidr": "10.0.1.0/24", "vlan_id": 42})
    client_admin.post("/api/v1/subnets", json={"name": "s2", "cidr": "10.0.2.0/24", "vlan_id": 42})
    rows = client_admin.get("/api/v1/vlans").json()
    row = next(r for r in rows if r["vlan_id"] == 42)
    assert row["subnet_count"] == 2


def test_readonly_can_list_cannot_write(client_gr):
    # client_gr is a readonly user; allowed to list (any auth user can read)
    assert client_gr.get("/api/v1/vlans").status_code == 200
    # Writes blocked (require_operator)
    r = client_gr.post("/api/v1/vlans", json={"vlan_id": 99, "name": "nope"})
    assert r.status_code == 403


def test_operator_can_write(client_operator):
    r = client_operator.post("/api/v1/vlans", json={"vlan_id": 77, "name": "Ops"})
    assert r.status_code == 201
