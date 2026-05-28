import math
from datetime import date, timedelta


def _linear_slope(xs: list[int], ys: list[int]) -> float:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _project(current: int, target: float, slope: float, today: date):
    if slope <= 0:
        return None, None
    remaining = target - current
    days = 0 if remaining <= 0 else math.ceil(remaining / slope)
    return days, today + timedelta(days=days)


def compute_forecast(
    snapshots: list[tuple[date, int]],
    total_count: int,
    warn_pct: float,
    critical_pct: float,
    today: date | None = None,
) -> dict:
    if today is None:
        today = date.today()

    ordered = sorted(snapshots, key=lambda s: s[0])
    data_points = len(ordered)
    current_used = ordered[-1][1] if ordered else 0

    result = {
        "slope_per_day": 0.0,
        "current_used": current_used,
        "total_count": total_count,
        "data_points": data_points,
        "warn_pct": warn_pct,
        "critical_pct": critical_pct,
        "days_to_warn": None,
        "days_to_critical": None,
        "projected_warn_date": None,
        "projected_critical_date": None,
        "confidence": "none",
    }

    if data_points < 2:
        return result

    xs = [d.toordinal() for d, _ in ordered]
    ys = [u for _, u in ordered]
    slope = _linear_slope(xs, ys)
    result["slope_per_day"] = slope

    if slope <= 0:
        return result

    warn_target = total_count * warn_pct / 100
    crit_target = total_count * critical_pct / 100
    result["days_to_warn"], result["projected_warn_date"] = _project(current_used, warn_target, slope, today)
    result["days_to_critical"], result["projected_critical_date"] = _project(current_used, crit_target, slope, today)

    if data_points >= 7:
        result["confidence"] = "high"
    elif data_points >= 4:
        result["confidence"] = "medium"
    else:
        result["confidence"] = "low"

    return result
