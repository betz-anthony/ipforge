from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import require_admin
from app.database import get_db
from app.models.subnet import Subnet
from app.models.subnet_grant import SubnetGrant
from app.models.user import User
from app.models.user_group import UserGroup

router = APIRouter()


class GrantCreate(BaseModel):
    user_id: int | None = None
    group_id: int | None = None
    subnet_id: int
    permission: Literal["view", "manage"]


def _grant_dict(g: SubnetGrant) -> dict:
    return {
        "id": g.id,
        "user_id": g.user_id,
        "group_id": g.group_id,
        "subnet_id": g.subnet_id,
        "permission": g.permission,
    }


@router.get("")
def list_grants(
    subnet_id: int | None = Query(None),
    user_id: int | None = Query(None),
    group_id: int | None = Query(None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(SubnetGrant)
    if subnet_id is not None:
        q = q.filter(SubnetGrant.subnet_id == subnet_id)
    if user_id is not None:
        q = q.filter(SubnetGrant.user_id == user_id)
    if group_id is not None:
        q = q.filter(SubnetGrant.group_id == group_id)
    return [_grant_dict(g) for g in q.order_by(SubnetGrant.id).all()]


@router.post("", status_code=201)
def create_grant(body: GrantCreate, _: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    if (body.user_id is None) == (body.group_id is None):
        raise HTTPException(400, "Exactly one of user_id or group_id must be set")
    if body.user_id is not None and db.get(User, body.user_id) is None:
        raise HTTPException(404, "User not found")
    if body.group_id is not None and db.get(UserGroup, body.group_id) is None:
        raise HTTPException(404, "Group not found")
    if db.get(Subnet, body.subnet_id) is None:
        raise HTTPException(404, "Subnet not found")

    dup = (
        db.query(SubnetGrant)
        .filter(
            SubnetGrant.subnet_id == body.subnet_id,
            SubnetGrant.user_id == body.user_id,
            SubnetGrant.group_id == body.group_id,
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(409, "A grant for this principal and subnet already exists")

    grant = SubnetGrant(
        user_id=body.user_id,
        group_id=body.group_id,
        subnet_id=body.subnet_id,
        permission=body.permission,
    )
    db.add(grant)
    db.flush()
    principal = f"user:{body.user_id}" if body.user_id else f"group:{body.group_id}"
    write_audit(db, "admin", "create", "subnet_grant", str(grant.id),
                f"{principal} {body.permission} subnet:{body.subnet_id}")
    db.commit()
    db.refresh(grant)
    return _grant_dict(grant)


@router.delete("/{grant_id}", status_code=204)
def delete_grant(grant_id: int, _: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    grant = db.get(SubnetGrant, grant_id)
    if grant is None:
        raise HTTPException(404, "Grant not found")
    write_audit(db, "admin", "delete", "subnet_grant", str(grant.id),
                f"subnet:{grant.subnet_id}")
    db.delete(grant)
    db.commit()
