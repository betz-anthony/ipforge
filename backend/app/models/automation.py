from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.time import utcnow


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True)
    name:         Mapped[str]      = mapped_column(String(64), nullable=False, unique=True)
    trigger_type: Mapped[str]      = mapped_column(String(32), nullable=False)  # rogue | drift
    condition:    Mapped[dict]     = mapped_column(JSON, nullable=False, default=dict)
    action:       Mapped[dict]     = mapped_column(JSON, nullable=False, default=dict)
    enabled:      Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at:   Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
