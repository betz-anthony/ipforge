from app.models.user import User


def test_cannot_demote_last_admin(client, db):
    admin = User(username="onlyadmin", hashed_password="x", role="admin", enabled=True)
    db.add(admin)
    db.commit()

    r = client.put(f"/api/users/{admin.id}", json={"role": "readonly"})
    assert r.status_code == 400
    assert "last admin" in r.json()["detail"].lower()


def test_can_demote_admin_when_another_exists(client, db):
    a1 = User(username="admin1", hashed_password="x", role="admin", enabled=True)
    a2 = User(username="admin2", hashed_password="x", role="admin", enabled=True)
    db.add_all([a1, a2])
    db.commit()

    r = client.put(f"/api/users/{a1.id}", json={"role": "readonly"})
    assert r.status_code == 200
    assert r.json()["role"] == "readonly"


def test_disabled_admin_does_not_count_toward_last_admin(client, db):
    active = User(username="active-admin", hashed_password="x", role="admin", enabled=True)
    disabled = User(username="disabled-admin", hashed_password="x", role="admin", enabled=False)
    db.add_all([active, disabled])
    db.commit()

    # Demoting the only *enabled* admin must fail even though a disabled admin exists.
    r = client.put(f"/api/users/{active.id}", json={"role": "operator"})
    assert r.status_code == 400
