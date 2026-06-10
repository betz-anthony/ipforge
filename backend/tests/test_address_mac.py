from app.models.subnet import Subnet
from app.models.address import IPAddress


def _subnet(db):
    s = Subnet(name="test", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    return s


def test_create_address_normalizes_mac(client, db):
    s = _subnet(db)
    r = client.post("/api/v1/addresses", json={
        "address": "10.0.0.5", "subnet_id": s.id,
        "mac_address": "AA-BB-CC-DD-EE-FF",
    })
    assert r.status_code == 201
    assert r.json()["mac_address"] == "aa:bb:cc:dd:ee:ff"


def test_create_address_rejects_bad_mac(client, db):
    s = _subnet(db)
    r = client.post("/api/v1/addresses", json={
        "address": "10.0.0.6", "subnet_id": s.id,
        "mac_address": "not-a-mac",
    })
    assert r.status_code == 422


def test_update_address_normalizes_mac(client, db):
    s = _subnet(db)
    addr = IPAddress(address="10.0.0.7", subnet_id=s.id)
    db.add(addr)
    db.commit()
    r = client.put(f"/api/v1/addresses/{addr.id}", json={"mac_address": "aabb.ccdd.eeff"})
    assert r.status_code == 200
    assert r.json()["mac_address"] == "aa:bb:cc:dd:ee:ff"


def test_create_address_blank_mac_becomes_null(client, db):
    s = _subnet(db)
    r = client.post("/api/v1/addresses", json={
        "address": "10.0.0.8", "subnet_id": s.id, "mac_address": "",
    })
    assert r.status_code == 201
    assert r.json()["mac_address"] is None
