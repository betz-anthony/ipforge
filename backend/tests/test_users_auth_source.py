from app.models.user import User


def test_user_list_includes_auth_source(client, db):
    db.add(User(username="ldapuser", hashed_password="", role="readonly",
                auth_source="ldap", enabled=True))
    db.commit()
    r = client.get("/api/users")
    assert r.status_code == 200
    users = r.json()
    ldap_user = next((u for u in users if u["username"] == "ldapuser"), None)
    assert ldap_user is not None
    assert ldap_user["auth_source"] == "ldap"
