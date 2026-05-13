from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.core.security import hash_password
from app.core.deps import require_admin, get_current_user

router = APIRouter()

ROLES = {"readonly", "operator", "admin"}


def _row(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "enabled": u.enabled}


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "readonly"


class UserUpdate(BaseModel):
    role: str | None = None
    enabled: bool | None = None
    password: str | None = None


@router.get("")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_row(u) for u in db.query(User).order_by(User.id).all()]


@router.post("", status_code=201)
def create_user(body: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(400, f"Role must be one of: {', '.join(sorted(ROLES))}")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, f"Username {body.username!r} already exists")
    u = User(username=body.username, hashed_password=hash_password(body.password), role=body.role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return _row(u)


@router.put("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(400, f"Role must be one of: {', '.join(sorted(ROLES))}")
        u.role = body.role
    if body.enabled is not None:
        if u.id == current_user.id and not body.enabled:
            raise HTTPException(400, "Cannot disable your own account")
        u.enabled = body.enabled
    if body.password is not None:
        if len(body.password) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        u.hashed_password = hash_password(body.password)
    db.commit()
    db.refresh(u)
    return _row(u)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == current_user.id:
        raise HTTPException(400, "Cannot delete your own account")
    db.delete(u)
    db.commit()
