from pydantic import BaseModel, Field
from datetime import datetime


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

    model_config = {"from_attributes": True}


class SubnetWithStats(SubnetRead):
    used_count: int
    total_count: int
    utilization_pct: float
    rollup_used_count: int = 0
    rollup_total_count: int = 0
    rollup_utilization_pct: float = 0.0
