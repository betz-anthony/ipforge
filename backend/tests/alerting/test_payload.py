from datetime import datetime
from app.alerting.payload import (
    build_subject, build_body, to_generic, to_slack, to_teams, to_pagerduty,
)
from app.alerting.models import AlertingEvent, AlertRule


def _evt():
    return AlertingEvent(
        id=1, rule_id=2, resource_key="ip:10.0.1.5:hostname_mismatch",
        state="firing",
        first_fired_at=datetime(2026, 5, 24, 15, 30, 0),
        last_fired_at=datetime(2026, 5, 24, 15, 30, 0),
        payload={"trigger": "collision", "context": {"ip": "10.0.1.5", "expected": "host-a", "actual": "host-b"}},
        deliveries=[],
    )


def _rule():
    return AlertRule(id=2, name="Production collisions", trigger_type="collision", channel_ids=[1])


def test_build_subject_includes_trigger_and_summary():
    s = build_subject(_evt(), _rule())
    assert "[IPForge]" in s
    assert "collision" in s.lower()


def test_build_body_includes_resource_and_context():
    b = build_body(_evt(), _rule())
    assert "ip:10.0.1.5:hostname_mismatch" in b
    assert "host-a" in b


def test_to_generic_shape():
    p = to_generic(_evt(), _rule())
    assert p["trigger"] == "collision"
    assert p["rule"] == "Production collisions"
    assert p["resource"] == "ip:10.0.1.5:hostname_mismatch"
    assert p["state"] == "firing"
    assert "fired_at" in p
    assert p["context"]["ip"] == "10.0.1.5"


def test_to_slack_has_text_field():
    p = to_slack(_evt(), _rule())
    assert "text" in p
    assert "collision" in p["text"].lower()


def test_to_teams_is_message_card():
    p = to_teams(_evt(), _rule())
    assert p["@type"] == "MessageCard"
    assert "sections" in p


def test_to_pagerduty_v2_shape():
    p = to_pagerduty(_evt(), _rule())
    assert p["event_action"] == "trigger"
    assert p["dedup_key"] == "ip:10.0.1.5:hostname_mismatch"
    assert p["payload"]["severity"] in {"critical", "error", "warning", "info"}


def test_to_pagerduty_resolved_uses_resolve_action():
    e = _evt()
    e.state = "resolved"
    p = to_pagerduty(e, _rule())
    assert p["event_action"] == "resolve"
