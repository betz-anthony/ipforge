from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.database import Base


class Subnet(Base):
    __tablename__ = "subnets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    cidr: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    ip_version: Mapped[int] = mapped_column(Integer, default=4)
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("subnets.id"), nullable=True
    )
    scan_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dns_provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dhcp_provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    addresses: Mapped[list["IPAddress"]] = relationship(
        "IPAddress", back_populates="subnet", cascade="all, delete-orphan"
    )
