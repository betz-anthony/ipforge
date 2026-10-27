"""ALLOC-POOLS-001 — named allocation pools within a subnet."""
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.address import IPAddress, AddressStatus
from app.models.subnet import Subnet
from app.models.subnet_grant import SubnetGrant
from app.models.subnet_range import SubnetRange
from app.models.user import User


def _subnet(db, cidr="10.10.0.0/22", name="servers"):
    s = Subnet(name=name, cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _pool(client, subnet_id, name="linux", start="10.10.3.1", end="10.10.3.254", **extra):
    return client.post(f"/api/v1/subnets/{subnet_id}/pools",
                       json={"name": name, "start_ip": start, "end_ip": end, **extra})


def _allocate(client, subnet_id, hostname, **extra):
    return client.post(f"/api/v1/subnets/{subnet_id}/allocate",
                       json={"hostname": hostname, **extra})


# ── CRUD and validation ──────────────────────────────────────────────────────

def test_create_and_list_pool(client, db):
    s = _subnet(db)
    r = _pool(client, s.id, description="Linux hosts")
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "linux"
    rows = client.get(f"/api/v1/subnets/{s.id}/pools").json()
    assert [p["name"] for p in rows] == ["linux"]
    assert rows[0]["total"] == 254


def test_pools_listed_in_numeric_order(client, db):
    s = _subnet(db)
    _pool(client, s.id, "b-pool", "10.10.2.1", "10.10.2.50")
    _pool(client, s.id, "a-pool", "10.10.1.100", "10.10.1.120")
    names = [p["name"] for p in client.get(f"/api/v1/subnets/{s.id}/pools").json()]
    assert names == ["a-pool", "b-pool"]


def test_name_is_normalized_to_lowercase(client, db):
    s = _subnet(db)
    assert _pool(client, s.id, "Linux").json()["name"] == "linux"


def test_invalid_pool_name_rejected(client, db):
    s = _subnet(db)
    assert _pool(client, s.id, "has space").status_code == 422
    assert _pool(client, s.id, "-leading-dash").status_code == 422


def test_pool_outside_subnet_rejected(client, db):
    s = _subnet(db)
    assert _pool(client, s.id, start="10.20.0.1", end="10.20.0.9").status_code == 422


def test_pool_reversed_range_rejected(client, db):
    s = _subnet(db)
    assert _pool(client, s.id, start="10.10.3.50", end="10.10.3.10").status_code == 422


def test_pool_wrong_ip_version_rejected(client, db):
    s = _subnet(db)
    assert _pool(client, s.id, start="2001:db8::1", end="2001:db8::9").status_code == 422


def test_duplicate_pool_name_rejected(client, db):
    s = _subnet(db)
    assert _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.9").status_code == 201
    assert _pool(client, s.id, "LINUX", "10.10.2.1", "10.10.2.9").status_code == 409


def test_overlapping_pools_rejected(client, db):
    s = _subnet(db)
    assert _pool(client, s.id, "a", "10.10.3.1", "10.10.3.50").status_code == 201
    r = _pool(client, s.id, "b", "10.10.3.40", "10.10.3.90")
    assert r.status_code == 409
    assert "a" in r.json()["detail"]


def test_pool_may_overlap_reserved_range(client, db):
    s = _subnet(db)
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.10.3.1", end_ip="10.10.3.1", kind="gateway"))
    db.commit()
    assert _pool(client, s.id).status_code == 201


def test_update_pool(client, db):
    s = _subnet(db)
    pid = _pool(client, s.id).json()["id"]
    r = client.put(f"/api/v1/subnets/{s.id}/pools/{pid}",
                   json={"name": "linux", "start_ip": "10.10.3.10", "end_ip": "10.10.3.20"})
    assert r.status_code == 200, r.text
    assert r.json()["start_ip"] == "10.10.3.10"


def test_update_pool_keeps_own_range_from_conflicting(client, db):
    s = _subnet(db)
    pid = _pool(client, s.id, "a", "10.10.3.1", "10.10.3.50").json()["id"]
    r = client.put(f"/api/v1/subnets/{s.id}/pools/{pid}",
                   json={"name": "a", "start_ip": "10.10.3.1", "end_ip": "10.10.3.60"})
    assert r.status_code == 200, r.text


def test_delete_pool_leaves_addresses(client, db):
    s = _subnet(db)
    pid = _pool(client, s.id).json()["id"]
    db.add(IPAddress(address="10.10.3.5", subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()
    assert client.delete(f"/api/v1/subnets/{s.id}/pools/{pid}").status_code == 204
    assert client.get(f"/api/v1/subnets/{s.id}/pools").json() == []
    assert db.query(IPAddress).filter_by(address="10.10.3.5").count() == 1


def test_pool_unknown_subnet_404(client, db):
    assert client.get("/api/v1/subnets/999/pools").status_code == 404


# ── allocation ───────────────────────────────────────────────────────────────

def test_allocate_from_pool(client, db):
    s = _subnet(db)
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.254")
    r = _allocate(client, s.id, "lx1", pool="linux")
    assert r.status_code == 201, r.text
    assert r.json()["address"] == "10.10.3.2"  # .1 skipped by the existing rule
    assert r.json()["pool"] == "linux"


def test_allocate_pool_name_is_case_insensitive(client, db):
    s = _subnet(db)
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.254")
    assert _allocate(client, s.id, "lx1", pool="LINUX").json()["address"] == "10.10.3.2"


def test_allocate_without_pool_unchanged(client, db):
    s = _subnet(db)
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.254")
    r = _allocate(client, s.id, "any")
    assert r.json()["address"] == "10.10.0.2"
    assert r.json()["pool"] is None


def test_allocate_pool_skips_taken_and_reserved(client, db):
    s = _subnet(db)
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.254")
    db.add(IPAddress(address="10.10.3.2", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.10.3.3", end_ip="10.10.3.4", kind="reserved"))
    db.commit()
    assert _allocate(client, s.id, "lx1", pool="linux").json()["address"] == "10.10.3.5"


def test_allocate_pool_skips_ip_held_under_parent_subnet(client, db):
    parent = _subnet(db, "10.10.0.0/16", "parent")
    child = _subnet(db, "10.10.0.0/22", "child")
    child.parent_id = parent.id
    db.add(IPAddress(address="10.10.3.2", subnet_id=parent.id, status=AddressStatus.assigned))
    db.commit()
    _pool(client, child.id, "linux", "10.10.3.1", "10.10.3.254")
    assert _allocate(client, child.id, "lx1", pool="linux").json()["address"] == "10.10.3.3"


def test_allocate_unknown_pool_422(client, db):
    s = _subnet(db)
    r = _allocate(client, s.id, "lx1", pool="nope")
    assert r.status_code == 422
    assert "nope" in r.json()["detail"]


def test_allocate_pool_exhausted_409(client, db):
    s = _subnet(db)
    _pool(client, s.id, "tiny", "10.10.3.2", "10.10.3.3")
    assert _allocate(client, s.id, "a", pool="tiny").status_code == 201
    assert _allocate(client, s.id, "b", pool="tiny").status_code == 201
    r = _allocate(client, s.id, "c", pool="tiny")
    assert r.status_code == 409
    assert 'pool "tiny" exhausted' in r.json()["detail"]


def test_allocate_pool_ignores_other_pools_space(client, db):
    s = _subnet(db)
    _pool(client, s.id, "win", "10.10.1.1", "10.10.1.254")
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.254")
    assert _allocate(client, s.id, "w1", pool="win").json()["address"] == "10.10.1.2"
    assert _allocate(client, s.id, "l1", pool="linux").json()["address"] == "10.10.3.2"


def test_allocate_idempotent_inside_pool(client, db):
    s = _subnet(db)
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.254")
    first = _allocate(client, s.id, "lx1", pool="linux")
    again = _allocate(client, s.id, "lx1", pool="linux")
    assert again.status_code == 200
    assert again.json()["address"] == first.json()["address"]
    assert again.json()["pool"] == "linux"


def test_allocate_existing_hostname_outside_pool_409(client, db):
    s = _subnet(db)
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.254")
    first = _allocate(client, s.id, "lx1")  # no pool -> 10.10.0.2
    assert first.json()["address"] == "10.10.0.2"
    r = _allocate(client, s.id, "lx1", pool="linux")
    assert r.status_code == 409
    assert "10.10.0.2" in r.json()["detail"]


def test_allocate_ipv6_pool(client, db):
    s = Subnet(name="v6", cidr="2001:db8::/64", ip_version=6)
    db.add(s)
    db.commit()
    r = client.post(f"/api/v1/subnets/{s.id}/pools",
                    json={"name": "lab", "start_ip": "2001:db8::100", "end_ip": "2001:db8::1ff"})
    assert r.status_code == 201, r.text
    got = _allocate(client, s.id, "h6", pool="lab")
    assert got.status_code == 201, got.text
    assert got.json()["address"] == "2001:db8::100"


# ── utilization ──────────────────────────────────────────────────────────────

def test_pool_utilization_counts(client, db):
    s = _subnet(db)
    _pool(client, s.id, "linux", "10.10.3.1", "10.10.3.20")
    db.add(IPAddress(address="10.10.3.5", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(IPAddress(address="10.10.3.6", subnet_id=s.id, status=AddressStatus.available))
    db.add(IPAddress(address="10.10.9.9", subnet_id=s.id, status=AddressStatus.assigned))  # outside
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.10.3.10", end_ip="10.10.3.12", kind="reserved"))
    db.commit()
    p = client.get(f"/api/v1/subnets/{s.id}/pools").json()[0]
    assert p["total"] == 20
    assert p["used"] == 1       # 'available' rows are not in use
    assert p["reserved"] == 3
    assert p["free"] == 16


# ── access control ───────────────────────────────────────────────────────────

def _scoped_client(db, user):
    app.dependency_overrides[get_current_user] = lambda: user
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def _scoped_user(db):
    u = User(username="scoped-pools", hashed_password="x", role="scoped", enabled=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_scoped_user_without_grant_cannot_list_pools(db):
    s = _subnet(db)
    c = _scoped_client(db, _scoped_user(db))
    try:
        assert c.get(f"/api/v1/subnets/{s.id}/pools").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_scoped_view_grant_can_list_but_not_create(db):
    s = _subnet(db)
    u = _scoped_user(db)
    db.add(SubnetGrant(user_id=u.id, subnet_id=s.id, permission="view"))
    db.commit()
    c = _scoped_client(db, u)
    try:
        assert c.get(f"/api/v1/subnets/{s.id}/pools").status_code == 200
        r = c.post(f"/api/v1/subnets/{s.id}/pools",
                   json={"name": "x", "start_ip": "10.10.3.1", "end_ip": "10.10.3.9"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_scoped_manage_grant_can_create_pool(db):
    s = _subnet(db)
    u = _scoped_user(db)
    db.add(SubnetGrant(user_id=u.id, subnet_id=s.id, permission="manage"))
    db.commit()
    c = _scoped_client(db, u)
    try:
        r = c.post(f"/api/v1/subnets/{s.id}/pools",
                   json={"name": "x", "start_ip": "10.10.3.1", "end_ip": "10.10.3.9"})
        assert r.status_code == 201, r.text
    finally:
        app.dependency_overrides.clear()
