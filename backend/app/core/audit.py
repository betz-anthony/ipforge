import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from app.webhook_outbox import enqueue_webhooks

logger = logging.getLogger(__name__)


def write_audit(
    db: Session,
    username: str,
    action: str,
    resource_type: str,
    resource_id: str,
    summary: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(AuditLog(
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
        before_state=json.dumps(before, default=str) if before is not None else None,
        after_state=json.dumps(after, default=str) if after is not None else None,
    ))
    # WEBHOOK-OUT-001: transactional outbox — same session, commits with the write.
    # Never let webhook plumbing break the audited operation itself.
    try:
        enqueue_webhooks(
            db,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            before=before,
            after=after,
        )
    except Exception:
        logger.exception("webhook outbox enqueue failed (event %s.%s)", resource_type, action)
