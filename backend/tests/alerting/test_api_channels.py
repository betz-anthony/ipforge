def test_create_channel_admin(client_admin):
    r = client_admin.post("/api/alerts/channels", json={
        "name": "ops-slack", "kind": "slack",
        "config": {"url": "https://hooks.example/x"}, "secret": None, "enabled": True,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "ops-slack"
    assert body["id"] > 0
    assert "secret_enc" not in body


def test_create_channel_encrypts_secret(client_admin, db):
    from cryptography.fernet import Fernet
    from unittest.mock import patch
    test_key = Fernet.generate_key()
    fernet = Fernet(test_key)
    with patch("app.core.crypto._fernet", return_value=fernet):
        r = client_admin.post("/api/alerts/channels", json={
            "name": "ops-smtp", "kind": "smtp",
            "config": {"host": "h", "port": 25, "tls": False, "user": "u", "from": "x@y"},
            "secret": "supersecret", "enabled": True,
        })
    assert r.status_code == 201
    from app.alerting.models import AlertChannel
    ch = db.query(AlertChannel).filter_by(name="ops-smtp").one()
    assert ch.secret_enc is not None
    # encrypted form should NOT contain plaintext
    assert "supersecret" not in (ch.secret_enc or "")


def test_list_channels(client_admin):
    client_admin.post("/api/alerts/channels", json={"name": "c1", "kind": "generic",
                                                    "config": {"url": "u"}, "enabled": True})
    r = client_admin.get("/api/alerts/channels")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_update_channel(client_admin):
    rid = client_admin.post("/api/alerts/channels", json={"name": "c", "kind": "generic",
                                                          "config": {"url": "u"}}).json()["id"]
    r = client_admin.put(f"/api/alerts/channels/{rid}", json={"name": "c2", "kind": "generic",
                                                              "config": {"url": "u"}, "enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_delete_channel(client_admin):
    rid = client_admin.post("/api/alerts/channels", json={"name": "c", "kind": "generic",
                                                          "config": {"url": "u"}}).json()["id"]
    r = client_admin.delete(f"/api/alerts/channels/{rid}")
    assert r.status_code == 204


def test_non_admin_forbidden(client_operator):
    r = client_operator.post("/api/alerts/channels", json={"name": "n", "kind": "generic",
                                                            "config": {"url": "u"}})
    assert r.status_code == 403


def test_test_channel_endpoint_calls_transport(client_admin):
    from unittest.mock import patch, MagicMock
    rid = client_admin.post("/api/alerts/channels", json={"name": "c", "kind": "generic",
                                                          "config": {"url": "u"}}).json()["id"]
    with patch("app.alerting.api.send_webhook") as sw:
        sw.return_value = MagicMock(status="sent", error=None, attempted_at="t")
        r = client_admin.post(f"/api/alerts/channels/{rid}/test")
    assert r.status_code == 200
    assert r.json()["status"] == "sent"
