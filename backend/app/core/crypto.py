from cryptography.fernet import Fernet, InvalidToken

# Fernet tokens always start with this prefix (base64url of version byte 0x80).
_FERNET_PREFIX = "gAAAAA"


def _fernet() -> Fernet | None:
    from app.config import settings
    key = settings.secret_key
    if not key:
        return None
    return Fernet(key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt plaintext. No-op if SECRET_KEY not configured or value already encrypted."""
    f = _fernet()
    if f is None or not plaintext or plaintext.startswith(_FERNET_PREFIX):
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_secret(value: str) -> str:
    """Decrypt a Fernet token. Returns value unchanged if not encrypted or no key."""
    if not value or not value.startswith(_FERNET_PREFIX):
        return value  # plaintext passthrough — handles pre-encryption rows
    f = _fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken:
        return value  # wrong key or corrupted — return as-is rather than crash


def encrypt_existing_secrets(db) -> int:
    """Encrypt any plaintext secret values still stored in the database.

    Idempotent: already-encrypted values are skipped, and nothing happens when
    SECRET_KEY is unconfigured. Returns the count of values newly encrypted.
    """
    if _fernet() is None:
        return 0

    import json
    from app.models.provider_config import ProviderConfig, SECRET_FIELDS
    from app.models.setting import AppSetting

    # Mirrors LDAP_SECRET_KEYS in app.api.settings.
    ldap_secret_keys = ("ldap_bind_password",)
    changed = 0

    for row in db.query(ProviderConfig).all():
        cfg = json.loads(row.config or "{}")
        row_changed = False
        for field in SECRET_FIELDS.get(row.provider_type, []):
            val = cfg.get(field)
            if val:
                enc = encrypt_secret(val)
                if enc != val:
                    cfg[field] = enc
                    row_changed = True
                    changed += 1
        if row_changed:
            row.config = json.dumps(cfg)

    for row in db.query(AppSetting).filter(AppSetting.key.in_(ldap_secret_keys)).all():
        if row.value:
            enc = encrypt_secret(row.value)
            if enc != row.value:
                row.value = enc
                changed += 1

    if changed:
        db.commit()
    return changed
