import enum
from datetime import datetime
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CollisionType(str, enum.Enum):
    active_but_available = "active_but_available"
    multi_dhcp_scope     = "multi_dhcp_scope"
    hostname_mismatch    = "hostname_mismatch"


class ScanResult(Base):
    __tablename__ = "scan_results"

    id:         Mapped[int]        = mapped_column(Integer, primary_key=True)
    subnet_id:  Mapped[int]        = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address: Mapped[str]        = mapped_column(String(50), nullable=False, index=True)
    reachable:  Mapped[bool]       = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[float|None] = mapped_column(Float, nullable=True)
    scanned_at: Mapped[datetime]   = mapped_column(DateTime, nullable=False)


class Collision(Base):
    __tablename__ = "collisions"
    __table_args__ = (
        UniqueConstraint("ip_address", "collision_type", name="uq_collision_ip_type"),
    )

    id:             Mapped[int]          = mapped_column(Integer, primary_key=True)
    ip_address:     Mapped[str]          = mapped_column(String(50), nullable=False, index=True)
    collision_type: Mapped[str]          = mapped_column(String(50), nullable=False)
    details:        Mapped[str|None]     = mapped_column(Text, nullable=True)
    detected_at:    Mapped[datetime]     = mapped_column(DateTime, nullable=False)
    resolved:       Mapped[bool]         = mapped_column(Boolean, nullable=False, default=False)
    resolved_at:    Mapped[datetime|None]= mapped_column(DateTime, nullable=True)
