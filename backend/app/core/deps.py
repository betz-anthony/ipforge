from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_api_token, is_api_token
from app.core.time import utcnow
from app.database import get_db
from app.models.api_token import ApiToken
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_LAST_USED_THROTTLE = timedelta(minutes=5)


def _user_from_api_token(request: Request, token: str, db: Session) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    row = db.query(ApiToken).filter_by(token_hash=hash_api_token(token)).first()
    if row is None:
        raise unauthorized
    now = utcnow()
    if row.expires_at is not None and row.expires_at < now:
        raise unauthorized
    user = db.query(User).filter(User.id == row.user_id, User.enabled == True).first()  # noqa: E712
    if user is None:
        raise unauthorized
    if row.read_only and request.method not in _SAFE_METHODS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This API token is read-only")
    if row.last_used_at is None or now - row.last_used_at >= _LAST_USED_THROTTLE:
        row.last_used_at = now
        db.commit()
    return user


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if is_api_token(token):
        return _user_from_api_token(request, token, db)

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        username: str = payload.get("sub", "")
        if not username:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.username == username, User.enabled == True).first()  # noqa: E712
    if not user:
        raise credentials_exc
    return user


def require_operator(user: User = Depends(get_current_user)) -> User:
    if user.role == "readonly":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator or admin role required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user
