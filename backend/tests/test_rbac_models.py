from app.models.user import User
from app.models.subnet import Subnet
from app.models.user_group import UserGroup, user_group_members
from app.models.subnet_grant import SubnetGrant


def test_group_and_membership(db):
    user = User(username="g-user", hashed_password="x", role="scoped", enabled=True)
    group = UserGroup(name="netops", description="Network ops")
    db.add_all([user, group])
    db.commit()
    db.execute(user_group_members.insert().values(user_id=user.id, group_id=group.id))
    db.commit()

    rows = db.execute(
        user_group_members.select().where(user_group_members.c.user_id == user.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].group_id == group.id


def test_subnet_grant_roundtrip(db):
    user = User(username="grantee", hashed_password="x", role="scoped", enabled=True)
    subnet = Subnet(name="s", cidr="10.0.0.0/24", ip_version=4)
    db.add_all([user, subnet])
    db.commit()
    grant = SubnetGrant(user_id=user.id, subnet_id=subnet.id, permission="manage")
    db.add(grant)
    db.commit()
    db.refresh(grant)

    assert grant.id is not None
    assert grant.group_id is None
    assert grant.permission == "manage"
