from app.core.access import resolve_access
from app.models.user import User
from app.models.subnet import Subnet
from app.models.user_group import UserGroup, user_group_members
from app.models.subnet_grant import SubnetGrant


def _user(db, role="scoped", name="u"):
    u = User(username=name, hashed_password="x", role=role, enabled=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _subnet(db, cidr, parent_id=None):
    s = Subnet(name=cidr, cidr=cidr, ip_version=4, parent_id=parent_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_global_role_has_global_flags(db):
    ctx = resolve_access(_user(db, role="operator"), db)
    assert ctx.global_read is True
    assert ctx.global_write is True


def test_readonly_is_read_only(db):
    ctx = resolve_access(_user(db, role="readonly"), db)
    assert ctx.global_read is True
    assert ctx.global_write is False


def test_scoped_user_has_no_global_access(db):
    ctx = resolve_access(_user(db, role="scoped"), db)
    assert ctx.global_read is False
    assert ctx.global_write is False


def test_direct_manage_grant(db):
    user = _user(db)
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="manage"))
    db.commit()
    ctx = resolve_access(user, db)
    assert ctx.can_read(sn.id) is True
    assert ctx.can_write(sn.id) is True


def test_view_grant_is_read_only(db):
    user = _user(db)
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="view"))
    db.commit()
    ctx = resolve_access(user, db)
    assert ctx.can_read(sn.id) is True
    assert ctx.can_write(sn.id) is False


def test_grant_inherits_to_descendant(db):
    user = _user(db)
    parent = _subnet(db, "10.0.0.0/16")
    child = _subnet(db, "10.0.1.0/24", parent_id=parent.id)
    db.add(SubnetGrant(user_id=user.id, subnet_id=parent.id, permission="manage"))
    db.commit()
    ctx = resolve_access(user, db)
    assert ctx.can_write(child.id) is True


def test_group_grant_applies_to_member(db):
    user = _user(db)
    sn = _subnet(db, "10.0.0.0/24")
    group = UserGroup(name="team")
    db.add(group)
    db.commit()
    db.execute(user_group_members.insert().values(user_id=user.id, group_id=group.id))
    db.add(SubnetGrant(group_id=group.id, subnet_id=sn.id, permission="manage"))
    db.commit()
    ctx = resolve_access(user, db)
    assert ctx.can_write(sn.id) is True


def test_no_grant_no_access(db):
    user = _user(db)
    sn = _subnet(db, "10.0.0.0/24")
    ctx = resolve_access(user, db)
    assert ctx.can_read(sn.id) is False
    assert ctx.can_write(sn.id) is False


def test_grant_is_additive_for_readonly(db):
    user = _user(db, role="readonly")
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="manage"))
    db.commit()
    ctx = resolve_access(user, db)
    assert ctx.can_write(sn.id) is True
    assert ctx.can_read(999) is True


def test_require_global_read_rejects_scoped():
    import pytest
    from fastapi import HTTPException
    from app.core.deps import require_global_read
    from app.models.user import User

    scoped = User(id=1, username="s", role="scoped", enabled=True, hashed_password="x")
    with pytest.raises(HTTPException) as exc:
        require_global_read(user=scoped)
    assert exc.value.status_code == 403

    operator = User(id=2, username="o", role="operator", enabled=True, hashed_password="x")
    assert require_global_read(user=operator) is operator
