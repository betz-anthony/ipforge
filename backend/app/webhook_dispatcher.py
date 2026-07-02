"""WEBHOOK-OUT-001: delivery dispatcher.

sign()/build_request() build the exact signed request; dispatch_tick() (Task 4)
claims due outbox rows and delivers them from a daemon thread.
"""
import hashlib
import hmac
import json
import logging
import threading
from datetime import timedelta

import requests
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_secret
from app.core.time import utcnow
from app.database import SessionLocal
from app.models.webhook import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)

BACKOFF_MINUTES = [1, 5, 15, 60, 360]
MAX_ATTEMPTS = 6  # 5 backoff waits (1m/5m/15m/1h/6h), dead on the 6th failed attempt
TICK_SECONDS = 5
RETENTION_DAYS = 30
CLAIM_TIMEOUT_MINUTES = 15  # worst case: 50-row batch * 10s timeout ~= 8.3min in-flight

_RESERVED_HEADERS = {"content-type", "x-ipforge-event", "x-ipforge-delivery", "x-ipforge-signature-256"}


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_request(ep: WebhookEndpoint, payload: dict) -> tuple[bytes, dict]:
    """Serialize once; sign the exact bytes that go on the wire."""
    body = json.dumps(payload, default=str, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "X-IPForge-Event": payload["event"],
        "X-IPForge-Delivery": payload["id"],
    }
    for k, v in (ep.custom_headers or {}).items():
        if k.lower() not in _RESERVED_HEADERS:
            headers[k] = str(v)
    if ep.secret_enc:
        headers["X-IPForge-Signature-256"] = sign(decrypt_secret(ep.secret_enc), body)
    return body, headers


_stop = threading.Event()


def dispatch_tick(db: Session) -> int:
    """Claim due pending rows for enabled endpoints, deliver each. Returns rows processed."""
    now = utcnow()

    # Recover claims stranded by a crash: no live claim can be this old.
    stale_cutoff = now - timedelta(minutes=CLAIM_TIMEOUT_MINUTES)
    (db.query(WebhookDelivery)
       .filter(WebhookDelivery.status == "delivering",
               WebhookDelivery.next_attempt_at <= stale_cutoff)
       .update({"status": "pending"}, synchronize_session=False))
    db.commit()

    rows = (
        db.query(WebhookDelivery)
        .join(WebhookEndpoint, WebhookDelivery.endpoint_id == WebhookEndpoint.id)
        .filter(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_attempt_at <= now,
            WebhookEndpoint.enabled == True,  # noqa: E712
        )
        .limit(50)
        .all()
    )
    for d in rows:
        d.status = "delivering"
    db.commit()

    for d in rows:
        try:
            ep = db.get(WebhookEndpoint, d.endpoint_id)
            if ep is None:
                d.status = "dead"
                d.last_error = "endpoint deleted"
                db.commit()
                continue
            body, headers = build_request(ep, d.payload)
            r = requests.post(ep.url, data=body, headers=headers, timeout=10)
            d.response_status = r.status_code
            if 200 <= r.status_code < 300:
                d.status = "delivered"
                d.delivered_at = utcnow()
                d.last_error = None
            else:
                _schedule_retry(d, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            d.response_status = None
            _schedule_retry(d, str(exc))
        db.commit()
    return len(rows)


def _schedule_retry(d: WebhookDelivery, error: str) -> None:
    d.attempts += 1
    d.last_error = error
    if d.attempts >= MAX_ATTEMPTS:
        d.status = "dead"
    else:
        d.status = "pending"
        d.next_attempt_at = utcnow() + timedelta(minutes=BACKOFF_MINUTES[d.attempts - 1])


def purge_delivered(db: Session) -> int:
    """Delete delivered rows older than RETENTION_DAYS. Dead rows are kept."""
    cutoff = utcnow() - timedelta(days=RETENTION_DAYS)
    n = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.status == "delivered", WebhookDelivery.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return n


def webhook_dispatcher_loop() -> None:
    logger.info("webhook dispatcher started (tick %ss)", TICK_SECONDS)
    while not _stop.wait(TICK_SECONDS):
        db = SessionLocal()
        try:
            dispatch_tick(db)
            purge_delivered(db)
        except Exception:
            logger.exception("webhook dispatcher tick failed")
        finally:
            db.close()


def start() -> None:
    threading.Thread(target=webhook_dispatcher_loop, daemon=True, name="ipam-webhook-dispatcher").start()
