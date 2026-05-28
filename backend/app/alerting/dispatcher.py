"""Background dispatcher: drains emit queue, matches rules, delivers, resolves."""
import logging
import threading
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.config import settings
from app.core.time import utcnow
from app.alerting.emit import drain_queue, TriggerEvent
from app.alerting.models import AlertChannel, AlertRule, AlertingEvent
from app.alerting.state import find_firing, should_renotify, transition_to_resolved
from app.alerting.delivery import send_smtp, send_webhook, DeliveryResult
from app.alerting.payload import (
    build_subject, build_body, to_generic, to_slack, to_teams, to_pagerduty,
)
from app.alerting.thresholds import eval_utilization, eval_stale_queue

logger = logging.getLogger(__name__)
_stop = threading.Event()


def _matching_rules(db: Session, trigger_type: str) -> list[AlertRule]:
    return db.query(AlertRule).filter(
        AlertRule.trigger_type == trigger_type, AlertRule.enabled == True  # noqa: E712
    ).all()


def _channel(db: Session, ch_id: int) -> AlertChannel | None:
    return (
        db.query(AlertChannel)
        .filter(AlertChannel.id == ch_id, AlertChannel.enabled == True)  # noqa: E712
        .first()
    )


def _deliver_to_channel(channel: AlertChannel, event: AlertingEvent, rule: AlertRule,
                         recipients: list[str]) -> DeliveryResult:
    if channel.kind == "smtp":
        return send_smtp(
            channel,
            recipients=recipients,
            subject=build_subject(event, rule),
            body=build_body(event, rule),
        )
    transformers = {"generic": to_generic, "slack": to_slack, "teams": to_teams, "pagerduty": to_pagerduty}
    builder = transformers.get(channel.kind, to_generic)
    return send_webhook(channel, payload=builder(event, rule))


def _deliver(db: Session, event: AlertingEvent, rule: AlertRule) -> None:
    out = []
    for ch_id in (rule.channel_ids or []):
        ch = _channel(db, ch_id)
        if not ch:
            continue
        result = _deliver_to_channel(ch, event, rule, rule.recipients or [])
        out.append({"channel_id": ch_id, "status": result.status,
                    "error": result.error, "attempted_at": result.attempted_at})
    event.deliveries = (event.deliveries or []) + out
    event.last_fired_at = utcnow()
    db.commit()


def _process_trigger(db: Session, te: TriggerEvent) -> None:
    rules = _matching_rules(db, te.trigger_type)
    for rule in rules:
        existing = find_firing(db, rule.id, te.resource_key)
        if existing is None:
            evt = AlertingEvent(
                rule_id=rule.id, resource_key=te.resource_key, state="firing",
                first_fired_at=utcnow(), last_fired_at=utcnow(),
                payload={"trigger": te.trigger_type, "context": te.context}, deliveries=[],
            )
            db.add(evt); db.commit()
            _deliver(db, evt, rule)
        else:
            if should_renotify(rule, existing):
                _deliver(db, existing, rule)
            else:
                existing.last_fired_at = utcnow()
                db.commit()


def _resolve_stale_firing(db: Session) -> None:
    """Auto-resolve firing utilization events whose subnet dropped below threshold - 5 (hysteresis).

    Other trigger types (collision/rogue/sync_error/stale_queue) rely on manual ack in v1.
    """
    import ipaddress
    from sqlalchemy import func
    from app.models.subnet import Subnet
    from app.models.address import IPAddress, AddressStatus

    for evt in db.query(AlertingEvent).filter(AlertingEvent.state == "firing").all():
        if not evt.resource_key.startswith("subnet:"):
            continue
        cidr = evt.resource_key.removeprefix("subnet:")
        rule = db.get(AlertRule, evt.rule_id) if evt.rule_id else None
        if rule is None or rule.trigger_type != "utilization":
            continue
        threshold = int((rule.condition or {}).get("threshold_pct", 90))
        s = db.query(Subnet).filter_by(cidr=cidr).first()
        if s is None:
            continue
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            usable = net.num_addresses - 2 if net.version == 4 and net.prefixlen <= 30 else max(1, net.num_addresses)
        except ValueError:
            continue
        used = db.query(func.count(IPAddress.id)).filter(
            IPAddress.subnet_id == s.id,
            IPAddress.status.in_([AddressStatus.reserved, AddressStatus.assigned]),
        ).scalar()
        pct = 100.0 * used / max(usable, 1)
        if pct < max(0, threshold - 5):
            transition_to_resolved(db, evt)


def process_tick(db: Session) -> None:
    # 1. Drain queue once; feed both notification and automation from the same events.
    from app.automation import run_automation
    for te in drain_queue():
        try:
            _process_trigger(db, te)
        except Exception:
            logger.exception("dispatcher: error processing trigger %s", te.resource_key)
        try:
            run_automation(db, te)
        except Exception:
            logger.exception("dispatcher: automation error for %s", te.resource_key)

    # 2. Periodic threshold evaluation
    rules = db.query(AlertRule).filter(AlertRule.enabled == True).all()  # noqa: E712
    try:
        eval_utilization(db, rules)
    except Exception:
        logger.exception("eval_utilization failed")
    try:
        eval_stale_queue(db, rules)
    except Exception:
        logger.exception("eval_stale_queue failed")

    # 3. Auto-resolve cleared utilization events
    try:
        _resolve_stale_firing(db)
    except Exception:
        logger.exception("resolve_stale_firing failed")


def loop() -> None:
    """Long-running dispatcher loop. Run inside a daemon thread."""
    interval = int(getattr(settings, "alert_dispatch_interval", 30))
    logger.info("alert dispatcher loop started (interval=%ss)", interval)
    while not _stop.is_set():
        db = SessionLocal()
        try:
            process_tick(db)
        except Exception:
            logger.exception("dispatcher tick crashed")
        finally:
            db.close()
        _stop.wait(interval)


def start() -> threading.Thread:
    _stop.clear()
    t = threading.Thread(target=loop, daemon=True, name="ipam-alert-dispatcher")
    t.start()
    return t


def stop() -> None:
    _stop.set()
