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
