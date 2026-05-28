from datetime import date, timedelta

from app.models.subnet import Subnet
from app.models.scan import SubnetUtilizationDay


def _seed_history(db, subnet_id, start_used, step, n, total=254, start=None):
    if start is None:
        start = date.today() - timedelta(days=n - 1)
    for i in range(n):
        db.add(SubnetUtilizationDay(
            subnet_id=subnet_id, date=start + timedelta(days=i),
            used_count=start_used + step * i, total_count=total,
        ))


def test_forecast_endpoint_returns_projection(client, db):
    s = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    _seed_history(db, s.id, 60, 10, 7)  # rising
    db.commit()

    r = client.get(f"/api/subnets/{s.id}/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["subnet_id"] == s.id
    assert body["slope_per_day"] > 0
    assert body["days_to_critical"] is not None
    assert body["confidence"] == "high"


def test_forecast_endpoint_no_history(client, db):
    s = Subnet(name="Empty", cidr="10.0.1.0/24", ip_version=4)
    db.add(s)
    db.commit()
    r = client.get(f"/api/subnets/{s.id}/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "none"
    assert body["days_to_critical"] is None


def test_forecast_endpoint_404(client, db):
    r = client.get("/api/subnets/99999/forecast")
    assert r.status_code == 404


def test_forecasts_top_sorted_and_limited(client, db):
    fast = Subnet(name="Fast", cidr="10.0.2.0/24", ip_version=4)
    slow = Subnet(name="Slow", cidr="10.0.3.0/24", ip_version=4)
    flat = Subnet(name="Flat", cidr="10.0.4.0/24", ip_version=4)
    db.add_all([fast, slow, flat])
    db.flush()
    _seed_history(db, fast.id, 100, 20, 7)  # soonest exhaustion
    _seed_history(db, slow.id, 100, 2, 7)
    _seed_history(db, flat.id, 50, 0, 7)    # no projection
    db.commit()

    r = client.get("/api/subnets/forecasts?limit=5")
    assert r.status_code == 200
    items = r.json()
    # flat excluded (no critical projection)
    names = [i["name"] for i in items]
    assert "Flat" not in names
    # fast before slow
    assert names.index("Fast") < names.index("Slow")


def test_forecasts_top_respects_limit(client, db):
    for i in range(4):
        s = Subnet(name=f"N{i}", cidr=f"10.1.{i}.0/24", ip_version=4)
        db.add(s)
        db.flush()
        _seed_history(db, s.id, 100, 10 + i, 7)
    db.commit()
    r = client.get("/api/subnets/forecasts?limit=2")
    assert r.status_code == 200
    assert len(r.json()) == 2
