from datetime import datetime

from sqlalchemy import String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DHCPScopeReservedSyncExclusion(Base):
    """Admin-set opt-out: a (source, scope_id) pair present here has its
    gateway/exclusions withheld from the Reserved Ranges auto-sync
    (sync.py's sync_dhcp), even though the scope itself keeps syncing leases
    and pool data normally. For a scope kept configured in DHCP purely for
    testing/monitoring rather than real distribution — its exclusion data
    would otherwise get unioned into Reserved Ranges as if it were
    authoritative, wrongly blocking allocation in the subnet it maps to.

    Never written by sync.py itself — only by the admin-facing API."""
    __tablename__ = "dhcp_scope_reserved_sync_exclusions"
    __table_args__ = (UniqueConstraint("source", "scope_id", name="uq_dhcp_scope_reserved_sync_exclusions"),)

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    source:     Mapped[str]      = mapped_column(String(100), nullable=False, index=True)
    scope_id:   Mapped[str]      = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
