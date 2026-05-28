"""CUSTOM-FIELDS-001 — admin-defined custom fields + tags."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.models.custom_field import CustomFieldDef, CustomFieldValue, Tag, TagAssignment

router = APIRouter()

FieldType = Literal["text", "select", "date"]
EntityType = Literal["subnet", "address"]


class FieldDefIn(BaseModel):
    entity_type: EntityType
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=255)
    field_type: FieldType
    options: list[str] | None = None


class FieldDefUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    options: list[str] | None = None


def _def_out(f: CustomFieldDef) -> dict:
    return {
        "id": f.id,
        "entity_type": f.entity_type,
        "name": f.name,
        "label": f.label,
        "field_type": f.field_type,
        "options": json.loads(f.options) if f.options else None,
    }


@router.get("")
def list_field_defs(
    entity_type: EntityType | None = Query(None),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(CustomFieldDef)
    if entity_type is not None:
        q = q.filter(CustomFieldDef.entity_type == entity_type)
    return [_def_out(f) for f in q.order_by(CustomFieldDef.entity_type, CustomFieldDef.name).all()]


@router.post("", status_code=201)
def create_field_def(
    body: FieldDefIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.field_type == "select" and not body.options:
        raise HTTPException(400, "A select field requires at least one option")
    if db.query(CustomFieldDef).filter_by(entity_type=body.entity_type, name=body.name).first():
        raise HTTPException(409, f"Field {body.name!r} already exists for {body.entity_type}")
    f = CustomFieldDef(
        entity_type=body.entity_type,
        name=body.name,
        label=body.label,
        field_type=body.field_type,
        options=json.dumps(body.options) if body.options else None,
    )
    db.add(f)
    db.flush()
    write_audit(db, current_user.username, "create", "custom_field", str(f.id), f"{f.entity_type}.{f.name}")
    db.commit()
    db.refresh(f)
    return _def_out(f)


@router.put("/{field_id}")
def update_field_def(
    field_id: int,
    body: FieldDefUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    f = db.get(CustomFieldDef, field_id)
    if f is None:
        raise HTTPException(404, "Field not found")
    if body.label is not None:
        f.label = body.label
    if body.options is not None:
        if f.field_type == "select" and not body.options:
            raise HTTPException(400, "A select field requires at least one option")
        f.options = json.dumps(body.options)
    write_audit(db, current_user.username, "update", "custom_field", str(f.id), f"{f.entity_type}.{f.name}")
    db.commit()
    db.refresh(f)
    return _def_out(f)


@router.delete("/{field_id}", status_code=204)
def delete_field_def(
    field_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    f = db.get(CustomFieldDef, field_id)
    if f is None:
        raise HTTPException(404, "Field not found")
    db.query(CustomFieldValue).filter_by(field_id=field_id).delete(synchronize_session=False)
    write_audit(db, current_user.username, "delete", "custom_field", str(f.id), f"{f.entity_type}.{f.name}")
    db.delete(f)
    db.commit()
    return Response(status_code=204)
