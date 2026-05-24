import json
from datetime import datetime, timezone
import pytest
from app.alerting.models import AlertChannel, AlertRule, AlertingEvent


def test_channel_defaults(db_session):
    ch = AlertChannel(name="ops-smtp", kind="smtp", config={"host": "smtp.example.com"})
    db_session.add(ch)
    db_session.commit()
    assert ch.enabled is True
    assert ch.id is not None
    assert ch.secret_enc is None


def test_rule_with_recipients(db_session):
    r = AlertRule(
        name="prod collisions", trigger_type="collision",
        condition={}, channel_ids=[1], recipients=["a@x", "b@y"], enabled=True,
    )
    db_session.add(r)
    db_session.commit()
    assert r.recipients == ["a@x", "b@y"]


def test_event_state_machine_fields(db_session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    e = AlertingEvent(
        rule_id=None, resource_key="ip:10.0.0.1", state="firing",
        first_fired_at=now, last_fired_at=now, payload={}, deliveries=[],
    )
    db_session.add(e)
    db_session.commit()
    assert e.state == "firing"
    assert e.resolved_at is None
