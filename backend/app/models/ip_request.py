"""IP-REQUEST-001 — see docs/superpowers/specs/2026-05-24-ip-request-design.md"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.core.time import utcnow


class IPRequest(Base):
    __tablename__ = "ip_requests"

    id:                 Mapped[int]            = mapped_column(Integer, primary_key=True)
    requester_username: Mapped[str]            = mapped_column(String(64), nullable=False)
    subnet_id:          Mapped[int | None]     = mapped_column(Integer, ForeignKey("subnets.id", ondelete="SET NULL"), nullable=True)
    hostname:           Mapped[str]            = mapped_column(String(63), nullable=False)
    mac_address:        Mapped[str | None]     = mapped_column(String(17), nullable=True)
    purpose:            Mapped[str]            = mapped_column(Text, nullable=False)
    status:             Mapped[str]            = mapped_column(String(16), nullable=False, default="pending")
    reviewer_username:  Mapped[str | None]     = mapped_column(String(64), nullable=True)
    reviewed_at:        Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_notes:       Mapped[str | None]     = mapped_column(Text, nullable=True)
    allocated_ip:       Mapped[str | None]     = mapped_column(String(45), nullable=True)
    allocated_id:       Mapped[int | None]     = mapped_column(Integer, ForeignKey("ip_addresses.id", ondelete="SET NULL"), nullable=True)
    created_at:         Mapped[datetime]       = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at:         Mapped[datetime]       = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


Index("ix_ip_requests_status_created", IPRequest.status, IPRequest.created_at)
Index("ix_ip_requests_requester_status", IPRequest.requester_username, IPRequest.status)
