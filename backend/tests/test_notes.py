def test_notes_field_in_address_response(client):
    r = client.post("/api/v1/subnets", json={"name": "Net", "cidr": "10.0.0.0/24"})
    assert r.status_code == 201
    subnet_id = r.json()["id"]

    r = client.post("/api/v1/addresses", json={"address": "10.0.0.1", "subnet_id": subnet_id})
    assert r.status_code == 201
    assert "notes" in r.json()
    assert r.json()["notes"] is None


def test_update_address_notes(client):
    r = client.post("/api/v1/subnets", json={"name": "Net", "cidr": "10.0.0.0/24"})
    subnet_id = r.json()["id"]
    r = client.post("/api/v1/addresses", json={"address": "10.0.0.1", "subnet_id": subnet_id})
    addr_id = r.json()["id"]

    r = client.put(f"/api/v1/addresses/{addr_id}", json={"notes": "rack 3 slot 2"})
    assert r.status_code == 200
    assert r.json()["notes"] == "rack 3 slot 2"


def test_notes_field_in_subnet_response(client):
    r = client.post("/api/v1/subnets", json={"name": "Net", "cidr": "10.0.0.0/24"})
    assert r.status_code == 201
    assert "notes" in r.json()
    assert r.json()["notes"] is None


def test_update_subnet_notes(client):
    r = client.post("/api/v1/subnets", json={"name": "Net", "cidr": "10.0.0.0/24"})
    subnet_id = r.json()["id"]

    r = client.put(f"/api/v1/subnets/{subnet_id}", json={"notes": "data center A"})
    assert r.status_code == 200
    assert r.json()["notes"] == "data center A"


def test_get_address_by_ip(client):
    r = client.post("/api/v1/subnets", json={"name": "Net", "cidr": "10.0.0.0/24"})
    subnet_id = r.json()["id"]
    client.post("/api/v1/addresses", json={
        "address": "10.0.0.5", "subnet_id": subnet_id, "notes": "server rack A"
    })

    r = client.get("/api/v1/addresses/by-ip/10.0.0.5")
    assert r.status_code == 200
    assert r.json()["address"] == "10.0.0.5"
    assert r.json()["notes"] == "server rack A"


def test_get_address_by_ip_not_found(client):
    r = client.get("/api/v1/addresses/by-ip/192.168.99.99")
    assert r.status_code == 404
