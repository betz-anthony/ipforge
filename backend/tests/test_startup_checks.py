import app.main
from app.main import _ensure_jwt_secret
from app.config import DEFAULT_JWT_SECRET_KEY
from app.models.setting import AppSetting


def test_ensure_jwt_secret_keeps_env_value(db, monkeypatch):
    monkeypatch.setattr(app.main.app_settings, "jwt_secret_key", "operator-set-key")
    _ensure_jwt_secret(db)
    assert app.main.app_settings.jwt_secret_key == "operator-set-key"
    # An operator-provided key is not persisted to the DB.
    assert db.get(AppSetting, "jwt_secret_key") is None


def test_ensure_jwt_secret_generates_when_default(db, monkeypatch):
    monkeypatch.setattr(app.main.app_settings, "jwt_secret_key", DEFAULT_JWT_SECRET_KEY)
    _ensure_jwt_secret(db)
    key = app.main.app_settings.jwt_secret_key
    assert key and key != DEFAULT_JWT_SECRET_KEY
    row = db.get(AppSetting, "jwt_secret_key")
    assert row is not None and row.value == key


def test_ensure_jwt_secret_generates_when_empty(db, monkeypatch):
    monkeypatch.setattr(app.main.app_settings, "jwt_secret_key", "")
    _ensure_jwt_secret(db)
    assert app.main.app_settings.jwt_secret_key not in ("", DEFAULT_JWT_SECRET_KEY)


def test_ensure_jwt_secret_reuses_persisted(db, monkeypatch):
    db.add(AppSetting(key="jwt_secret_key", value="persisted-key-xyz"))
    db.commit()
    monkeypatch.setattr(app.main.app_settings, "jwt_secret_key", "")
    _ensure_jwt_secret(db)
    assert app.main.app_settings.jwt_secret_key == "persisted-key-xyz"
