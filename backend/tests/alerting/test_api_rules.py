def test_create_rule(client_admin):
    ch_id = client_admin.post("/api/alerts/channels",
                              json={"name": "c", "kind": "generic", "config": {"url": "u"}}).json()["id"]
    r = client_admin.post("/api/alerts/rules", json={
        "name": "prod-collisions", "trigger_type": "collision", "condition": {},
        "channel_ids": [ch_id], "recipients": [], "renotify_minutes": 60, "enabled": True,
    })
    assert r.status_code == 201, r.text
    assert r.json()["trigger_type"] == "collision"


def test_rule_rejects_unknown_channel(client_admin):
    r = client_admin.post("/api/alerts/rules", json={
        "name": "x", "trigger_type": "collision", "channel_ids": [99999], "condition": {},
    })
    assert r.status_code == 400


def test_rule_smtp_recipients_required(client_admin):
    ch_id = client_admin.post("/api/alerts/channels",
                              json={"name": "smtp", "kind": "smtp",
                                    "config": {"host": "h", "port": 25, "tls": False, "user": None,
                                               "from": "x@y"}}).json()["id"]
    r = client_admin.post("/api/alerts/rules", json={
        "name": "x", "trigger_type": "collision", "channel_ids": [ch_id], "recipients": [], "condition": {},
    })
    assert r.status_code == 400
    assert "recipients" in r.text.lower()


def test_list_update_delete_rule(client_admin):
    ch_id = client_admin.post("/api/alerts/channels",
                              json={"name": "c", "kind": "generic", "config": {"url": "u"}}).json()["id"]
    rid = client_admin.post("/api/alerts/rules", json={"name": "r", "trigger_type": "sync_error",
                                                        "channel_ids": [ch_id], "condition": {},
                                                        "recipients": []}).json()["id"]
    assert client_admin.get("/api/alerts/rules").status_code == 200
    upd = client_admin.put(f"/api/alerts/rules/{rid}",
                           json={"name": "r2", "trigger_type": "sync_error", "channel_ids": [ch_id],
                                 "condition": {}, "recipients": [], "enabled": False})
    assert upd.json()["enabled"] is False
    assert client_admin.delete(f"/api/alerts/rules/{rid}").status_code == 204


def test_rule_duplicate_name_409(client_admin):
    ch_id = client_admin.post("/api/alerts/channels",
                              json={"name": "c", "kind": "generic", "config": {"url": "u"}}).json()["id"]
    client_admin.post("/api/alerts/rules", json={"name": "dup", "trigger_type": "collision",
                                                  "channel_ids": [ch_id], "recipients": [], "condition": {}})
    r = client_admin.post("/api/alerts/rules", json={"name": "dup", "trigger_type": "sync_error",
                                                      "channel_ids": [ch_id], "recipients": [], "condition": {}})
    assert r.status_code == 409


def test_update_rule_rejects_rename_to_existing(client_admin):
    ch_id = client_admin.post("/api/alerts/channels",
                              json={"name": "c", "kind": "generic", "config": {"url": "u"}}).json()["id"]
    a = client_admin.post("/api/alerts/rules", json={"name": "a", "trigger_type": "collision",
                                                      "channel_ids": [ch_id], "recipients": [], "condition": {}}).json()
    b = client_admin.post("/api/alerts/rules", json={"name": "b", "trigger_type": "collision",
                                                      "channel_ids": [ch_id], "recipients": [], "condition": {}}).json()
    r = client_admin.put(f"/api/alerts/rules/{b['id']}", json={
        "name": "a", "trigger_type": "collision", "channel_ids": [ch_id], "recipients": [],
        "condition": {}, "enabled": True,
    })
    assert r.status_code == 409


def test_non_admin_forbidden_on_rules(client_operator):
    r = client_operator.post("/api/alerts/rules", json={"name": "x", "trigger_type": "collision",
                                                         "channel_ids": [], "recipients": [], "condition": {}})
    assert r.status_code == 403
