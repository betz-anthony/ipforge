from pydantic import BaseModel
from datetime import datetime


class SubnetCreate(BaseModel):
    name: str
    cidr: str
    vlan_id: int | None = None
    description: str | None = None
    notes: str | None = None


class SubnetUpdate(BaseModel):
    name: str | None = None
    vlan_id: int | None = None
    description: str | None = None
    notes: str | None = None


class SubnetRead(SubnetCreate):
    id: int
    ip_version: int
    created_at: datetime

    model_config = {"from_attributes": True}
