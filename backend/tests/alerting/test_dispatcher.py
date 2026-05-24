# backend/tests/alerting/test_dispatcher.py
from unittest.mock import patch, MagicMock
from datetime import timedelta
from app.alerting.dispatcher import process_tick
from app.alerting.models import AlertChannel, AlertRule, AlertingEvent
from app.alerting.emit import emit, drain_queue, _queue
from app.core.time import utcnow


def setup_function():
    while not _queue.empty():
        _queue.get_nowait()


def _setup(db, *, channel_kind="generic"):
    ch = AlertChannel(name="ch1", kind=channel_kind, config={"url": "http://x"}, enabled=True)
    db.add(ch); db.commit()
    r = AlertRule(name="r1", trigger_type="collision", condition={}, channel_ids=[ch.id],
                  recipients=[], enabled=True)
    db.add(r); db.commit()
    return ch, r


def test_first_emit_creates_event_and_sends(db_session):
    ch, r = _setup(db_session)
    emit("collision", "ip:10.0.0.1", {"info": 1})
    with patch("app.alerting.dispatcher.send_webhook") as sw:
        sw.return_value = MagicMock(status="sent", error=None, attempted_at="t")
        process_tick(db_session)
    assert sw.call_count == 1
    e = db_session.query(AlertingEvent).filter_by(resource_key="ip:10.0.0.1").one()
    assert e.state == "firing"
    assert e.deliveries[0]["status"] == "sent"


def test_dedupe_does_not_resend_while_firing(db_session):
    ch, r = _setup(db_session)
    emit("collision", "ip:10.0.0.1", {})
    with patch("app.alerting.dispatcher.send_webhook") as sw:
        sw.return_value = MagicMock(status="sent", error=None, attempted_at="t")
        process_tick(db_session)
        emit("collision", "ip:10.0.0.1", {})
        process_tick(db_session)
    assert sw.call_count == 1
    e = db_session.query(AlertingEvent).filter_by(resource_key="ip:10.0.0.1").one()
    assert e.state == "firing"


def test_renotify_after_interval(db_session):
    ch, r = _setup(db_session)
    r.renotify_minutes = 1
    db_session.commit()
    emit("collision", "ip:10.0.0.1", {})
    with patch("app.alerting.dispatcher.send_webhook") as sw:
        sw.return_value = MagicMock(status="sent", error=None, attempted_at="t")
        process_tick(db_session)
        e = db_session.query(AlertingEvent).filter_by(resource_key="ip:10.0.0.1").one()
        e.last_fired_at = utcnow() - timedelta(minutes=2)
        db_session.commit()
        emit("collision", "ip:10.0.0.1", {})
        process_tick(db_session)
    assert sw.call_count == 2


def test_disabled_rule_skips(db_session):
    ch, r = _setup(db_session)
    r.enabled = False
    db_session.commit()
    emit("collision", "ip:10.0.0.1", {})
    with patch("app.alerting.dispatcher.send_webhook") as sw:
        process_tick(db_session)
    sw.assert_not_called()
    assert db_session.query(AlertingEvent).count() == 0


def test_smtp_channel_uses_recipients(db_session):
    ch = AlertChannel(name="email", kind="smtp",
                      config={"host": "h", "port": 25, "tls": False, "user": None, "from": "x@y"},
                      secret_enc=None, enabled=True)
    db_session.add(ch); db_session.commit()
    r = AlertRule(name="r", trigger_type="collision", channel_ids=[ch.id],
                  recipients=["a@x", "b@y"], condition={}, enabled=True)
    db_session.add(r); db_session.commit()
    emit("collision", "ip:10.0.0.1", {})
    with patch("app.alerting.dispatcher.send_smtp") as ss:
        ss.return_value = MagicMock(status="sent", error=None, attempted_at="t")
        process_tick(db_session)
    ss.assert_called_once()
    _, kw = ss.call_args
    assert kw["recipients"] == ["a@x", "b@y"]
