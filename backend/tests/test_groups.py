from app.models.user import User
from app.models.user_group import user_group_members


def test_create_and_list_group(client, db):
    r = client.post("/api/v1/groups", json={"name": "netops", "description": "Net ops"})
    assert r.status_code == 201
    assert r.json()["name"] == "netops"

    rows = client.get("/api/v1/groups").json()
    assert any(g["name"] == "netops" for g in rows)


def test_duplicate_group_name_rejected(client, db):
    client.post("/api/v1/groups", json={"name": "dup"})
    r = client.post("/api/v1/groups", json={"name": "dup"})
    assert r.status_code == 409


def test_update_and_delete_group(client, db):
    gid = client.post("/api/v1/groups", json={"name": "tmp"}).json()["id"]
    assert client.put(f"/api/v1/groups/{gid}", json={"description": "x"}).status_code == 200
    assert client.delete(f"/api/v1/groups/{gid}").status_code == 204
    assert all(g["id"] != gid for g in client.get("/api/v1/groups").json())


def test_add_and_remove_member(client, db):
    gid = client.post("/api/v1/groups", json={"name": "team"}).json()["id"]
    user = User(username="member", hashed_password="x", role="scoped", enabled=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    r = client.post(f"/api/v1/groups/{gid}/members", json={"user_id": user.id})
    assert r.status_code == 204
    members = client.get(f"/api/v1/groups/{gid}/members").json()
    assert any(m["id"] == user.id for m in members)

    r = client.request("DELETE", f"/api/v1/groups/{gid}/members", json={"user_id": user.id})
    assert r.status_code == 204
    assert client.get(f"/api/v1/groups/{gid}/members").json() == []
