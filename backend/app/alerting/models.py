"""ORM models for ALERTING-001.

Note: The existing scan module has an AlertEvent with __tablename__ = "alert_events".
To avoid a collision, the alerting-system event model is named AlertingEvent and uses
__tablename__ = "alerting_events".
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Index, Text
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(64), nullable=False, unique=True)
    kind        = Column(String(16), nullable=False)   # smtp|generic|slack|teams|pagerduty
    enabled     = Column(Boolean, nullable=False, default=True)
    config      = Column(JSON, nullable=False, default=dict)
    secret_enc  = Column(Text, nullable=True)
    created_at  = Column(DateTime, nullable=False, default=_utcnow)
    updated_at  = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id                = Column(Integer, primary_key=True)
    name              = Column(String(64), nullable=False, unique=True)
    trigger_type      = Column(String(32), nullable=False)  # collision|utilization|rogue|sync_error|stale_queue
    condition         = Column(JSON, nullable=False, default=dict)
    channel_ids       = Column(JSON, nullable=False, default=list)
    recipients        = Column(JSON, nullable=False, default=list)
    renotify_minutes  = Column(Integer, nullable=True)
    enabled           = Column(Boolean, nullable=False, default=True)
    created_at        = Column(DateTime, nullable=False, default=_utcnow)
    updated_at        = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class AlertingEvent(Base):
    """Alerting system event (distinct from app.models.scan.AlertEvent / alert_events table).

    Uses __tablename__ = 'alerting_events' to avoid clashing with the scan module's
    'alert_events' table.
    """
    __tablename__ = "alerting_events"

    id              = Column(Integer, primary_key=True)
    rule_id         = Column(Integer, ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True)
    resource_key    = Column(String(128), nullable=False)
    state           = Column(String(8), nullable=False)    # firing|resolved
    first_fired_at  = Column(DateTime, nullable=False, default=_utcnow)
    last_fired_at   = Column(DateTime, nullable=False, default=_utcnow)
    resolved_at     = Column(DateTime, nullable=True)
    payload         = Column(JSON, nullable=False, default=dict)
    deliveries      = Column(JSON, nullable=False, default=list)


Index("ix_alerting_events_dedupe", AlertingEvent.rule_id, AlertingEvent.resource_key, AlertingEvent.state)
Index("ix_alerting_events_state_fired", AlertingEvent.state, AlertingEvent.first_fired_at)
