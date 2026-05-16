from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.core.security import verify_password, create_access_token, hash_password
from app.core.deps import get_current_user
from app.core.ldap import authenticate_ldap

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
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(400, "Current password incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
