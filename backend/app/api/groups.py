from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.models.user_group import UserGroup, user_group_members

router = APIRouter()


class GroupCreate(BaseModel):
    name: str = Field(..., max_length=64)
    description: str | None = None


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = None


class MemberRef(BaseModel):
    user_id: int


def _group_dict(g: UserGroup) -> dict:
    return {"id": g.id, "name": g.name, "description": g.description}


@router.get("")
def list_groups(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_group_dict(g) for g in db.query(UserGroup).order_by(UserGroup.name).all()]


@router.post("", status_code=201)
def create_group(body: GroupCreate, current_user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Group name is required")
    if db.query(UserGroup).filter(UserGroup.name == name).first():
        raise HTTPException(409, f"Group {name!r} already exists")
    group = UserGroup(name=name, description=body.description)
    db.add(group)
    db.flush()
    write_audit(db, current_user.username, "create", "user_group", str(group.id), name)
    db.commit()
    db.refresh(group)
    return _group_dict(group)


@router.put("/{group_id}")
def update_group(group_id: int, body: GroupUpdate, current_user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    group = db.get(UserGroup, group_id)
    if group is None:
        raise HTTPException(404, "Group not found")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Group name is required")
        clash = db.query(UserGroup).filter(
            UserGroup.name == name, UserGroup.id != group_id
        ).first()
        if clash:
            raise HTTPException(409, f"Group {name!r} already exists")
        group.name = name
    if body.description is not None:
        group.description = body.description
    write_audit(db, current_user.username, "update", "user_group", str(group.id), group.name)
    db.commit()
    db.refresh(group)
    return _group_dict(group)


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, current_user: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    group = db.get(UserGroup, group_id)
    if group is None:
        raise HTTPException(404, "Group not found")
    write_audit(db, current_user.username, "delete", "user_group", str(group.id), group.name)
    db.delete(group)
    db.commit()


@router.get("/{group_id}/members")
def list_members(group_id: int, _: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    if db.get(UserGroup, group_id) is None:
        raise HTTPException(404, "Group not found")
    member_ids = [
        uid for (uid,) in
        db.query(user_group_members.c.user_id)
        .filter(user_group_members.c.group_id == group_id)
        .all()
    ]
    users = db.query(User).filter(User.id.in_(member_ids)).all() if member_ids else []
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]


@router.post("/{group_id}/members", status_code=204)
def add_member(group_id: int, body: MemberRef, current_user: User = Depends(require_admin),
               db: Session = Depends(get_db)):
    if db.get(UserGroup, group_id) is None:
        raise HTTPException(404, "Group not found")
    if db.get(User, body.user_id) is None:
        raise HTTPException(404, "User not found")
    exists = db.execute(
        user_group_members.select()
        .where(user_group_members.c.group_id == group_id)
        .where(user_group_members.c.user_id == body.user_id)
    ).first()
    if exists is None:
        db.execute(user_group_members.insert().values(
            group_id=group_id, user_id=body.user_id))
        write_audit(db, current_user.username, "update", "user_group", str(group_id), f"add member {body.user_id}")
        db.commit()


@router.delete("/{group_id}/members", status_code=204)
def remove_member(group_id: int, body: MemberRef, current_user: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    db.execute(
        user_group_members.delete()
        .where(user_group_members.c.group_id == group_id)
        .where(user_group_members.c.user_id == body.user_id)
    )
    write_audit(db, current_user.username, "update", "user_group", str(group_id), f"remove member {body.user_id}")
    db.commit()
