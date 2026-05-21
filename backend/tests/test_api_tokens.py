from datetime import timedelta

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
    import pytest
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
    from app.core.security import generate_api_token
    token = generate_api_token()
    assert token.startswith("ipfg_")
    assert len(token) > 20


def test_generate_api_token_is_unique():
    from app.core.security import generate_api_token
    assert generate_api_token() != generate_api_token()


def test_hash_api_token_deterministic():
    from app.core.security import hash_api_token
    h1 = hash_api_token("ipfg_sample")
    h2 = hash_api_token("ipfg_sample")
    assert h1 == h2
    assert len(h1) == 64           # sha256 hex
    assert h1 != "ipfg_sample"


def test_is_api_token():
    from app.core.security import is_api_token
    assert is_api_token("ipfg_anything") is True
    assert is_api_token("eyJhbGciOi...") is False
