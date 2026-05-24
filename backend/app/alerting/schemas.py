from typing import Any, Literal
from pydantic import BaseModel, Field


ChannelKind = Literal["smtp", "generic", "slack", "teams", "pagerduty"]


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: ChannelKind
    config: dict[str, Any] = {}
    secret: str | None = None
    enabled: bool = True


class ChannelOut(BaseModel):
    id: int
    name: str
    kind: ChannelKind
    config: dict[str, Any]
    has_secret: bool
    enabled: bool

    @classmethod
    def from_orm_safe(cls, ch):
        return cls(id=ch.id, name=ch.name, kind=ch.kind, config=ch.config or {},
                   has_secret=bool(ch.secret_enc), enabled=ch.enabled)


TriggerType = Literal["collision", "utilization", "rogue", "sync_error", "stale_queue"]


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    trigger_type: TriggerType
    condition: dict[str, Any] = {}
    channel_ids: list[int] = []
    recipients: list[str] = []
    renotify_minutes: int | None = None
    enabled: bool = True


class RuleOut(BaseModel):
    id: int
    name: str
    trigger_type: TriggerType
    condition: dict[str, Any]
    channel_ids: list[int]
    recipients: list[str]
    renotify_minutes: int | None
    enabled: bool

    @classmethod
    def from_orm(cls, r):
        return cls(id=r.id, name=r.name, trigger_type=r.trigger_type,
                   condition=r.condition or {}, channel_ids=r.channel_ids or [],
                   recipients=r.recipients or [], renotify_minutes=r.renotify_minutes, enabled=r.enabled)


class EventOut(BaseModel):
    id: int
    rule_id: int | None
    resource_key: str
    state: Literal["firing", "resolved"]
    first_fired_at: str
    last_fired_at: str
    resolved_at: str | None
    payload: dict[str, Any]
    deliveries: list[dict[str, Any]]

    @classmethod
    def from_orm(cls, e):
        return cls(
            id=e.id, rule_id=e.rule_id, resource_key=e.resource_key, state=e.state,
            first_fired_at=e.first_fired_at.isoformat(),
            last_fired_at=e.last_fired_at.isoformat(),
            resolved_at=e.resolved_at.isoformat() if e.resolved_at else None,
            payload=e.payload or {}, deliveries=e.deliveries or [],
        )
