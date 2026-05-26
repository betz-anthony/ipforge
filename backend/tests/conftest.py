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


class _StickyClient:
    """TestClient wrapper that re-applies its own dependency overrides before
    every request, so multiple role-based clients can coexist in the same test
    without trampling each other's overrides."""

    def __init__(self, db, role: str):
        from app.models.user import User as _User
        self._user = _User(id=10000, username=f"test_{role}", role=role, enabled=True, hashed_password="x")
        self._db = db
        self._tc = TestClient(app)

    def _install(self):
        db = self._db
        user = self._user

        def override_get_db():
            yield db

        def override_get_current_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

    def get(self, *args, **kwargs):
        self._install(); return self._tc.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        self._install(); return self._tc.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        self._install(); return self._tc.put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        self._install(); return self._tc.patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._install(); return self._tc.delete(*args, **kwargs)


def _make_client_for_role(db, role: str):
    return _StickyClient(db, role)


@pytest.fixture
def client_admin(db):
    yield _make_client_for_role(db, "admin")
    app.dependency_overrides.clear()


@pytest.fixture
def client_operator(db):
    yield _make_client_for_role(db, "operator")
    app.dependency_overrides.clear()


@pytest.fixture
def client_gr(db):
    yield _make_client_for_role(db, "readonly")
    app.dependency_overrides.clear()


@pytest.fixture
def client_scoped(db):
    yield _make_client_for_role(db, "scoped")
    app.dependency_overrides.clear()


@pytest.fixture
def client_requester(db):
    yield _make_client_for_role(db, "requester")
    app.dependency_overrides.clear()
