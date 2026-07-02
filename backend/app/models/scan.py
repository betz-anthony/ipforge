import enum
from datetime import datetime, date
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Date, Text, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DriftCategory(str, enum.Enum):
    # carried conflict categories
    active_but_available = "active_but_available"
    multi_dhcp_scope     = "multi_dhcp_scope"
    hostname_mismatch    = "hostname_mismatch"
    # new reconciliation categories
    missing_dns          = "missing_dns"
    orphan_dns           = "orphan_dns"
    orphan_dhcp          = "orphan_dhcp"
    mac_mismatch         = "mac_mismatch"
    # v2 categories
    missing_dhcp         = "missing_dhcp"
    ptr_mismatch         = "ptr_mismatch"
    unreachable_assigned = "unreachable_assigned"
    # PROVIDER-CONFLICT-001 — cross-provider conflicts
    dns_source_conflict  = "dns_source_conflict"


# Backwards-compatible alias (the three original values still resolve).
CollisionType = DriftCategory

_CONFLICT_CATEGORIES = {
    DriftCategory.active_but_available,
    DriftCategory.hostname_mismatch,
    DriftCategory.multi_dhcp_scope,
}

DRIFT_SEVERITY = {
    DriftCategory.active_but_available: "warning",
    DriftCategory.hostname_mismatch:    "warning",
    DriftCategory.multi_dhcp_scope:     "warning",
    DriftCategory.missing_dns:          "warning",
    DriftCategory.missing_dhcp:         "warning",
    DriftCategory.mac_mismatch:         "warning",
    DriftCategory.ptr_mismatch:         "warning",
    DriftCategory.orphan_dns:           "info",
    DriftCategory.orphan_dhcp:          "info",
    DriftCategory.unreachable_assigned: "info",
    DriftCategory.dns_source_conflict:  "warning",
}


class ScanResult(Base):
    __tablename__ = "scan_results"

    id:         Mapped[int]        = mapped_column(Integer, primary_key=True)
    subnet_id:  Mapped[int]        = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_address: Mapped[str]        = mapped_column(String(50), nullable=False, index=True)
    reachable:  Mapped[bool]       = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[float|None] = mapped_column(Float, nullable=True)
    scanned_at: Mapped[datetime]   = mapped_column(DateTime, nullable=False)


class DriftItem(Base):
    __tablename__ = "drift_items"
    __table_args__ = (
        UniqueConstraint("ip_address", "category", name="uq_drift_ip_category"),
    )

    id:          Mapped[int]          = mapped_column(Integer, primary_key=True)
    ip_address:  Mapped[str]          = mapped_column(String(50), nullable=False, index=True)
    category:    Mapped[str]          = mapped_column(String(50), nullable=False)
    severity:    Mapped[str]          = mapped_column(String(20), nullable=False, default="warning")
    subnet_id:   Mapped[int|None]     = mapped_column(Integer, ForeignKey("subnets.id", ondelete="SET NULL"), nullable=True, index=True)
    details:     Mapped[str|None]     = mapped_column(Text, nullable=True)
    detected_at:  Mapped[datetime]     = mapped_column(DateTime, nullable=False)
    resolved:     Mapped[bool]         = mapped_column(Boolean, nullable=False, default=False)
    resolved_at:  Mapped[datetime|None]= mapped_column(DateTime, nullable=True)
    needs_review: Mapped[bool]         = mapped_column(Boolean, nullable=False, default=False)

    # Back-compat property: old code referenced `.collision_type`.
    @property
    def collision_type(self) -> str:
        return self.category


class DriftPolicy(Base):
    __tablename__ = "drift_policies"
    __table_args__ = (
        # Global policies (subnet_id=None) uniqueness enforced at app layer.
        # Subnet-specific policies unique per (category, subnet_id).
        UniqueConstraint("category", "subnet_id", name="uq_drift_policies_category_subnet"),
    )

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    category:   Mapped[str]      = mapped_column(String(50), nullable=False)
    subnet_id:  Mapped[int|None] = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=True, index=True)
    mode:       Mapped[str]      = mapped_column(String(10), nullable=False)  # auto | review
    dry_run:    Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    params:     Mapped[dict]     = mapped_column(JSON, nullable=False, default=dict)
    enabled:    Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Alias so lingering imports of `Collision` keep working during the migration.
Collision = DriftItem


class ScanHistoryDay(Base):
    __tablename__ = "scan_history_daily"
    __table_args__ = (
        UniqueConstraint("ip_address", "date", name="uq_scan_history_ip_date"),
    )

    id:             Mapped[int]        = mapped_column(Integer, primary_key=True)
    ip_address:     Mapped[str]        = mapped_column(String(50), nullable=False, index=True)
    subnet_id:      Mapped[int]        = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True)
    date:           Mapped[date]       = mapped_column(Date, nullable=False)
    up_count:       Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    total_count:    Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    avg_latency_ms: Mapped[float|None] = mapped_column(Float, nullable=True)
    uptime_pct:     Mapped[float]      = mapped_column(Float, nullable=False, default=0.0)


class SubnetUtilizationDay(Base):
    __tablename__ = "subnet_utilization_history"
    __table_args__ = (
        UniqueConstraint("subnet_id", "date", name="uq_subnet_util_date"),
    )

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True)
    subnet_id:   Mapped[int]  = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True)
    date:        Mapped[date] = mapped_column(Date, nullable=False)
    used_count:  Mapped[int]  = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int]  = mapped_column(Integer, nullable=False, default=0)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id:               Mapped[int]          = mapped_column(Integer, primary_key=True)
    event_type:       Mapped[str]          = mapped_column(String(30), nullable=False)
    ip_address:       Mapped[str]          = mapped_column(String(50), nullable=False, index=True)
    subnet_id:        Mapped[int]          = mapped_column(Integer, ForeignKey("subnets.id", ondelete="CASCADE"), nullable=False, index=True)
    detected_at:      Mapped[datetime]     = mapped_column(DateTime, nullable=False)
    details:          Mapped[str|None]     = mapped_column(Text, nullable=True)
    acknowledged:     Mapped[bool]         = mapped_column(Boolean, nullable=False, default=False)
    acknowledged_at:  Mapped[datetime|None]= mapped_column(DateTime, nullable=True)
