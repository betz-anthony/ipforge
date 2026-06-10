from app.core.time import utcnow


def test_list_events_filters(client_gr, db):
    from app.alerting.models import AlertingEvent
    db.add_all([
        AlertingEvent(rule_id=None, resource_key="ip:1", state="firing",
                      first_fired_at=utcnow(), last_fired_at=utcnow(), payload={}, deliveries=[]),
        AlertingEvent(rule_id=None, resource_key="ip:2", state="resolved",
                      first_fired_at=utcnow(), last_fired_at=utcnow(),
                      resolved_at=utcnow(), payload={}, deliveries=[]),
    ])
    db.commit()
    r = client_gr.get("/api/v1/alerts/events?state=firing")
    assert r.status_code == 200
    body = r.json()
    assert all(e["state"] == "firing" for e in body)
    assert any(e["resource_key"] == "ip:1" for e in body)


def test_list_events_all(client_gr, db):
    from app.alerting.models import AlertingEvent
    db.add(AlertingEvent(rule_id=None, resource_key="x", state="firing",
                         first_fired_at=utcnow(), last_fired_at=utcnow(), payload={}, deliveries=[]))
    db.commit()
    r = client_gr.get("/api/v1/alerts/events")
    assert r.status_code == 200


def test_ack_resolves_event(client_operator, db):
    from app.alerting.models import AlertingEvent
    e = AlertingEvent(rule_id=None, resource_key="x", state="firing",
                      first_fired_at=utcnow(), last_fired_at=utcnow(), payload={}, deliveries=[])
    db.add(e); db.commit()
    eid = e.id
    r = client_operator.post(f"/api/v1/alerts/events/{eid}/ack")
    assert r.status_code == 200, r.text
    e2 = db.get(AlertingEvent, eid)
    db.refresh(e2)
    assert e2.state == "resolved"


def test_scoped_user_403_on_events(client_scoped):
    r = client_scoped.get("/api/v1/alerts/events")
    assert r.status_code == 403


def test_readonly_can_list_but_not_ack(client_gr, db):
    from app.alerting.models import AlertingEvent
    e = AlertingEvent(rule_id=None, resource_key="x", state="firing",
                      first_fired_at=utcnow(), last_fired_at=utcnow(), payload={}, deliveries=[])
    db.add(e); db.commit()
    eid = e.id
    assert client_gr.get("/api/v1/alerts/events").status_code == 200
    assert client_gr.post(f"/api/v1/alerts/events/{eid}/ack").status_code == 403
