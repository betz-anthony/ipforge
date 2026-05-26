"""Shared input validators reused across API modules."""
import re

_HOSTNAME_RE = re.compile(r'^[a-z0-9][a-z0-9\-]*$')


def validate_hostname(v: str) -> str:
    """Normalize and validate a single-label hostname. Returns canonical form (lowercase, stripped).
    Raises ValueError if invalid."""
    v = v.strip().lower()
    if not _HOSTNAME_RE.match(v) or len(v) > 63:
        raise ValueError("hostname must be 1-63 chars, start with alphanumeric, contain only a-z, 0-9, hyphen")
    return v
