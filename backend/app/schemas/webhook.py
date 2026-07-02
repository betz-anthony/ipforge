from datetime import datetime
from pydantic import BaseModel, ConfigDict


class WebhookEndpointIn(BaseModel):
    name: str
    url: str
    enabled: bool = True
    secret: str | None = None          # None = leave unchanged; "" = clear
    custom_headers: dict[str, str] = {}
    resource_types: list[str] = []     # [] = all
    actions: list[str] = []            # [] = all


class WebhookEndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    enabled: bool
    has_secret: bool
    custom_headers: dict
    resource_types: list
    actions: list
    last_status: str | None = None
    dead_count: int = 0
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    endpoint_id: int
    event_type: str
    status: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    response_status: int | None
    created_at: datetime
    delivered_at: datetime | None
    payload: dict


class WebhookTestResult(BaseModel):
    status: str                        # "sent" | "failed"
    response_status: int | None = None
    error: str | None = None
