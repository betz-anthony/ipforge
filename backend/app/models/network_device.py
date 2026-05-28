from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NetworkDevice(Base):
    __tablename__ = "network_devices"

    id:        Mapped[int]        = mapped_column(Integer, primary_key=True)
    name:      Mapped[str]        = mapped_column(String(255), nullable=False)
    host:      Mapped[str]        = mapped_column(String(255), nullable=False)
    snmp_version: Mapped[str]     = mapped_column(String(4), nullable=False, default="2c")  # 2c | 3

    community:      Mapped[str | None] = mapped_column(String(512), nullable=True)  # v2c (encrypted)
    v3_user:        Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_protocol:  Mapped[str | None] = mapped_column(String(16), nullable=True)   # SHA | MD5 | None
    auth_key:       Mapped[str | None] = mapped_column(String(512), nullable=True)  # encrypted
    priv_protocol:  Mapped[str | None] = mapped_column(String(16), nullable=True)   # AES | DES | None
    priv_key:       Mapped[str | None] = mapped_column(String(512), nullable=True)  # encrypted
    security_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    poll_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    enabled:    Mapped[bool]      = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=datetime.utcnow)


class DiscoveredEndpoint(Base):
    __tablename__ = "discovered_endpoints"

    id:        Mapped[int]        = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int]        = mapped_column(Integer, ForeignKey("network_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    ip:        Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    mac:       Mapped[str]        = mapped_column(String(50), nullable=False, index=True)
    ifindex:   Mapped[int | None] = mapped_column(Integer, nullable=True)
    port_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vlan:      Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen: Mapped[datetime]   = mapped_column(DateTime, nullable=False)
    source:    Mapped[str]        = mapped_column(String(255), nullable=False)
