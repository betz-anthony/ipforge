from app.models.webhook import WebhookEndpoint, WebhookDelivery


def test_endpoint_defaults(db):
    ep = WebhookEndpoint(name="n8n", url="https://n8n.local/hook")
    db.add(ep)
    db.commit()
    db.refresh(ep)
    assert ep.enabled is True
    assert ep.custom_headers == {}
    assert ep.resource_types == []
    assert ep.actions == []
    assert ep.secret_enc is None


def test_delivery_defaults_and_uuid(db):
    ep = WebhookEndpoint(name="x", url="https://x/h")
    db.add(ep)
    db.commit()
    d = WebhookDelivery(endpoint_id=ep.id, event_type="address.updated", payload={"a": 1})
    db.add(d)
    db.commit()
    db.refresh(d)
    assert d.status == "pending"
    assert d.attempts == 0
    assert len(d.uuid) == 36
    assert d.next_attempt_at is not None
    assert d.delivered_at is None
