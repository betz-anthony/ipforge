"""CUSTOM-FIELDS-001 — tag catalog."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import get_current_user, require_operator, require_admin
from app.database import get_db
from app.models.user import User
from app.models.custom_field import Tag, TagAssignment

router = APIRouter()


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


def _tag_out(t: Tag, count: int = 0) -> dict:
    return {"id": t.id, "name": t.name, "usage_count": count}


@router.get("")
def list_tags(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    counts = dict(
        db.query(TagAssignment.tag_id, func.count(TagAssignment.id))
        .group_by(TagAssignment.tag_id).all()
    )
    return [_tag_out(t, counts.get(t.id, 0)) for t in db.query(Tag).order_by(Tag.name).all()]


@router.post("", status_code=201)
def create_tag(
    body: TagIn,
    current_user: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if db.query(Tag).filter(func.lower(Tag.name) == name.lower()).first():
        raise HTTPException(409, f"Tag {name!r} already exists")
    t = Tag(name=name)
    db.add(t)
    db.flush()
    write_audit(db, current_user.username, "create", "tag", str(t.id), t.name)
    db.commit()
    db.refresh(t)
    return _tag_out(t)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(
    tag_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    t = db.get(Tag, tag_id)
    if t is None:
        raise HTTPException(404, "Tag not found")
    db.query(TagAssignment).filter_by(tag_id=tag_id).delete(synchronize_session=False)
    write_audit(db, current_user.username, "delete", "tag", str(t.id), t.name)
    db.delete(t)
    db.commit()
    return Response(status_code=204)
