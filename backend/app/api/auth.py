from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.core.audit import write_audit
from app.core.time import utcnow
from app.core.deps import get_current_user
from app.core.ldap import authenticate_ldap
from app.core.security import verify_password, create_access_token, hash_password, generate_api_token, hash_api_token, API_TOKEN_DISPLAY_PREFIX_LEN
from app.models.api_token import ApiToken

router = APIRouter()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    _401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = db.query(User).filter_by(username=form.username).first()

    if user and user.hashed_password:
        # Local account: verify password locally, no LDAP fallback
        if not verify_password(form.password, user.hashed_password):
            raise _401
        if not user.enabled:
            raise _401
    else:
        # No local password — try LDAP
        ldap_role = authenticate_ldap(form.username, form.password)
        if ldap_role is None:
            raise _401
        if user is None:
            user = User(
                username=form.username,
                hashed_password="",
                role=ldap_role,
                auth_source="ldap",
                enabled=True,
            )
            db.add(user)
        else:
            user.role = ldap_role
        db.commit()
        db.refresh(user)
        if not user.enabled:
            raise _401

    token = create_access_token(sub=user.username, role=user.role)
    return TokenResponse(access_token=token, username=user.username, role=user.role)


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role}


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.hashed_password:
        raise HTTPException(400, "Password change is not available for LDAP accounts")
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(400, "Current password incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()


class TokenCreate(BaseModel):
    name: str = Field(..., max_length=64)
    read_only: bool = False
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def _expiry_in_future(cls, v: datetime | None) -> datetime | None:
        if v is not None and v < utcnow():
            raise ValueError("expires_at must be in the future")
        return v


class TokenRead(BaseModel):
    id: int
    name: str
    token_prefix: str
    read_only: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenCreated(TokenRead):
    token: str   # full plaintext value — returned only at creation


@router.get("/tokens", response_model=list[TokenRead])
def list_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ApiToken)
        .filter_by(user_id=current_user.id)
        .order_by(ApiToken.id)
        .all()
    )


@router.post("/tokens", response_model=TokenCreated, status_code=201)
def create_token(
    body: TokenCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Token name is required")
    value = generate_api_token()
    row = ApiToken(
        user_id=current_user.id,
        name=name,
        token_hash=hash_api_token(value),
        token_prefix=value[:API_TOKEN_DISPLAY_PREFIX_LEN],
        read_only=body.read_only,
        expires_at=body.expires_at,
    )
    db.add(row)
    db.flush()
    write_audit(db, current_user.username, "create", "api_token", str(row.id), name)
    db.commit()
    db.refresh(row)
    return TokenCreated(token=value, **TokenRead.model_validate(row).model_dump())


@router.delete("/tokens/{token_id}", status_code=204)
def delete_token(
    token_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(ApiToken).filter_by(id=token_id, user_id=current_user.id).first()
    if row is None:
        raise HTTPException(404, "Token not found")
    write_audit(db, current_user.username, "delete", "api_token", str(row.id), row.name)
    db.delete(row)
    db.commit()
