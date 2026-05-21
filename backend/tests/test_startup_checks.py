import pytest

import app.main
from app.main import _check_jwt_secret
from app.config import DEFAULT_JWT_SECRET_KEY


def test_check_jwt_secret_rejects_default(monkeypatch):
    monkeypatch.setattr(app.main.app_settings, "jwt_secret_key", DEFAULT_JWT_SECRET_KEY)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        _check_jwt_secret()


def test_check_jwt_secret_rejects_empty(monkeypatch):
    monkeypatch.setattr(app.main.app_settings, "jwt_secret_key", "")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        _check_jwt_secret()


def test_check_jwt_secret_accepts_custom(monkeypatch):
    monkeypatch.setattr(app.main.app_settings, "jwt_secret_key", "a-strong-random-secret")
    _check_jwt_secret()  # must not raise
