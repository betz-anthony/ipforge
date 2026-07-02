from app.models.webhook import WebhookEndpoint, WebhookDelivery
from app.webhook_outbox import matches, enqueue_webhooks
from app.core.audit import write_audit


def _ep(**kw):
    defaults = dict(name="ep", url="https://x/h", enabled=True)
    defaults.update(kw)
    return WebhookEndpoint(**defaults)


def test_matches_empty_filters_match_all():
    assert matches(_ep(), "address", "update") is True


def test_matches_resource_type_filter():
    ep = _ep(resource_types=["subnet"])
    assert matches(ep, "subnet", "create") is True
    assert matches(ep, "address", "create") is False


def test_matches_action_filter():
    ep = _ep(actions=["delete"])
    assert matches(ep, "address", "delete") is True
    assert matches(ep, "address", "update") is False


def test_enqueue_creates_row_with_payload(db):
    db.add(_ep())
    db.commit()
    enqueue_webhooks(db, username="admin", action="update", resource_type="address",
                     resource_id="42", summary="s", before={"h": "a"}, after={"h": "b"})
    db.commit()
    d = db.query(WebhookDelivery).one()
    assert d.event_type == "address.update"
    assert d.status == "pending"
    p = d.payload
    assert p["id"] == d.uuid
    assert p["event"] == "address.update"
    assert p["actor"] == "admin"
    assert p["resource_id"] == "42"
    assert p["before"] == {"h": "a"}
    assert p["after"] == {"h": "b"}


def test_enqueue_skips_disabled_and_nonmatching(db):
    db.add(_ep(name="off", enabled=False))
    db.add(_ep(name="other", resource_types=["subnet"]))
    db.commit()
    enqueue_webhooks(db, username="u", action="update", resource_type="address",
                     resource_id="1", summary="s", before=None, after=None)
    db.commit()
    assert db.query(WebhookDelivery).count() == 0


def test_write_audit_enqueues_in_same_transaction(db):
    db.add(_ep())
    db.commit()
    write_audit(db, "admin", "create", "subnet", "7", "10.0.0.0/24")
    db.rollback()  # audited write rolled back → outbox row must vanish too
    assert db.query(WebhookDelivery).count() == 0
    write_audit(db, "admin", "create", "subnet", "7", "10.0.0.0/24")
    db.commit()
    assert db.query(WebhookDelivery).count() == 1


def test_write_audit_survives_outbox_failure(db, monkeypatch):
    db.add(_ep())
    db.commit()
    import app.core.audit as audit_mod

    def boom(*a, **kw):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(audit_mod, "enqueue_webhooks", boom)
    write_audit(db, "admin", "create", "subnet", "7", "10.0.0.0/24")  # must not raise
    db.commit()
