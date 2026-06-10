"""Tests for credential encryption at rest (SECRETS-001)."""
import json
import pytest
from cryptography.fernet import Fernet
from unittest.mock import patch

from app.core.crypto import encrypt_secret, decrypt_secret, encrypt_existing_secrets
from app.models.provider_config import ProviderConfig


# ── crypto unit tests ────────────────────────────────────────────────────────

def _test_key() -> str:
    return Fernet.generate_key().decode()


def test_encrypt_decrypt_roundtrip():
    key = _test_key()
    with patch("app.core.crypto._fernet", return_value=Fernet(key.encode())):
        ct = encrypt_secret("hunter2")
        assert ct != "hunter2"
        assert decrypt_secret(ct) == "hunter2"


def test_encrypt_empty_string_unchanged():
    key = _test_key()
    with patch("app.core.crypto._fernet", return_value=Fernet(key.encode())):
        assert encrypt_secret("") == ""


def test_decrypt_plaintext_passthrough():
    """Plaintext values (no Fernet prefix) pass through unchanged — handles pre-encryption rows."""
    assert decrypt_secret("plaintext_password") == "plaintext_password"


def test_decrypt_empty_string_unchanged():
    assert decrypt_secret("") == ""


def test_no_key_encrypt_is_noop():
    """If SECRET_KEY not configured, encrypt returns plaintext."""
    with patch("app.core.crypto._fernet", return_value=None):
        assert encrypt_secret("secret") == "secret"


def test_invalid_key_is_noop_not_crash(monkeypatch):
    """A malformed SECRET_KEY disables encryption instead of crashing."""
    import app.config
    from app.core import crypto
    monkeypatch.setattr(app.config.settings, "secret_key", "not-a-valid-fernet-key")
    crypto._invalid_key_logged = False
    assert crypto._fernet() is None
    assert encrypt_secret("hunter2") == "hunter2"   # plaintext passthrough
    assert decrypt_secret("hunter2") == "hunter2"


def test_no_key_decrypt_is_noop():
    """If SECRET_KEY not configured and value looks encrypted, return as-is."""
    key = _test_key()
    f = Fernet(key.encode())
    ct = f.encrypt(b"secret").decode()
    with patch("app.core.crypto._fernet", return_value=None):
        assert decrypt_secret(ct) == ct


def test_wrong_key_decrypt_returns_as_is():
    """Wrong key on decrypt returns ciphertext unchanged rather than raising."""
    key1 = _test_key()
    key2 = _test_key()
    ct = Fernet(key1.encode()).encrypt(b"secret").decode()
    with patch("app.core.crypto._fernet", return_value=Fernet(key2.encode())):
        result = decrypt_secret(ct)
    assert result == ct  # not "secret", not an exception


# ── integration: provider_configs API ───────────────────────────────────────

def test_create_provider_config_encrypts_secret(client, db):
    key = _test_key()
    with patch("app.core.crypto._fernet", return_value=Fernet(key.encode())):
        r = client.post("/api/v1/provider-configs", json={
            "category": "dns",
            "provider_type": "msdns",
            "name": "test-msdns",
            "config": {"winrm_host": "dc1", "winrm_user": "admin", "winrm_password": "hunter2"},
        })
    assert r.status_code == 201

    row = db.query(ProviderConfig).filter_by(name="test-msdns").first()
    stored = json.loads(row.config)
    assert stored["winrm_password"] != "hunter2"
    assert stored["winrm_password"].startswith("gAAAAA")
    assert stored["winrm_host"] == "dc1"  # non-secret unchanged


def test_create_provider_config_no_key_stores_plaintext(client, db):
    with patch("app.core.crypto._fernet", return_value=None):
        r = client.post("/api/v1/provider-configs", json={
            "category": "dns",
            "provider_type": "msdns",
            "name": "test-msdns-plain",
            "config": {"winrm_host": "dc1", "winrm_password": "hunter2"},
        })
    assert r.status_code == 201
    row = db.query(ProviderConfig).filter_by(name="test-msdns-plain").first()
    stored = json.loads(row.config)
    assert stored["winrm_password"] == "hunter2"


def test_update_provider_config_blank_secret_keeps_existing(client, db):
    key = _test_key()
    f = Fernet(key.encode())
    with patch("app.core.crypto._fernet", return_value=f):
        r = client.post("/api/v1/provider-configs", json={
            "category": "dns",
            "provider_type": "msdns",
            "name": "test-update",
            "config": {"winrm_host": "dc1", "winrm_password": "original"},
        })
    assert r.status_code == 201
    config_id = r.json()["id"]

    with patch("app.core.crypto._fernet", return_value=f):
        r2 = client.put(f"/api/v1/provider-configs/{config_id}", json={
            "config": {"winrm_host": "dc2", "winrm_password": ""},
        })
    assert r2.status_code == 200

    row = db.query(ProviderConfig).filter_by(id=config_id).first()
    stored = json.loads(row.config)
    assert stored["winrm_host"] == "dc2"
    assert f.decrypt(stored["winrm_password"].encode()).decode() == "original"


def test_api_response_masks_secret(client, db):
    key = _test_key()
    with patch("app.core.crypto._fernet", return_value=Fernet(key.encode())):
        r = client.post("/api/v1/provider-configs", json={
            "category": "dns",
            "provider_type": "msdns",
            "name": "test-masked",
            "config": {"winrm_host": "dc1", "winrm_password": "hunter2"},
        })
    assert r.status_code == 201
    data = r.json()
    assert data["config"]["winrm_password"] == ""
    assert data["secrets_set"]["winrm_password"] is True


def test_plaintext_in_db_still_decrypts_for_provider(db):
    """Pre-encryption rows (plaintext in DB) pass through decrypt_secret unchanged."""
    from app.core.crypto import decrypt_secret
    assert decrypt_secret("oldplaintextpassword") == "oldplaintextpassword"


# ── encrypt_existing_secrets (plaintext migration) ───────────────────────────

def test_encrypt_existing_secrets_encrypts_plaintext(db):
    key = _test_key()
    f = Fernet(key.encode())
    db.add(ProviderConfig(
        category="dns", provider_type="msdns", name="legacy-msdns",
        config=json.dumps({"winrm_host": "dc1", "winrm_password": "plainpw"}),
    ))
    db.commit()

    with patch("app.core.crypto._fernet", return_value=f):
        n = encrypt_existing_secrets(db)

    assert n == 1
    stored = json.loads(db.query(ProviderConfig).filter_by(name="legacy-msdns").first().config)
    assert stored["winrm_password"].startswith("gAAAAA")
    assert f.decrypt(stored["winrm_password"].encode()).decode() == "plainpw"
    assert stored["winrm_host"] == "dc1"  # non-secret field untouched


def test_encrypt_existing_secrets_idempotent(db):
    key = _test_key()
    f = Fernet(key.encode())
    db.add(ProviderConfig(
        category="dns", provider_type="msdns", name="enc-msdns",
        config=json.dumps({"winrm_password": "plainpw"}),
    ))
    db.commit()

    with patch("app.core.crypto._fernet", return_value=f):
        first  = encrypt_existing_secrets(db)
        second = encrypt_existing_secrets(db)

    assert first == 1
    assert second == 0  # already encrypted — no-op on re-run


def test_encrypt_existing_secrets_noop_without_key(db):
    db.add(ProviderConfig(
        category="dns", provider_type="msdns", name="nokey-msdns",
        config=json.dumps({"winrm_password": "plainpw"}),
    ))
    db.commit()

    with patch("app.core.crypto._fernet", return_value=None):
        n = encrypt_existing_secrets(db)

    assert n == 0
    stored = json.loads(db.query(ProviderConfig).filter_by(name="nokey-msdns").first().config)
    assert stored["winrm_password"] == "plainpw"  # untouched without a key
