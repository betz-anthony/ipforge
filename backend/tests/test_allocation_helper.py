"""Test that _do_allocate works directly (not via HTTP route)."""
import pytest
from app.api.allocation import _do_allocate, AllocateRequest
from app.models.subnet import Subnet
from app.models.user import User


def test_do_allocate_basic(db):
    s = Subnet(cidr="10.0.0.0/29", name="test")
    db.add(s); db.commit()
    body = AllocateRequest(hostname="host1", description="x")
    user = User(id=1, username="alice", role="operator", enabled=True, hashed_password="x")
    result = _do_allocate(db, s.id, body, user, access=None)
    assert result["address"].startswith("10.0.0.")
    assert result["hostname"] == "host1"
    assert result["is_new"] is True


def test_do_allocate_missing_subnet(db):
    from fastapi import HTTPException
    body = AllocateRequest(hostname="host1")
    user = User(id=1, username="alice", role="operator", enabled=True, hashed_password="x")
    with pytest.raises(HTTPException) as ei:
        _do_allocate(db, 99999, body, user, access=None)
    assert ei.value.status_code == 404
