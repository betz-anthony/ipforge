from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import generate_api_token, hash_api_token
from app.core.time import utcnow
from app.models.api_token import ApiToken
from app.models.user import User


def _make_user(db, username="tokuser", role="admin", enabled=True):
    u = User(username=username, hashed_password="x", role=role, enabled=enabled)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_api_token_row_roundtrip(db):
    user = _make_user(db)
    row = ApiToken(
        user_id=user.id,
        name="ci",
        token_hash="a" * 64,
        token_prefix="ipfg_abc123",
        read_only=True,
        expires_at=utcnow() + timedelta(days=30),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    fetched = db.query(ApiToken).filter_by(id=row.id).first()
    assert fetched is not None
    assert fetched.user_id == user.id
    assert fetched.read_only is True
    assert fetched.token_prefix == "ipfg_abc123"
    assert fetched.last_used_at is None
    assert fetched.created_at is not None


def test_token_hash_unique_constraint(db):
    from sqlalchemy.exc import IntegrityError
    user = _make_user(db)
    dup_hash = "d" * 64
    db.add(ApiToken(user_id=user.id, name="a", token_hash=dup_hash, token_prefix="ipfg_a"))
    db.commit()
    db.add(ApiToken(user_id=user.id, name="b", token_hash=dup_hash, token_prefix="ipfg_b"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_generate_api_token_has_prefix():
    token = generate_api_token()
    assert token.startswith("ipfg_")
    assert len(token) > 20


def test_generate_api_token_is_unique():
    assert generate_api_token() != generate_api_token()


def test_hash_api_token_deterministic():
    h1 = hash_api_token("ipfg_sample")
    h2 = hash_api_token("ipfg_sample")
    assert h1 == h2
    assert len(h1) == 64           # sha256 hex
    assert h1 != "ipfg_sample"


def test_is_api_token():
    from app.core.security import is_api_token
    assert is_api_token("ipfg_anything") is True
    assert is_api_token("eyJhbGciOi...") is False


def _make_token(db, user, value, read_only=False, expires_at=None):
    row = ApiToken(
        user_id=user.id,
        name="t",
        token_hash=hash_api_token(value),
        token_prefix=value[:12],
        read_only=read_only,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def noauth_client(db):
    """TestClient with only the DB overridden — real authentication runs."""
    from app.main import app
    from app.database import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_valid_api_token_authenticates(noauth_client, db):
    user = _make_user(db)
    value = generate_api_token()
    _make_token(db, user, value)
    r = noauth_client.get("/api/subnets", headers={"Authorization": f"Bearer {value}"})
    assert r.status_code == 200


def test_unknown_api_token_rejected(noauth_client, db):
    r = noauth_client.get("/api/subnets",
                          headers={"Authorization": "Bearer ipfg_does_not_exist"})
    assert r.status_code == 401


def test_expired_api_token_rejected(noauth_client, db):
    user = _make_user(db)
    value = generate_api_token()
    _make_token(db, user, value, expires_at=utcnow() - timedelta(seconds=1))
    r = noauth_client.get("/api/subnets", headers={"Authorization": f"Bearer {value}"})
    assert r.status_code == 401


def test_api_token_for_disabled_user_rejected(noauth_client, db):
    user = _make_user(db, username="off", enabled=False)
    value = generate_api_token()
    _make_token(db, user, value)
    r = noauth_client.get("/api/subnets", headers={"Authorization": f"Bearer {value}"})
    assert r.status_code == 401


def test_read_only_token_allows_get(noauth_client, db):
    user = _make_user(db)
    value = generate_api_token()
    _make_token(db, user, value, read_only=True)
    r = noauth_client.get("/api/subnets", headers={"Authorization": f"Bearer {value}"})
    assert r.status_code == 200


def test_read_only_token_blocks_write(noauth_client, db):
    user = _make_user(db)
    value = generate_api_token()
    _make_token(db, user, value, read_only=True)
    r = noauth_client.post(
        "/api/subnets",
        json={"name": "ro-test", "cidr": "10.9.0.0/24"},
        headers={"Authorization": f"Bearer {value}"},
    )
    assert r.status_code == 403


def test_valid_api_token_writes_last_used_at(noauth_client, db):
    user = _make_user(db, username="lu_user")
    value = generate_api_token()
    row = _make_token(db, user, value)
    assert row.last_used_at is None
    noauth_client.get("/api/subnets", headers={"Authorization": f"Bearer {value}"})
    db.refresh(row)
    assert row.last_used_at is not None


def test_create_token_returns_value_once(client, db):
    r = client.post("/api/auth/tokens", json={"name": "ci-pipeline"})
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("ipfg_")
    assert body["name"] == "ci-pipeline"
    assert body["read_only"] is False
    row = db.query(ApiToken).filter_by(id=body["id"]).first()
    assert row.token_hash == hash_api_token(body["token"])


def test_list_tokens_excludes_value(client, db):
    client.post("/api/auth/tokens", json={"name": "one"})
    r = client.get("/api/auth/tokens")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert "token" not in items[0]
    assert items[0]["name"] == "one"


def test_delete_own_token(client, db):
    created = client.post("/api/auth/tokens", json={"name": "tmp"}).json()
    r = client.delete(f"/api/auth/tokens/{created['id']}")
    assert r.status_code == 204
    assert db.query(ApiToken).filter_by(id=created["id"]).first() is None


def test_cannot_delete_other_users_token(client, db):
    other = _make_user(db, username="other")
    value = generate_api_token()
    row = _make_token(db, other, value)
    r = client.delete(f"/api/auth/tokens/{row.id}")
    assert r.status_code == 404
    assert db.query(ApiToken).filter_by(id=row.id).first() is not None
