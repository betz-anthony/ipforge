from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.subnet import Subnet
from app.models.subnet_grant import SubnetGrant
from app.models.user import User
from app.models.user_group import user_group_members

_GLOBAL_READ_ROLES = {"admin", "operator", "readonly"}
_GLOBAL_WRITE_ROLES = {"admin", "operator"}


@dataclass
class AccessContext:
    """Per-request resolved access. Grants are additive on top of the role."""
    global_read: bool
    global_write: bool
    viewable: set[int] = field(default_factory=set)
    manageable: set[int] = field(default_factory=set)

    def can_read(self, subnet_id: int) -> bool:
        return self.global_read or subnet_id in self.viewable

    def can_write(self, subnet_id: int) -> bool:
        return self.global_write or subnet_id in self.manageable

    def require_read(self, subnet_id: int) -> None:
        if not self.can_read(subnet_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this subnet")

    def require_write(self, subnet_id: int) -> None:
        if not self.can_write(subnet_id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No write access to this subnet")


def _descendants(db: Session, subnet_id: int) -> set[int]:
    """Return subnet_id plus every subnet beneath it in the parent hierarchy."""
    result = {subnet_id}
    frontier = [subnet_id]
    while frontier:
        rows = db.query(Subnet.id).filter(Subnet.parent_id.in_(frontier)).all()
        new = {r.id for r in rows} - result
        result |= new
        frontier = list(new)
    return result


def resolve_access(user: User, db: Session) -> AccessContext:
    ctx = AccessContext(
        global_read=user.role in _GLOBAL_READ_ROLES,
        global_write=user.role in _GLOBAL_WRITE_ROLES,
    )
    group_ids = [
        gid for (gid,) in
        db.query(user_group_members.c.group_id)
        .filter(user_group_members.c.user_id == user.id)
        .all()
    ]
    conditions = [SubnetGrant.user_id == user.id]
    if group_ids:
        conditions.append(SubnetGrant.group_id.in_(group_ids))
    grants = db.query(SubnetGrant).filter(or_(*conditions)).all()
    for grant in grants:
        subtree = _descendants(db, grant.subnet_id)
        ctx.viewable |= subtree
        if grant.permission == "manage":
            ctx.manageable |= subtree
    return ctx


def get_access_context(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccessContext:
    return resolve_access(user, db)
