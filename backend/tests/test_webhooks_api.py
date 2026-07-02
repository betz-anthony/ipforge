from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from app.models.webhook import WebhookDelivery, WebhookEndpoint


def _create(client, **overrides):
    body = {"name": "n8n", "url": "https://n8n.local/hook", "secret": "s3cret",
            "custom_headers": {"X-Api-Key": "k"}, "resource_types": ["address"], "actions": []}
    body.update(overrides)
    r = client.post("/api/v1/webhooks", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_and_list_no_secret_leak(client, db, monkeypatch):
    # A real SECRET_KEY so encrypt_secret actually encrypts (default test env has none
    # configured, in which case encrypt_secret is an intentional plaintext passthrough —
    # see test_secrets.py::test_no_key_encrypt_is_noop). Assert real encryption here.
    monkeypatch.setattr("app.config.settings.secret_key", Fernet.generate_key().decode())
    ep = _create(client)
    assert ep["has_secret"] is True
    assert "secret" not in ep and "secret_enc" not in ep
    r = client.get("/api/v1/webhooks")
    assert r.status_code == 200
    listed = r.json()[0]
    assert listed["name"] == "n8n"
    assert "secret" not in listed and "secret_enc" not in listed
    row = db.query(WebhookEndpoint).one()
    assert row.secret_enc is not None and row.secret_enc != "s3cret"  # encrypted, never plaintext


def test_duplicate_name_409(client, db):
    _create(client)
    r = client.post("/api/v1/webhooks", json={"name": "n8n", "url": "https://other/h"})
    assert r.status_code == 409


def test_update_secret_semantics(client, db):
    ep = _create(client)
    # omitted secret → unchanged
    r = client.put(f"/api/v1/webhooks/{ep['id']}", json={"name": "n8n", "url": "https://n8n.local/hook"})
    assert r.status_code == 200 and r.json()["has_secret"] is True
    # empty string → cleared
    r = client.put(f"/api/v1/webhooks/{ep['id']}",
                   json={"name": "n8n", "url": "https://n8n.local/hook", "secret": ""})
    assert r.status_code == 200 and r.json()["has_secret"] is False


def test_delete_cascades_deliveries(client, db):
    ep = _create(client)
    db.add(WebhookDelivery(endpoint_id=ep["id"], event_type="ping", payload={"id": "u", "event": "ping"}))
    db.commit()
    r = client.delete(f"/api/v1/webhooks/{ep['id']}")
    assert r.status_code == 204
    assert db.query(WebhookDelivery).count() == 0


def test_test_ping(client, db):
    ep = _create(client)
    resp = MagicMock(); resp.status_code = 204; resp.text = ""
    with patch("app.api.webhooks.requests.post", return_value=resp) as post:
        r = client.post(f"/api/v1/webhooks/{ep['id']}/test")
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "sent" and out["response_status"] == 204
    kwargs = post.call_args.kwargs
    assert kwargs["headers"]["X-IPForge-Event"] == "ping"
    assert "X-IPForge-Signature-256" in kwargs["headers"]
    assert db.query(WebhookDelivery).count() == 0   # test pings are not persisted


def test_test_ping_failure_reported(client, db):
    ep = _create(client)
    with patch("app.api.webhooks.requests.post", side_effect=ConnectionError("refused")):
        r = client.post(f"/api/v1/webhooks/{ep['id']}/test")
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert "refused" in r.json()["error"]


def test_delivery_log_filter_and_redeliver(client, db):
    ep = _create(client)
    d1 = WebhookDelivery(endpoint_id=ep["id"], event_type="address.update",
                         payload={"id": "u1", "event": "address.update"}, status="dead", attempts=5)
    d2 = WebhookDelivery(endpoint_id=ep["id"], event_type="subnet.create",
                         payload={"id": "u2", "event": "subnet.create"}, status="delivered")
    db.add_all([d1, d2]); db.commit()

    r = client.get(f"/api/v1/webhooks/{ep['id']}/deliveries?status=dead")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["status"] == "dead"

    r = client.post(f"/api/v1/webhooks/deliveries/{d1.id}/redeliver")
    assert r.status_code == 200
    db.refresh(d1)
    assert d1.status == "pending" and d1.attempts == 0

    r = client.delete(f"/api/v1/webhooks/deliveries/{d2.id}")
    assert r.status_code == 204


def test_endpoint_summary_dead_count(client, db):
    ep = _create(client)
    db.add(WebhookDelivery(endpoint_id=ep["id"], event_type="x.y",
                           payload={"id": "u", "event": "x.y"}, status="dead", attempts=5))
    db.commit()
    r = client.get("/api/v1/webhooks")
    assert r.json()[0]["dead_count"] == 1


def test_requires_admin(client_operator, db):
    r = client_operator.get("/api/v1/webhooks")
    assert r.status_code == 403
    r = client_operator.post("/api/v1/webhooks", json={"name": "x", "url": "https://x/h"})
    assert r.status_code == 403
