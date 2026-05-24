"""ORM models for ALERTING-001.

Note: The existing scan module has an AlertEvent with __tablename__ = "alert_events".
To avoid a collision, the alerting-system event model is named AlertingEvent and uses
__tablename__ = "alerting_events".
"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.core.time import utcnow


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id:          Mapped[int]        = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]        = mapped_column(String(64), nullable=False, unique=True)
    kind:        Mapped[str]        = mapped_column(String(16), nullable=False)   # smtp|generic|slack|teams|pagerduty
    enabled:     Mapped[bool]       = mapped_column(Boolean, nullable=False, default=True)
    config:      Mapped[dict]       = mapped_column(JSON, nullable=False, default=dict)
    secret_enc:  Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at:  Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id:               Mapped[int]        = mapped_column(Integer, primary_key=True)
    name:             Mapped[str]        = mapped_column(String(64), nullable=False, unique=True)
    trigger_type:     Mapped[str]        = mapped_column(String(32), nullable=False)  # collision|utilization|rogue|sync_error|stale_queue
    condition:        Mapped[dict]       = mapped_column(JSON, nullable=False, default=dict)
    channel_ids:      Mapped[list]       = mapped_column(JSON, nullable=False, default=list)
    recipients:       Mapped[list]       = mapped_column(JSON, nullable=False, default=list)
    renotify_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled:          Mapped[bool]       = mapped_column(Boolean, nullable=False, default=True)
    created_at:       Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at:       Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AlertingEvent(Base):
    """Alerting system event (distinct from app.models.scan.AlertEvent / alert_events table).

    Uses __tablename__ = 'alerting_events' to avoid clashing with the scan module's
    'alert_events' table.
    """
    __tablename__ = "alerting_events"

    id:             Mapped[int]        = mapped_column(Integer, primary_key=True)
    rule_id:        Mapped[int | None] = mapped_column(Integer, ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True)
    resource_key:   Mapped[str]        = mapped_column(String(128), nullable=False)
    state:          Mapped[str]        = mapped_column(String(8), nullable=False)    # firing|resolved
    first_fired_at: Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow)
    last_fired_at:  Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow)
    resolved_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload:        Mapped[dict]       = mapped_column(JSON, nullable=False, default=dict)
    deliveries:     Mapped[list]       = mapped_column(JSON, nullable=False, default=list)


Index("ix_alerting_events_dedupe", AlertingEvent.rule_id, AlertingEvent.resource_key, AlertingEvent.state)
Index("ix_alerting_events_state_fired", AlertingEvent.state, AlertingEvent.first_fired_at)
