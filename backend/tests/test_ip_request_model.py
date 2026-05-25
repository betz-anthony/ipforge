"""Tests for IPRequest ORM model — IP-REQUEST-001 Task 1."""
from datetime import datetime
from app.models.ip_request import IPRequest
from app.models.subnet import Subnet


def test_ip_request_defaults(db):
    r = IPRequest(
        requester_username="alice", subnet_id=None, hostname="webhost",
        purpose="new web server",
    )
    db.add(r); db.commit()
    assert r.status == "pending"
    assert r.id is not None
    assert r.created_at is not None
    assert r.reviewer_username is None
    assert r.allocated_ip is None


def test_ip_request_fields_round_trip(db):
    r = IPRequest(
        requester_username="bob", subnet_id=None,
        hostname="dbhost", mac_address="aa:bb:cc:dd:ee:ff", purpose="db",
        status="approved", reviewer_username="ops1", reviewed_at=datetime(2026, 5, 25),
        review_notes="ok", allocated_ip="10.0.0.5", allocated_id=42,
    )
    db.add(r); db.commit()
    db.refresh(r)
    assert r.status == "approved"
    assert r.allocated_ip == "10.0.0.5"
    assert r.review_notes == "ok"


def test_subnet_request_eligible_default(db):
    s = Subnet(cidr="10.0.0.0/24", name="test")
    db.add(s); db.commit()
    assert s.request_eligible is False
