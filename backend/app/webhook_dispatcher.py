"""WEBHOOK-OUT-001: delivery dispatcher.

sign()/build_request() build the exact signed request; dispatch_tick() (Task 4)
claims due outbox rows and delivers them from a daemon thread.
"""
import hashlib
import hmac
import json
import logging

from app.core.crypto import decrypt_secret
from app.models.webhook import WebhookEndpoint

logger = logging.getLogger(__name__)

BACKOFF_MINUTES = [1, 5, 15, 60, 360]
MAX_ATTEMPTS = 5
TICK_SECONDS = 5
RETENTION_DAYS = 30

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
