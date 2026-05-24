"""Transport implementations: SMTP + HTTP webhook."""
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
import requests
from app.alerting.models import AlertChannel
from app.core.crypto import decrypt_secret
from app.core.time import utcnow


@dataclass
class DeliveryResult:
    status: str  # "sent" | "failed"
    error: str | None = None
    attempted_at: str = field(default_factory=lambda: utcnow().isoformat())


def _smtp_password(channel: AlertChannel) -> str | None:
    if not channel.secret_enc:
        return None
    return decrypt_secret(channel.secret_enc)


def send_smtp(channel: AlertChannel, *, recipients: list[str], subject: str, body: str) -> DeliveryResult:
    cfg = channel.config or {}
    host = cfg.get("host")
    port = int(cfg.get("port", 25))
    tls = bool(cfg.get("tls", False))
    user = cfg.get("user")
    from_addr = cfg.get("from", user or "noreply@ipforge")
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=10) as s:
            if tls:
                s.starttls()
            if user:
                pw = _smtp_password(channel)
                s.login(user, pw or "")
            s.send_message(msg)
        return DeliveryResult(status="sent")
    except Exception as exc:
        return DeliveryResult(status="failed", error=str(exc))


def send_webhook(channel: AlertChannel, *, payload: dict) -> DeliveryResult:
    cfg = channel.config or {}
    url = cfg.get("url")
    headers = dict(cfg.get("headers") or {})
    if channel.secret_enc:
        token = decrypt_secret(channel.secret_enc)
        headers.setdefault("Authorization", f"Bearer {token}")
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if 200 <= r.status_code < 300:
            return DeliveryResult(status="sent")
        return DeliveryResult(status="failed", error=f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as exc:
        return DeliveryResult(status="failed", error=str(exc))
