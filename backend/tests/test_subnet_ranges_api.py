from app.models.subnet import Subnet
from app.models.subnet_range import SubnetRange


def _subnet(db, cidr="10.0.0.0/24"):
    s = Subnet(name="N", cidr=cidr, ip_version=4 if "." in cidr else 6)
    db.add(s)
    db.commit()
    return s


def test_create_and_list_range(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/ranges", json={
        "start_ip": "10.0.0.10", "end_ip": "10.0.0.20", "kind": "dhcp_pool", "label": "pool",
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    rows = client.get(f"/api/v1/subnets/{s.id}/ranges").json()
    assert any(x["id"] == rid and x["kind"] == "dhcp_pool" for x in rows)


def test_range_out_of_cidr_rejected(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/ranges", json={
        "start_ip": "10.0.1.5", "end_ip": "10.0.1.9", "kind": "reserved",
    })
    assert r.status_code == 422


def test_range_start_after_end_rejected(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/ranges", json={
        "start_ip": "10.0.0.20", "end_ip": "10.0.0.10", "kind": "reserved",
    })
    assert r.status_code == 422


def test_range_overlap_conflict(client, db):
    s = _subnet(db)
    client.post(f"/api/v1/subnets/{s.id}/ranges", json={"start_ip": "10.0.0.10", "end_ip": "10.0.0.20", "kind": "reserved"})
    r = client.post(f"/api/v1/subnets/{s.id}/ranges", json={"start_ip": "10.0.0.15", "end_ip": "10.0.0.25", "kind": "reserved"})
    assert r.status_code == 409


def test_range_invalid_kind_rejected(client, db):
    s = _subnet(db)
    r = client.post(f"/api/v1/subnets/{s.id}/ranges", json={
        "start_ip": "10.0.0.10", "end_ip": "10.0.0.20", "kind": "bogus",
    })
    assert r.status_code == 422


def test_delete_range(client, db):
    s = _subnet(db)
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.0.0.1", end_ip="10.0.0.1", kind="gateway"))
    db.commit()
    rid = db.query(SubnetRange).first().id
    assert client.delete(f"/api/v1/subnets/{s.id}/ranges/{rid}").status_code == 204
    assert db.query(SubnetRange).count() == 0


def test_range_create_requires_operator(client_gr, db):
    s = _subnet(db)
    r = client_gr.post(f"/api/v1/subnets/{s.id}/ranges", json={
        "start_ip": "10.0.0.10", "end_ip": "10.0.0.20", "kind": "reserved",
    })
    assert r.status_code == 403
