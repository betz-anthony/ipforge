"""ALLOC-POOLS-001 — helpers for named allocation pools."""
import ipaddress
import re

from sqlalchemy.orm import Session

from app.models.subnet_pool import SubnetPool

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def normalize_pool_name(name: str) -> str:
    """Lowercase and validate a pool name; raises ValueError when invalid."""
    n = (name or "").strip().lower()
    if not _NAME_RE.match(n):
        raise ValueError("pool name must be 1-64 chars: lowercase letters, digits, - and _, starting with a letter or digit")
    return n


def pool_bounds(pool: SubnetPool) -> tuple[int, int]:
    """Inclusive (start, end) of the pool as integers."""
    return int(ipaddress.ip_address(pool.start_ip)), int(ipaddress.ip_address(pool.end_ip))


def find_pool(db: Session, subnet_id: int, name: str) -> SubnetPool | None:
    try:
        n = normalize_pool_name(name)
    except ValueError:
        return None
    return db.query(SubnetPool).filter_by(subnet_id=subnet_id, name=n).first()


def ip_in_pool(ip: str, pool: SubnetPool) -> bool:
    try:
        lo, hi = pool_bounds(pool)
        return lo <= int(ipaddress.ip_address(ip)) <= hi
    except ValueError:
        return False
