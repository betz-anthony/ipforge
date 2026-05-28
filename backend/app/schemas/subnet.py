from pydantic import BaseModel, Field
from datetime import datetime, date


class SubnetCreate(BaseModel):
    name: str
    cidr: str
    ip_version: int = 4
    vlan_id: int | None = None
    description: str | None = None
    notes: str | None = None
    parent_id: int | None = None
    scan_interval_minutes: int | None = Field(default=None, ge=1)
    dns_provider_name: str | None = None
    dhcp_provider_name: str | None = None
    request_eligible: bool = False


class SubnetUpdate(BaseModel):
    name: str | None = None
    vlan_id: int | None = None
    description: str | None = None
    notes: str | None = None
    parent_id: int | None = None
    scan_interval_minutes: int | None = Field(default=None, ge=1)
    dns_provider_name: str | None = None
    dhcp_provider_name: str | None = None
    request_eligible: bool | None = None
    custom_fields: dict[str, str] | None = None
    tags: list[str] | None = None


class SubnetRead(BaseModel):
    id: int
    name: str
    cidr: str
    ip_version: int
    vlan_id: int | None
    description: str | None
    notes: str | None
    created_at: datetime
    parent_id: int | None
    scan_interval_minutes: int | None
    dns_provider_name: str | None
    dhcp_provider_name: str | None
    request_eligible: bool
    custom_fields: dict[str, str] = {}
    tags: list[str] = []

    model_config = {"from_attributes": True}


class SubnetWithStats(SubnetRead):
    used_count: int
    total_count: int
    utilization_pct: float
    reserved_count: int = 0
    rollup_used_count: int = 0
    rollup_total_count: int = 0
    rollup_utilization_pct: float = 0.0


class SubnetForecast(BaseModel):
    subnet_id: int
    cidr: str
    name: str
    slope_per_day: float
    current_used: int
    total_count: int
    data_points: int
    warn_pct: float
    critical_pct: float
    days_to_warn: int | None
    days_to_critical: int | None
    projected_warn_date: date | None
    projected_critical_date: date | None
    confidence: str
