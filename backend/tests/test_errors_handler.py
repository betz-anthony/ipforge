from fastapi import APIRouter
from app.main import app
from fastapi.testclient import TestClient


def test_unhandled_exception_returns_generic_envelope():
    router = APIRouter()

    @router.get("/api/_boom")
    def _boom():
        raise RuntimeError("secret internal detail dc01\nstack trace line")

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/_boom")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"]["code"] == "internal_error"
    assert "secret internal detail" not in r.text   # no leak
