import pytest
from datetime import datetime, timezone, timedelta
from app.models.address import IPAddress, AddressStatus
from app.models.subnet import Subnet
from app.config import settings as app_settings


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── autouse fixture: reset stale_reclaim_days between tests ──────────────────

@pytest.fixture(autouse=True)
def reset_stale_days():
    original = app_settings.stale_reclaim_days
    yield
    app_settings.stale_reclaim_days = original


# ── helpers ───────────────────────────────────────────────────────────────────

def _subnet(db, cidr="10.0.1.0/24", name="test"):
    s = Subnet(name=name, cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _ip(db, subnet_id, address, status=AddressStatus.assigned,
        last_seen_days_ago=None, dismissed_until=None):
    now = _utcnow()
    last_seen = (now - timedelta(days=last_seen_days_ago)) if last_seen_days_ago is not None else None
    a = IPAddress(
        address=address,
        subnet_id=subnet_id,
        status=status,
        last_seen=last_seen,
        reclaim_dismissed_until=dismissed_until,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ── column existence ──────────────────────────────────────────────────────────

def test_reclaim_dismissed_until_column_exists(db):
    s = _subnet(db)
    a = _ip(db, s.id, "10.0.1.2", last_seen_days_ago=40)
    assert hasattr(a, "reclaim_dismissed_until")
    assert a.reclaim_dismissed_until is None
