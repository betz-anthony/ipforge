"""State machine for alerting events — dedupe + renotify decisions."""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.alerting.models import AlertingEvent, AlertRule
from app.core.time import utcnow


def find_firing(db: Session, rule_id: int, resource_key: str) -> AlertingEvent | None:
    return (
        db.query(AlertingEvent)
        .filter(
            AlertingEvent.rule_id == rule_id,
            AlertingEvent.resource_key == resource_key,
            AlertingEvent.state == "firing",
        )
        .first()
    )


def should_renotify(rule: AlertRule, event: AlertingEvent, now: datetime | None = None) -> bool:
    if not rule.renotify_minutes:
        return False
    now = now or utcnow()
    return (now - event.last_fired_at) >= timedelta(minutes=rule.renotify_minutes)


def transition_to_resolved(db: Session, event: AlertingEvent) -> None:
    event.state = "resolved"
    event.resolved_at = utcnow()
    db.commit()
