from app.config import settings as app_settings


def encrypt_value(plaintext: str) -> str:
    if not app_settings.secret_key or not plaintext:
        return plaintext
    from cryptography.fernet import Fernet
    return Fernet(app_settings.secret_key.encode()).encrypt(plaintext.encode()).decode()


def decrypt_value(value: str) -> str:
    if not app_settings.secret_key or not value:
        return value
    try:
        from cryptography.fernet import Fernet, InvalidToken
        return Fernet(app_settings.secret_key.encode()).decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value  # not encrypted (backward-compat plaintext)
