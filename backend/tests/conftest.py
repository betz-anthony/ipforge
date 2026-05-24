import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Passlib's bcrypt backend runs a detect_wrap_bug() check during initialisation
# that sends a 256-byte dummy password through bcrypt.hashpw().  Newer bcrypt
# wheels (4.x) reject passwords longer than 72 bytes, causing a ValueError that
# crashes the backend init.  Truncate the input in hashpw() so the probe
# succeeds; this has no effect on real passwords used in tests (all ≤ 72 B).
import bcrypt as _bcrypt_mod
_orig_hashpw = _bcrypt_mod.hashpw
def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
    return _orig_hashpw(password[:72], salt)
_bcrypt_mod.hashpw = _safe_hashpw

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.core.deps import get_current_user
from app.models.user import User

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

_MOCK_USER = User(id=9999, username="test_admin", role="admin", enabled=True, hashed_password="x")


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def db_session(db):
    """Alias for the db fixture, used by alerting tests."""
    yield db


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    def override_get_current_user():
        return _MOCK_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()
