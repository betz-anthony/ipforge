from unittest.mock import patch, MagicMock
from app.alerting.delivery import send_smtp, send_webhook, DeliveryResult
from app.alerting.models import AlertChannel


def test_send_smtp_uses_starttls_when_configured():
    ch = AlertChannel(name="ops", kind="smtp", config={
        "host": "smtp.example.com", "port": 587, "tls": True, "user": "u", "from": "noreply@x"
    }, secret_enc="pw")
    smtp_mock = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__.return_value = smtp_mock
    smtp_ctx.__exit__.return_value = False
    with patch("app.alerting.delivery.smtplib.SMTP", return_value=smtp_ctx), \
         patch("app.alerting.delivery.decrypt_secret", return_value="pw"):
        r = send_smtp(ch, recipients=["a@x"], subject="S", body="B")
    assert r.status == "sent"
    smtp_mock.starttls.assert_called_once()
    smtp_mock.login.assert_called_once_with("u", "pw")
    smtp_mock.send_message.assert_called_once()


def test_send_smtp_failure_returns_failed_with_error():
    ch = AlertChannel(name="ops", kind="smtp",
                      config={"host": "h", "port": 25, "tls": False, "user": "u", "from": "x"},
                      secret_enc=None)
    with patch("app.alerting.delivery.smtplib.SMTP", side_effect=ConnectionRefusedError("nope")):
        r = send_smtp(ch, recipients=["a@x"], subject="S", body="B")
    assert r.status == "failed"
    assert "nope" in r.error


def test_send_webhook_posts_payload():
    ch = AlertChannel(name="slack", kind="slack", config={"url": "https://hooks.example/x"}, secret_enc=None)
    with patch("app.alerting.delivery.requests.post") as post:
        post.return_value.status_code = 200
        r = send_webhook(ch, payload={"text": "hi"})
    assert r.status == "sent"
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == "https://hooks.example/x"
    assert kwargs["json"] == {"text": "hi"}


def test_send_webhook_5xx_is_failed():
    ch = AlertChannel(name="x", kind="generic", config={"url": "https://x"}, secret_enc=None)
    with patch("app.alerting.delivery.requests.post") as post:
        post.return_value.status_code = 503
        post.return_value.text = "down"
        r = send_webhook(ch, payload={})
    assert r.status == "failed"
    assert "503" in r.error
