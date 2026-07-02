import hashlib
import hmac as hmac_mod
import json

from app.core.crypto import encrypt_secret
from app.models.webhook import WebhookEndpoint
from app.webhook_dispatcher import sign, build_request


def test_sign_known_vector():
    # hmac-sha256("secret", b"hello") — verifiable with:
    #   python -c "import hmac,hashlib;print(hmac.new(b'secret',b'hello',hashlib.sha256).hexdigest())"
    expected = hmac_mod.new(b"secret", b"hello", hashlib.sha256).hexdigest()
    assert sign("secret", b"hello") == f"sha256={expected}"


def test_build_request_headers_and_body():
    ep = WebhookEndpoint(name="e", url="https://x/h", custom_headers={"X-Api-Key": "k"})
    payload = {"id": "u-1", "event": "address.update", "actor": "a"}
    body, headers = build_request(ep, payload)
    assert json.loads(body) == payload
    assert headers["Content-Type"] == "application/json"
    assert headers["X-IPForge-Event"] == "address.update"
    assert headers["X-IPForge-Delivery"] == "u-1"
    assert headers["X-Api-Key"] == "k"
    assert "X-IPForge-Signature-256" not in headers  # no secret set


def test_build_request_signs_when_secret_set():
    ep = WebhookEndpoint(name="e", url="https://x/h", secret_enc=encrypt_secret("s3cret"))
    body, headers = build_request(ep, {"id": "u", "event": "ping"})
    expected = hmac_mod.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert headers["X-IPForge-Signature-256"] == f"sha256={expected}"


def test_build_request_custom_headers_cannot_override_reserved():
    ep = WebhookEndpoint(name="e", url="https://x/h",
                         custom_headers={"X-IPForge-Event": "spoof", "Content-Type": "text/evil"})
    _, headers = build_request(ep, {"id": "u", "event": "ping"})
    assert headers["X-IPForge-Event"] == "ping"
    assert headers["Content-Type"] == "application/json"


def test_build_request_reserved_header_check_is_case_insensitive():
    ep = WebhookEndpoint(name="e", url="https://x/h",
                         custom_headers={"content-type": "text/evil", "X-IPFORGE-EVENT": "spoof"})
    _, headers = build_request(ep, {"id": "u", "event": "ping"})
    assert headers["Content-Type"] == "application/json"
    assert headers["X-IPForge-Event"] == "ping"
    # no duplicate case-variant keys snuck in
    lowered = [k.lower() for k in headers]
    assert lowered.count("content-type") == 1
    assert lowered.count("x-ipforge-event") == 1


from datetime import timedelta
from unittest.mock import MagicMock, patch

from app.core.time import utcnow
from app.models.webhook import WebhookDelivery
from app.webhook_dispatcher import dispatch_tick, purge_delivered, BACKOFF_MINUTES, MAX_ATTEMPTS


def _seed(db, *, enabled=True, **delivery_kw):
    ep = WebhookEndpoint(name=f"ep-{id(delivery_kw)}", url="https://recv.local/hook", enabled=enabled)
    db.add(ep)
    db.commit()
    kw = dict(endpoint_id=ep.id, event_type="address.update",
              payload={"id": "u-1", "event": "address.update"})
    kw.update(delivery_kw)
    d = WebhookDelivery(**kw)
    db.add(d)
    db.commit()
    return ep, d


def _resp(status=200, text="ok"):
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


def test_tick_delivers_success(db):
    ep, d = _seed(db)
    with patch("app.webhook_dispatcher.requests.post", return_value=_resp(200)) as post:
        n = dispatch_tick(db)
    assert n == 1
    db.refresh(d)
    assert d.status == "delivered"
    assert d.response_status == 200
    assert d.delivered_at is not None
    args, kwargs = post.call_args
    assert args[0] == "https://recv.local/hook"
    assert kwargs["timeout"] == 10
    assert isinstance(kwargs["data"], bytes)          # signed raw body, not json=
    assert kwargs["headers"]["X-IPForge-Event"] == "address.update"


def test_tick_failure_schedules_backoff(db):
    ep, d = _seed(db)
    with patch("app.webhook_dispatcher.requests.post", return_value=_resp(500, "boom")):
        dispatch_tick(db)
    db.refresh(d)
    assert d.status == "pending"
    assert d.attempts == 1
    assert "500" in d.last_error
    assert d.response_status == 500
    delta = d.next_attempt_at - utcnow()
    assert timedelta(seconds=30) < delta <= timedelta(minutes=BACKOFF_MINUTES[0], seconds=5)


def test_tick_exception_counts_as_failure(db):
    ep, d = _seed(db)
    with patch("app.webhook_dispatcher.requests.post", side_effect=ConnectionError("refused")):
        dispatch_tick(db)
    db.refresh(d)
    assert d.status == "pending"
    assert d.attempts == 1
    assert "refused" in d.last_error


def test_dead_letter_after_max_attempts(db):
    ep, d = _seed(db, attempts=MAX_ATTEMPTS - 1)
    with patch("app.webhook_dispatcher.requests.post", return_value=_resp(500)):
        dispatch_tick(db)
    db.refresh(d)
    assert d.status == "dead"
    assert d.attempts == MAX_ATTEMPTS


def test_tick_skips_not_due_and_disabled(db):
    _seed(db, next_attempt_at=utcnow() + timedelta(hours=1))   # not due
    _seed(db, enabled=False)                                    # endpoint disabled
    with patch("app.webhook_dispatcher.requests.post", return_value=_resp(200)) as post:
        n = dispatch_tick(db)
    assert n == 0
    post.assert_not_called()


def test_purge_delivered_old_rows(db):
    ep, d = _seed(db, status="delivered")
    d.created_at = utcnow() - timedelta(days=31)
    ep2, dead = _seed(db, status="dead")
    dead.created_at = utcnow() - timedelta(days=90)
    db.commit()
    purged = purge_delivered(db)
    assert purged == 1
    assert db.query(WebhookDelivery).count() == 1   # dead row kept forever
