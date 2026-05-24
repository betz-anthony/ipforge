"""Periodic threshold checks. Called by the dispatcher each tick."""
import ipaddress
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.alerting.emit import emit
from app.alerting.models import AlertRule
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus

logger = logging.getLogger(__name__)


def _usable_hosts(cidr: str) -> int:
    net = ipaddress.ip_network(cidr, strict=False)
    if net.version == 4 and net.prefixlen <= 30:
        return net.num_addresses - 2
    return max(1, net.num_addresses)


def eval_utilization(db: Session, rules: list[AlertRule]) -> None:
    """Emit 'utilization' for any subnet exceeding any matching rule's threshold."""
    for rule in rules:
        if rule.trigger_type != "utilization" or not rule.enabled:
            continue
        threshold = int((rule.condition or {}).get("threshold_pct", 90))
        for s in db.query(Subnet).all():
            try:
                usable = _usable_hosts(s.cidr)
            except ValueError:
                continue
            used = (
                db.query(func.count(IPAddress.id))
                .filter(
                    IPAddress.subnet_id == s.id,
                    IPAddress.status.in_([AddressStatus.reserved, AddressStatus.assigned]),
                )
                .scalar()
            )
            pct = round(100.0 * used / max(usable, 1), 1)
            if pct >= threshold:
                emit(
                    "utilization",
                    f"subnet:{s.cidr}",
                    {"cidr": s.cidr, "used": used, "usable": usable, "pct": pct,
                     "threshold_pct": threshold},
                )


def _stale_count(db: Session) -> int:
    """Reuse the canonical stale-IP query from app.api.reclaim."""
    try:
        from app.api.reclaim import _stale_query
        return _stale_query(db).count()
    except Exception:
        logger.exception("stale_count failed — returning 0")
        return 0


def eval_stale_queue(db: Session, rules: list[AlertRule]) -> None:
    count = _stale_count(db)
    for rule in rules:
        if rule.trigger_type != "stale_queue" or not rule.enabled:
            continue
        threshold = int((rule.condition or {}).get("threshold", 10))
        if count >= threshold:
            emit("stale_queue", "stale_queue",
                 {"count": count, "threshold": threshold})
