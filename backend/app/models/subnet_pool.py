from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubnetPool(Base):
    """ALLOC-POOLS-001 — named IP window inside a subnet that allocation can target."""
    __tablename__ = "subnet_pools"
    __table_args__ = (
        UniqueConstraint("subnet_id", "name", name="uq_subnet_pools_subnet_name"),
    )

    id:          Mapped[int]        = mapped_column(Integer, primary_key=True)
    subnet_id:   Mapped[int]        = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True)
    name:        Mapped[str]        = mapped_column(String(64), nullable=False)
    start_ip:    Mapped[str]        = mapped_column(String(50), nullable=False)
    end_ip:      Mapped[str]        = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow)
