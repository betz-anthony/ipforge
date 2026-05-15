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
