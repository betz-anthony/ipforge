import ipaddress
from pydantic import BaseModel, field_validator
from datetime import datetime
from app.models.address import AddressStatus


class AddressCreate(BaseModel):
    address: str
    subnet_id: int

    @field_validator("address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError(f"Invalid IP address: {v}")
        return v
    hostname: str | None = None
    status: AddressStatus = AddressStatus.available
    mac_address: str | None = None
    description: str | None = None
    notes: str | None = None


class AddressUpdate(BaseModel):
    hostname: str | None = None
    status: AddressStatus | None = None
    mac_address: str | None = None
    description: str | None = None
    notes: str | None = None


class AddressRead(AddressCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    last_seen: datetime | None = None

    model_config = {"from_attributes": True}
