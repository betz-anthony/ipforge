from unittest.mock import patch
from app.main import app
from app.core.deps import get_current_user
from app.models.user import User

# Pre-computed bcrypt hash for "pass1234".  We use a raw bcrypt hash rather
# than calling hash_password() because passlib's bcrypt backend init is broken
# on Python 3.13 with newer bcrypt wheels (detect_wrap_bug ValueError).
# The raw `bcrypt` library works fine; passlib can still *verify* against it.
_PASS1234_HASH = "$2b$12$NprlbmEAtO9ab8afyIdSS.7XyzjLtpHOgKwXNn3YiU8UxcNx1NCuK"


def test_local_user_still_works(client, db):
    db.add(User(username="localuser", hashed_password=_PASS1234_HASH,
                role="operator", enabled=True))
    db.commit()
    r = client.post("/api/auth/login",
                    data={"username": "localuser", "password": "pass1234"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    assert r.json()["username"] == "localuser"


def test_local_wrong_password_rejected(client, db):
    db.add(User(username="localuser", hashed_password=_PASS1234_HASH,
                role="operator", enabled=True))
    db.commit()
    r = client.post("/api/auth/login",
                    data={"username": "localuser", "password": "wrong"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 401


def test_ldap_user_creates_shadow_account(client, db):
    with patch("app.api.auth.authenticate_ldap", return_value="operator"):
        r = client.post("/api/auth/login",
                        data={"username": "ldapuser", "password": "ldappass"},
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    assert r.json()["role"] == "operator"
    shadow = db.query(User).filter_by(username="ldapuser").first()
    assert shadow is not None
    assert shadow.hashed_password == ""
    assert shadow.auth_source == "ldap"


def test_ldap_role_refreshed_on_login(client, db):
    db.add(User(username="ldapuser", hashed_password="", role="readonly",
                auth_source="ldap", enabled=True))
    db.commit()
    with patch("app.api.auth.authenticate_ldap", return_value="admin"):
        r = client.post("/api/auth/login",
                        data={"username": "ldapuser", "password": "ldappass"},
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    db.expire_all()
    shadow = db.query(User).filter_by(username="ldapuser").first()
    assert shadow.role == "admin"


def test_ldap_disabled_user_rejected(client, db):
    db.add(User(username="ldapuser", hashed_password="", role="operator",
                auth_source="ldap", enabled=False))
    db.commit()
    with patch("app.api.auth.authenticate_ldap", return_value="operator"):
        r = client.post("/api/auth/login",
                        data={"username": "ldapuser", "password": "ldappass"},
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 401


def test_ldap_failed_auth_rejected(client, db):
    with patch("app.api.auth.authenticate_ldap", return_value=None):
        r = client.post("/api/auth/login",
                        data={"username": "unknown", "password": "bad"},
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 401


def test_change_password_rejected_for_ldap_user(client, db):
    ldap_user = User(id=99, username="ldapuser", hashed_password="",
                     role="readonly", auth_source="ldap", enabled=True)
    app.dependency_overrides[get_current_user] = lambda: ldap_user
    r = client.post("/api/auth/change-password",
                    json={"current_password": "x", "new_password": "newpass1234"})
    assert r.status_code == 400
    assert "LDAP" in r.json()["detail"]
