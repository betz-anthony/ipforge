from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id:              Mapped[int]          = mapped_column(Integer, primary_key=True)
    event_type:      Mapped[str]          = mapped_column(String(20), nullable=False, index=True)
    severity:        Mapped[str]          = mapped_column(String(10), nullable=False)
    mac:             Mapped[str | None]   = mapped_column(String(50), nullable=True, index=True)
    ip:              Mapped[str | None]   = mapped_column(String(50), nullable=True, index=True)
    details:         Mapped[str | None]   = mapped_column(Text, nullable=True)
    detected_at:     Mapped[datetime]     = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    acknowledged:    Mapped[bool]         = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at: Mapped[datetime|None]= mapped_column(DateTime, nullable=True)
    quarantined:     Mapped[bool]         = mapped_column(Boolean, nullable=False, default=False)


class MacLastSeen(Base):
    __tablename__ = "mac_last_seen"

    mac:       Mapped[str]          = mapped_column(String(50), primary_key=True)
    device_id: Mapped[int | None]   = mapped_column(Integer, nullable=True)
    port_name: Mapped[str | None]   = mapped_column(String(128), nullable=True)
    ip:        Mapped[str | None]   = mapped_column(String(50), nullable=True)
    last_seen: Mapped[datetime]     = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
