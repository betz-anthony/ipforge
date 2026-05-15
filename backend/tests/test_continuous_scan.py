import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import json
from datetime import datetime, timezone, timedelta, date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.scan import ScanResult, ScanHistoryDay, AlertEvent

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
_MOCK_USER = User(id=1, username="test_admin", role="admin", enabled=True, hashed_password="x")


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    def override_get_current_user():
        return _MOCK_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_subnet(db, cidr="10.0.0.0/30", name="Test"):
    s = Subnet(name=name, cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _make_address(db, subnet_id, address="10.0.0.1"):
    a = IPAddress(address=address, subnet_id=subnet_id, status=AddressStatus.assigned)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_update_last_seen_sets_timestamp(db):
    subnet = _make_subnet(db)
    addr = _make_address(db, subnet.id, "10.0.0.1")
    assert addr.last_seen is None

    from app.scan import _update_last_seen
    now = _utcnow()
    _update_last_seen(db, {"10.0.0.1"}, now)
    db.commit()
    db.refresh(addr)
    assert addr.last_seen == now


def test_update_last_seen_skips_unreachable(db):
    subnet = _make_subnet(db)
    addr = _make_address(db, subnet.id, "10.0.0.1")

    from app.scan import _update_last_seen
    now = _utcnow()
    _update_last_seen(db, set(), now)   # empty reachable set
    db.commit()
    db.refresh(addr)
    assert addr.last_seen is None


def test_upsert_daily_history_creates_row(db):
    subnet = _make_subnet(db)
    now = _utcnow()
    results = [
        {"ip": "10.0.0.1", "reachable": True,  "latency_ms": 5.0},
        {"ip": "10.0.0.2", "reachable": False, "latency_ms": None},
    ]

    from app.scan import _upsert_daily_history
    _upsert_daily_history(db, subnet.id, results, now)
    db.commit()

    rows = db.query(ScanHistoryDay).all()
    assert len(rows) == 2

    up_row = db.query(ScanHistoryDay).filter_by(ip_address="10.0.0.1").first()
    assert up_row.up_count == 1
    assert up_row.total_count == 1
    assert up_row.uptime_pct == 100.0
    assert up_row.avg_latency_ms == 5.0

    down_row = db.query(ScanHistoryDay).filter_by(ip_address="10.0.0.2").first()
    assert down_row.up_count == 0
    assert down_row.total_count == 1
    assert down_row.uptime_pct == 0.0


def test_upsert_daily_history_increments_second_call(db):
    subnet = _make_subnet(db)
    now = _utcnow()
    results1 = [{"ip": "10.0.0.1", "reachable": True,  "latency_ms": 4.0}]
    results2 = [{"ip": "10.0.0.1", "reachable": False, "latency_ms": None}]

    from app.scan import _upsert_daily_history
    _upsert_daily_history(db, subnet.id, results1, now)
    db.commit()
    _upsert_daily_history(db, subnet.id, results2, now)
    db.commit()

    row = db.query(ScanHistoryDay).filter_by(ip_address="10.0.0.1").first()
    assert row.total_count == 2
    assert row.up_count == 1
    assert row.uptime_pct == 50.0


def _add_scan_result(db, subnet_id, ip, reachable, scanned_at):
    db.add(ScanResult(
        subnet_id=subnet_id, ip_address=ip,
        reachable=reachable, latency_ms=None, scanned_at=scanned_at,
    ))
    db.commit()


def test_detect_went_unreachable(db):
    subnet = _make_subnet(db)
    past = _utcnow() - timedelta(minutes=30)
    now  = _utcnow()

    _add_scan_result(db, subnet.id, "10.0.0.1", True, past)   # was up
    _add_scan_result(db, subnet.id, "10.0.0.1", False, now)   # now down

    from app.scan import _detect_reachability_changes
    _detect_reachability_changes(db, subnet.id, now)
    db.commit()

    events = db.query(AlertEvent).all()
    assert len(events) == 1
    assert events[0].event_type == "went_unreachable"
    assert events[0].ip_address == "10.0.0.1"


def test_detect_came_back(db):
    subnet = _make_subnet(db)
    past = _utcnow() - timedelta(minutes=30)
    now  = _utcnow()

    _add_scan_result(db, subnet.id, "10.0.0.1", False, past)  # was down
    _add_scan_result(db, subnet.id, "10.0.0.1", True,  now)   # now up

    from app.scan import _detect_reachability_changes
    _detect_reachability_changes(db, subnet.id, now)
    db.commit()

    events = db.query(AlertEvent).all()
    assert len(events) == 1
    assert events[0].event_type == "came_back"


def test_detect_no_event_if_no_prev_scan(db):
    subnet = _make_subnet(db)
    now = _utcnow()
    _add_scan_result(db, subnet.id, "10.0.0.1", True, now)

    from app.scan import _detect_reachability_changes
    _detect_reachability_changes(db, subnet.id, now)
    db.commit()

    assert db.query(AlertEvent).count() == 0


def test_detect_no_event_if_stable_reachable(db):
    subnet = _make_subnet(db)
    past = _utcnow() - timedelta(minutes=30)
    now  = _utcnow()
    _add_scan_result(db, subnet.id, "10.0.0.1", True, past)
    _add_scan_result(db, subnet.id, "10.0.0.1", True, now)

    from app.scan import _detect_reachability_changes
    _detect_reachability_changes(db, subnet.id, now)
    db.commit()

    assert db.query(AlertEvent).count() == 0


def test_settings_includes_scan_interval(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "scan_interval_minutes" in r.json()
    assert r.json()["scan_interval_minutes"] == 30


def test_settings_update_scan_interval(client):
    r = client.put("/api/settings", json={"scan_interval_minutes": 15})
    assert r.status_code == 200
    assert r.json()["scan_interval_minutes"] == 15

    r2 = client.get("/api/settings")
    assert r2.json()["scan_interval_minutes"] == 15


def test_subnet_list_includes_scan_interval(client, db):
    db.add(Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4, scan_interval_minutes=15))
    db.commit()
    r = client.get("/api/subnets")
    assert r.status_code == 200
    s = r.json()[0]
    assert s["scan_interval_minutes"] == 15


def test_subnet_create_with_scan_interval(client):
    r = client.post("/api/subnets", json={
        "name": "Net", "cidr": "10.0.0.0/24", "ip_version": 4,
        "scan_interval_minutes": 20,
    })
    assert r.status_code == 201
    assert r.json()["scan_interval_minutes"] == 20


def test_subnet_update_scan_interval(client, db):
    s = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(s); db.commit(); db.refresh(s)
    r = client.put(f"/api/subnets/{s.id}", json={"scan_interval_minutes": 60})
    assert r.status_code == 200
    assert r.json()["scan_interval_minutes"] == 60
