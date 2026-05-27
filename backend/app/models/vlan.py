"""VLAN-001 — catalog of VLAN tags.

Soft-joined to Subnet.vlan_id (integer): subnets keep their existing
int vlan_id column; the vlans table provides names/descriptions for
those tag IDs. No FK constraint — a subnet can carry a vlan_id with
no matching entry, and an entry can exist without any subnet using it.
"""
from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.core.time import utcnow


class Vlan(Base):
    __tablename__ = "vlans"

    id:          Mapped[int]            = mapped_column(Integer, primary_key=True)
    vlan_id:     Mapped[int]            = mapped_column(Integer, unique=True, nullable=False, index=True)
    name:        Mapped[str]            = mapped_column(String(255), nullable=False)
    description: Mapped[str | None]     = mapped_column(Text, nullable=True)
    notes:       Mapped[str | None]     = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]       = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at:  Mapped[datetime]       = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
