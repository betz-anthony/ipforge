import enum
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AddressStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"
    assigned = "assigned"
    deprecated = "deprecated"
    discovered = "discovered"


class IPAddress(Base):
    __tablename__ = "ip_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    subnet_id: Mapped[int] = mapped_column(Integer, ForeignKey("subnets.id"))
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[AddressStatus] = mapped_column(Enum(AddressStatus), default=AddressStatus.available)
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reclaim_dismissed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dns_provider:  Mapped[str | None] = mapped_column(String(255), nullable=True)
    dns_zone:      Mapped[str | None] = mapped_column(String(255), nullable=True)
    dhcp_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dhcp_scope_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ptr_zone:      Mapped[str | None] = mapped_column(String(255), nullable=True)

    subnet: Mapped["Subnet"] = relationship("Subnet", back_populates="addresses")
