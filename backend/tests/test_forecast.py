from datetime import date

from app.core.forecast import compute_forecast


def _snaps(start_used, step, n, start=date(2026, 5, 1)):
    return [(date(start.year, start.month, start.day + i), start_used + step * i) for i in range(n)]


def test_linear_slope_one_per_day():
    snaps = _snaps(10, 1, 5)  # 10,11,12,13,14 over 5 days
    f = compute_forecast(snaps, total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 5))
    assert round(f["slope_per_day"], 4) == 1.0
    assert f["current_used"] == 14
    assert f["data_points"] == 5


def test_days_to_critical():
    # 100 used, +10/day, total 254, critical 95% -> 241.3 used target
    snaps = _snaps(60, 10, 5)  # ends at 100 on day 5 (2026-05-05)
    f = compute_forecast(snaps, total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 5))
    # target = ceil-ish: critical_count = 254*0.95 = 241.3; need (241.3-100)/10 = 14.13 -> 15 days
    assert f["days_to_critical"] == 15
    assert f["projected_critical_date"] == date(2026, 5, 20)


def test_warn_before_critical():
    snaps = _snaps(60, 10, 5)
    f = compute_forecast(snaps, total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 5))
    assert f["days_to_warn"] is not None
    assert f["days_to_critical"] is not None
    assert f["days_to_warn"] < f["days_to_critical"]


def test_flat_usage_no_projection():
    snaps = _snaps(50, 0, 5)  # constant 50
    f = compute_forecast(snaps, total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 5))
    assert f["slope_per_day"] == 0.0
    assert f["days_to_critical"] is None
    assert f["projected_critical_date"] is None
    assert f["confidence"] == "none"


def test_declining_usage_no_projection():
    snaps = _snaps(100, -5, 5)
    f = compute_forecast(snaps, total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 5))
    assert f["slope_per_day"] < 0
    assert f["days_to_critical"] is None
    assert f["confidence"] == "none"


def test_already_past_critical_zero_days():
    snaps = _snaps(240, 1, 5)  # ends 244 > 241.3 critical
    f = compute_forecast(snaps, total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 5))
    assert f["days_to_critical"] == 0
    assert f["projected_critical_date"] == date(2026, 5, 5)


def test_insufficient_data_confidence_none():
    f = compute_forecast([(date(2026, 5, 1), 10)], total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 1))
    assert f["confidence"] == "none"
    assert f["slope_per_day"] == 0.0
    assert f["days_to_critical"] is None


def test_empty_snapshots():
    f = compute_forecast([], total_count=254, warn_pct=80, critical_pct=95, today=date(2026, 5, 1))
    assert f["confidence"] == "none"
    assert f["current_used"] == 0
    assert f["data_points"] == 0


def test_confidence_levels_by_data_points():
    low = compute_forecast(_snaps(10, 2, 3), 254, 80, 95, date(2026, 5, 3))
    med = compute_forecast(_snaps(10, 2, 5), 254, 80, 95, date(2026, 5, 5))
    high = compute_forecast(_snaps(10, 2, 8), 254, 80, 95, date(2026, 5, 8))
    assert low["confidence"] == "low"
    assert med["confidence"] == "medium"
    assert high["confidence"] == "high"
