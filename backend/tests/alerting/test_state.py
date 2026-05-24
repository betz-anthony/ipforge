from datetime import timedelta
from app.alerting.state import find_firing, should_renotify, transition_to_resolved
from app.alerting.models import AlertingEvent, AlertRule
from app.core.time import utcnow


def test_find_firing_returns_none_when_no_event(db_session):
    assert find_firing(db_session, rule_id=1, resource_key="ip:10.0.0.1") is None


def test_find_firing_returns_existing_firing(db_session):
    e = AlertingEvent(rule_id=1, resource_key="ip:10.0.0.1", state="firing",
                      first_fired_at=utcnow(), last_fired_at=utcnow(), payload={}, deliveries=[])
    db_session.add(e); db_session.commit()
    found = find_firing(db_session, rule_id=1, resource_key="ip:10.0.0.1")
    assert found.id == e.id


def test_find_firing_ignores_resolved(db_session):
    e = AlertingEvent(rule_id=1, resource_key="ip:10.0.0.1", state="resolved",
                      first_fired_at=utcnow(), last_fired_at=utcnow(),
                      resolved_at=utcnow(), payload={}, deliveries=[])
    db_session.add(e); db_session.commit()
    assert find_firing(db_session, 1, "ip:10.0.0.1") is None


def test_should_renotify_none_when_no_minutes_set():
    rule = AlertRule(name="r", trigger_type="collision", channel_ids=[1])
    rule.renotify_minutes = None
    e = AlertingEvent(last_fired_at=utcnow())
    assert should_renotify(rule, e, now=utcnow()) is False


def test_should_renotify_true_when_elapsed():
    rule = AlertRule(name="r", trigger_type="collision", channel_ids=[1])
    rule.renotify_minutes = 60
    e = AlertingEvent(last_fired_at=utcnow() - timedelta(minutes=61))
    assert should_renotify(rule, e, now=utcnow()) is True


def test_should_renotify_false_when_too_recent():
    rule = AlertRule(name="r", trigger_type="collision", channel_ids=[1])
    rule.renotify_minutes = 60
    e = AlertingEvent(last_fired_at=utcnow() - timedelta(minutes=30))
    assert should_renotify(rule, e, now=utcnow()) is False


def test_transition_to_resolved_sets_fields(db_session):
    e = AlertingEvent(rule_id=1, resource_key="x", state="firing",
                     first_fired_at=utcnow(), last_fired_at=utcnow(),
                     payload={}, deliveries=[])
    db_session.add(e); db_session.commit()
    transition_to_resolved(db_session, e)
    assert e.state == "resolved"
    assert e.resolved_at is not None
