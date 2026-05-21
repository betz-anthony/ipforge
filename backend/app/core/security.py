from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def create_access_token(sub: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": sub, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


_API_TOKEN_PREFIX = "ipfg_"
API_TOKEN_DISPLAY_PREFIX_LEN = 12   # chars of the token kept for display ("ipfg_" + 7)


def generate_api_token() -> str:
    """Return a new plaintext API token. Shown to the user exactly once."""
    return _API_TOKEN_PREFIX + secrets.token_urlsafe(30)


def hash_api_token(token: str) -> str:
    """Return the SHA-256 hex digest used to store and look up an API token."""
    return hashlib.sha256(token.encode()).hexdigest()


def is_api_token(credential: str) -> bool:
    """True if a bearer credential is an API token rather than a JWT."""
    return credential.startswith(_API_TOKEN_PREFIX)
