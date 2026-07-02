"""WEBHOOK-OUT-001: outbound webhook endpoints + transactional-outbox deliveries."""
import uuid as _uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.core.time import utcnow


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id:             Mapped[int]        = mapped_column(Integer, primary_key=True)
    name:           Mapped[str]        = mapped_column(String(64), nullable=False, unique=True)
    url:            Mapped[str]        = mapped_column(Text, nullable=False)
    enabled:        Mapped[bool]       = mapped_column(Boolean, nullable=False, default=True)
    secret_enc:     Mapped[str | None] = mapped_column(Text, nullable=True)   # Fernet; HMAC key
    custom_headers: Mapped[dict]       = mapped_column(JSON, nullable=False, default=dict)
    resource_types: Mapped[list]       = mapped_column(JSON, nullable=False, default=list)  # [] = all
    actions:        Mapped[list]       = mapped_column(JSON, nullable=False, default=list)  # [] = all
    created_at:     Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at:     Mapped[datetime]   = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id:              Mapped[int]             = mapped_column(Integer, primary_key=True)
    uuid:            Mapped[str]             = mapped_column(String(36), nullable=False, unique=True,
                                                             default=lambda: str(_uuid.uuid4()))
    endpoint_id:     Mapped[int]             = mapped_column(Integer,
                                                             ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
                                                             nullable=False)
    event_type:      Mapped[str]             = mapped_column(String(64), nullable=False)
    payload:         Mapped[dict]            = mapped_column(JSON, nullable=False, default=dict)
    status:          Mapped[str]             = mapped_column(String(12), nullable=False, default="pending")
    attempts:        Mapped[int]             = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime]        = mapped_column(DateTime, nullable=False, default=utcnow)
    last_error:      Mapped[str | None]      = mapped_column(Text, nullable=True)
    response_status: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    created_at:      Mapped[datetime]        = mapped_column(DateTime, nullable=False, default=utcnow)
    delivered_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


Index("ix_webhook_deliveries_due", WebhookDelivery.status, WebhookDelivery.next_attempt_at)
Index("ix_webhook_deliveries_endpoint", WebhookDelivery.endpoint_id)
