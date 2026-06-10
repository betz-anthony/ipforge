import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User


def _scoped_client(db):
    scoped = User(id=8001, username="scoped-rt", role="scoped", enabled=True, hashed_password="x")

    def override_user():
        return scoped

    def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.mark.parametrize("path", ["/api/v1/dns/zones", "/api/v1/dhcp/scopes",
                                  "/api/v1/audit", "/api/v1/search?q=x"])
def test_scoped_user_blocked_from_global_routers(db, path):
    client = _scoped_client(db)
    try:
        r = client.get(path)
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_scoped_user_reaches_subnets(db):
    client = _scoped_client(db)
    try:
        r = client.get("/api/v1/subnets")
        assert r.status_code == 200   # reachable; contents filtered by a later task
    finally:
        app.dependency_overrides.clear()
