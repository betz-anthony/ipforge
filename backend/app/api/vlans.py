"""VLAN-001 — catalog endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import require_operator, get_current_user
from app.database import get_db
from app.models.user import User
from app.models.subnet import Subnet
from app.models.vlan import Vlan

router = APIRouter()

# IEEE 802.1Q: 12-bit VLAN ID, 0 and 4095 reserved.
VLAN_MIN = 1
VLAN_MAX = 4094


class VlanIn(BaseModel):
    vlan_id: int = Field(ge=VLAN_MIN, le=VLAN_MAX)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    notes: str | None = None


class VlanUpdate(BaseModel):
    vlan_id: int | None = Field(default=None, ge=VLAN_MIN, le=VLAN_MAX)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    notes: str | None = None


def _to_out(v: Vlan, subnet_count: int = 0) -> dict:
    return {
        "id": v.id,
        "vlan_id": v.vlan_id,
        "name": v.name,
        "description": v.description,
        "notes": v.notes,
        "subnet_count": subnet_count,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


@router.get("")
def list_vlans(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    vlans = db.query(Vlan).order_by(Vlan.vlan_id).all()
    # Aggregate subnet counts in one query.
    from sqlalchemy import func
    counts = dict(
        db.query(Subnet.vlan_id, func.count(Subnet.id))
        .filter(Subnet.vlan_id.isnot(None))
        .group_by(Subnet.vlan_id).all()
    )
    return [_to_out(v, counts.get(v.vlan_id, 0)) for v in vlans]


@router.get("/{vlan_pk}")
def get_vlan(vlan_pk: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.get(Vlan, vlan_pk)
    if v is None:
        raise HTTPException(404, "VLAN not found")
    count = db.query(Subnet).filter(Subnet.vlan_id == v.vlan_id).count()
    return _to_out(v, count)


@router.post("", status_code=201)
def create_vlan(body: VlanIn, current_user: User = Depends(require_operator),
                db: Session = Depends(get_db)):
    if db.query(Vlan).filter(Vlan.vlan_id == body.vlan_id).first():
        raise HTTPException(409, f"VLAN {body.vlan_id} already exists")
    v = Vlan(
        vlan_id=body.vlan_id,
        name=body.name.strip(),
        description=body.description,
        notes=body.notes,
    )
    db.add(v)
    db.flush()
    write_audit(db, current_user.username, "create", "vlan", str(v.id), f"vlan {v.vlan_id} ({v.name})")
    db.commit()
    db.refresh(v)
    return _to_out(v, 0)


@router.put("/{vlan_pk}")
def update_vlan(vlan_pk: int, body: VlanUpdate, current_user: User = Depends(require_operator),
                db: Session = Depends(get_db)):
    v = db.get(Vlan, vlan_pk)
    if v is None:
        raise HTTPException(404, "VLAN not found")
    if body.vlan_id is not None and body.vlan_id != v.vlan_id:
        clash = db.query(Vlan).filter(Vlan.vlan_id == body.vlan_id, Vlan.id != vlan_pk).first()
        if clash:
            raise HTTPException(409, f"VLAN {body.vlan_id} already exists")
        v.vlan_id = body.vlan_id
    if body.name is not None:
        v.name = body.name.strip()
    if body.description is not None:
        v.description = body.description
    if body.notes is not None:
        v.notes = body.notes
    write_audit(db, current_user.username, "update", "vlan", str(v.id), f"vlan {v.vlan_id} ({v.name})")
    db.commit()
    db.refresh(v)
    count = db.query(Subnet).filter(Subnet.vlan_id == v.vlan_id).count()
    return _to_out(v, count)


@router.delete("/{vlan_pk}", status_code=204)
def delete_vlan(vlan_pk: int, current_user: User = Depends(require_operator),
                db: Session = Depends(get_db)):
    v = db.get(Vlan, vlan_pk)
    if v is None:
        raise HTTPException(404, "VLAN not found")
    label = f"vlan {v.vlan_id} ({v.name})"
    write_audit(db, current_user.username, "delete", "vlan", str(v.id), label)
    db.delete(v)
    db.commit()
    return Response(status_code=204)
