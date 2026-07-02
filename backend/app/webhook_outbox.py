"""WEBHOOK-OUT-001: transactional outbox.

enqueue_webhooks() is called from write_audit() with the caller's session, so
delivery rows commit/roll back atomically with the audited write.
"""
import uuid
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.webhook import WebhookDelivery, WebhookEndpoint


def matches(ep: WebhookEndpoint, resource_type: str, action: str) -> bool:
    """Empty filter list = match all."""
    if ep.resource_types and resource_type not in ep.resource_types:
        return False
    if ep.actions and action not in ep.actions:
        return False
    return True


def enqueue_webhooks(
    db: Session,
    *,
    username: str,
    action: str,
    resource_type: str,
    resource_id: str,
    summary: str,
    before: dict | None,
    after: dict | None,
) -> None:
    endpoints = db.query(WebhookEndpoint).filter(WebhookEndpoint.enabled == True).all()  # noqa: E712
    if not endpoints:
        return
    event = f"{resource_type}.{action}"
    for ep in endpoints:
        if not matches(ep, resource_type, action):
            continue
        delivery_uuid = str(uuid.uuid4())
        db.add(WebhookDelivery(
            uuid=delivery_uuid,
            endpoint_id=ep.id,
            event_type=event,
            payload={
                "id": delivery_uuid,
                "event": event,
                "timestamp": utcnow().isoformat(),
                "actor": username,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "summary": summary,
                "before": before,
                "after": after,
            },
        ))
