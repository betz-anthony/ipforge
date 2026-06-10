from app.models.user import User
from app.models.subnet import Subnet
from app.models.user_group import UserGroup


def _user(db, name="grantee"):
    u = User(username=name, hashed_password="x", role="scoped", enabled=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _subnet(db, cidr="10.0.0.0/24"):
    s = Subnet(name=cidr, cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_create_user_grant(client, db):
    user = _user(db)
    sn = _subnet(db)
    r = client.post("/api/v1/subnet-grants", json={
        "user_id": user.id, "subnet_id": sn.id, "permission": "manage",
    })
    assert r.status_code == 201
    assert r.json()["permission"] == "manage"


def test_create_group_grant(client, db):
    group = UserGroup(name="team")
    db.add(group)
    db.commit()
    db.refresh(group)
    sn = _subnet(db)
    r = client.post("/api/v1/subnet-grants", json={
        "group_id": group.id, "subnet_id": sn.id, "permission": "view",
    })
    assert r.status_code == 201


def test_grant_requires_exactly_one_principal(client, db):
    sn = _subnet(db)
    user = _user(db)
    r = client.post("/api/v1/subnet-grants", json={"subnet_id": sn.id, "permission": "view"})
    assert r.status_code == 400
    r = client.post("/api/v1/subnet-grants", json={
        "user_id": user.id, "group_id": 1, "subnet_id": sn.id, "permission": "view",
    })
    assert r.status_code == 400


def test_duplicate_grant_rejected(client, db):
    user = _user(db)
    sn = _subnet(db)
    body = {"user_id": user.id, "subnet_id": sn.id, "permission": "manage"}
    assert client.post("/api/v1/subnet-grants", json=body).status_code == 201
    assert client.post("/api/v1/subnet-grants", json=body).status_code == 409


def test_invalid_permission_rejected(client, db):
    user = _user(db)
    sn = _subnet(db)
    r = client.post("/api/v1/subnet-grants", json={
        "user_id": user.id, "subnet_id": sn.id, "permission": "owner",
    })
    assert r.status_code == 422


def test_list_and_delete_grant(client, db):
    user = _user(db)
    sn = _subnet(db)
    gid = client.post("/api/v1/subnet-grants", json={
        "user_id": user.id, "subnet_id": sn.id, "permission": "view",
    }).json()["id"]

    rows = client.get(f"/api/v1/subnet-grants?subnet_id={sn.id}").json()
    assert len(rows) == 1

    assert client.delete(f"/api/v1/subnet-grants/{gid}").status_code == 204
    assert client.get(f"/api/v1/subnet-grants?subnet_id={sn.id}").json() == []
