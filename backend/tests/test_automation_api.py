from app.models.automation import AutomationRule


def test_create_and_list(client, db):
    r = client.post("/api/automation/rules", json={
        "name": "tag-rogue", "trigger_type": "rogue", "action": {"add_tags": ["unverified"]},
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert any(x["id"] == rid for x in client.get("/api/automation/rules").json())


def test_invalid_trigger_rejected(client, db):
    r = client.post("/api/automation/rules", json={
        "name": "x", "trigger_type": "bogus", "action": {"add_tags": ["a"]},
    })
    assert r.status_code == 422


def test_invalid_status_rejected(client, db):
    r = client.post("/api/automation/rules", json={
        "name": "x", "trigger_type": "rogue", "action": {"set_status": "nope"},
    })
    assert r.status_code == 400


def test_empty_action_rejected(client, db):
    r = client.post("/api/automation/rules", json={
        "name": "x", "trigger_type": "rogue", "action": {},
    })
    assert r.status_code == 400


def test_update_and_delete(client, db):
    rid = client.post("/api/automation/rules", json={
        "name": "r", "trigger_type": "drift", "action": {"add_tags": ["a"]},
    }).json()["id"]
    assert client.put(f"/api/automation/rules/{rid}", json={"enabled": False}).status_code == 200
    assert db.get(AutomationRule, rid).enabled is False
    assert client.delete(f"/api/automation/rules/{rid}").status_code == 204
    assert db.get(AutomationRule, rid) is None


def test_requires_admin(client_operator, db):
    r = client_operator.post("/api/automation/rules", json={
        "name": "x", "trigger_type": "rogue", "action": {"add_tags": ["a"]},
    })
    assert r.status_code == 403
