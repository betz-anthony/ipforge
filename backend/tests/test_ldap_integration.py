from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.core.security import create_access_token


def test_ldap_login_token_grants_access(client, db):
    """Full flow: LDAP login -> JWT -> protected endpoint."""
    # Temporarily remove the get_current_user mock so the real JWT validation
    # runs for the /me call.  We restore it afterwards so the fixture teardown
    # (app.dependency_overrides.clear()) is unaffected.
    saved = app.dependency_overrides.pop(get_current_user, None)
    try:
        with patch("app.api.auth.authenticate_ldap", return_value="operator"):
            login_r = client.post(
                "/api/auth/login",
                data={"username": "aduser", "password": "adpass"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert login_r.status_code == 200
        token = login_r.json()["access_token"]

        me_r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_r.status_code == 200
        assert me_r.json()["username"] == "aduser"
        assert me_r.json()["role"] == "operator"
    finally:
        if saved is not None:
            app.dependency_overrides[get_current_user] = saved


def test_local_login_unaffected_by_ldap_enabled(client, db):
    """Local accounts work normally even when LDAP is enabled."""
    from app.config import settings
    from app.models.user import User

    settings.ldap_enabled = True
    # Use a pre-computed hash for "pass1234" to avoid passlib bcrypt init issues
    _LOCALPASS_HASH = "$2b$12$NprlbmEAtO9ab8afyIdSS.7XyzjLtpHOgKwXNn3YiU8UxcNx1NCuK"
    db.add(User(username="localadmin", hashed_password=_LOCALPASS_HASH,
                role="admin", enabled=True))
    db.commit()

    r = client.post(
        "/api/auth/login",
        data={"username": "localadmin", "password": "pass1234"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    settings.ldap_enabled = False
