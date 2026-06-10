import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.subnet_grant import SubnetGrant


def _client(db, user):
    def override_user():
        return user

    def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _scoped_user(db, name="scoped-e"):
    u = User(username=name, hashed_password="x", role="scoped", enabled=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _subnet(db, cidr):
    s = Subnet(name=cidr, cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_scoped_subnet_list_only_granted(db):
    user = _scoped_user(db)
    granted = _subnet(db, "10.0.0.0/24")
    _subnet(db, "10.9.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=granted.id, permission="view"))
    db.commit()
    client = _client(db, user)
    try:
        rows = client.get("/api/v1/subnets").json()
        assert {r["cidr"] for r in rows} == {"10.0.0.0/24"}
    finally:
        app.dependency_overrides.clear()


def test_scoped_get_ungranted_subnet_403(db):
    user = _scoped_user(db)
    other = _subnet(db, "10.9.0.0/24")
    client = _client(db, user)
    try:
        assert client.get(f"/api/v1/subnets/{other.id}").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_scoped_view_grant_cannot_write_subnet(db):
    user = _scoped_user(db)
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="view"))
    db.commit()
    client = _client(db, user)
    try:
        r = client.put(f"/api/v1/subnets/{sn.id}", json={"name": "renamed"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_scoped_manage_grant_can_write_subnet(db):
    user = _scoped_user(db)
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="manage"))
    db.commit()
    client = _client(db, user)
    try:
        r = client.put(f"/api/v1/subnets/{sn.id}", json={"name": "renamed"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_scoped_cannot_create_subnet(db):
    user = _scoped_user(db)
    client = _client(db, user)
    try:
        r = client.post("/api/v1/subnets", json={"name": "n", "cidr": "10.5.0.0/24"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_scoped_address_list_only_granted_subnet(db):
    user = _scoped_user(db)
    granted = _subnet(db, "10.0.0.0/24")
    other = _subnet(db, "10.9.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=granted.id, permission="manage"))
    db.add(IPAddress(address="10.0.0.5", subnet_id=granted.id, status=AddressStatus.assigned))
    db.add(IPAddress(address="10.9.0.5", subnet_id=other.id, status=AddressStatus.assigned))
    db.commit()
    client = _client(db, user)
    try:
        rows = client.get("/api/v1/addresses").json()["items"]
        assert {r["address"] for r in rows} == {"10.0.0.5"}
    finally:
        app.dependency_overrides.clear()


def test_scoped_address_write_requires_manage(db):
    user = _scoped_user(db)
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="view"))
    db.commit()
    client = _client(db, user)
    try:
        r = client.post("/api/v1/addresses", json={"address": "10.0.0.7", "subnet_id": sn.id})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_operator_unaffected(db):
    op_user = User(username="op-e", hashed_password="x", role="operator", enabled=True)
    db.add(op_user)
    db.commit()
    _subnet(db, "10.0.0.0/24")
    client = _client(db, op_user)
    try:
        assert len(client.get("/api/v1/subnets").json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_scoped_allocate_requires_manage(db):
    user = _scoped_user(db, name="scoped-alloc")
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="view"))
    db.commit()
    client = _client(db, user)
    try:
        r = client.post(f"/api/v1/subnets/{sn.id}/allocate", json={"hostname": "h1"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_scoped_allocate_with_manage_succeeds(db):
    user = _scoped_user(db, name="scoped-alloc-ok")
    sn = _subnet(db, "10.0.0.0/24")
    db.add(SubnetGrant(user_id=user.id, subnet_id=sn.id, permission="manage"))
    db.commit()
    client = _client(db, user)
    try:
        r = client.post(f"/api/v1/subnets/{sn.id}/allocate", json={"hostname": "h1"})
        assert r.status_code in (200, 201)
    finally:
        app.dependency_overrides.clear()
