from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp — tz-aware now() with tzinfo stripped to match DB columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
