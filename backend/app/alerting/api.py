from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import require_admin
from app.core.audit import write_audit
from app.core.crypto import encrypt_secret
from app.core.time import utcnow
from app.alerting.models import AlertChannel, AlertRule, AlertingEvent
from app.alerting.schemas import ChannelIn, ChannelOut, RuleIn, RuleOut, EventOut
from app.alerting.delivery import send_smtp, send_webhook
from app.alerting.payload import (
    to_generic, to_slack, to_teams, to_pagerduty, build_subject, build_body,
)

router = APIRouter()


def _404():
    raise HTTPException(404, "not found")


# ------------- channels -------------
@router.get("/channels", response_model=list[ChannelOut])
def list_channels(db: Session = Depends(get_db)):
    return [ChannelOut.from_orm_safe(c) for c in db.query(AlertChannel).order_by(AlertChannel.name).all()]


@router.post("/channels", response_model=ChannelOut, status_code=201)
def create_channel(body: ChannelIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    if db.query(AlertChannel).filter_by(name=body.name).first():
        raise HTTPException(409, "channel name exists")
    ch = AlertChannel(name=body.name, kind=body.kind, config=body.config, enabled=body.enabled)
    if body.secret:
        ch.secret_enc = encrypt_secret(body.secret)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    write_audit(db, user.username, "create", "alert_channel", str(ch.id), ch.name,
                after={"name": ch.name, "kind": ch.kind})
    return ChannelOut.from_orm_safe(ch)


@router.put("/channels/{ch_id}", response_model=ChannelOut)
def update_channel(ch_id: int, body: ChannelIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    ch = db.get(AlertChannel, ch_id) or _404()
    existing = db.query(AlertChannel).filter(
        AlertChannel.name == body.name,
        AlertChannel.id != ch_id,
    ).first()
    if existing:
        raise HTTPException(409, "channel name exists")
    before = {"name": ch.name, "kind": ch.kind, "enabled": ch.enabled}
    ch.name = body.name
    ch.kind = body.kind
    ch.config = body.config
    ch.enabled = body.enabled
    if body.secret is not None:
        ch.secret_enc = encrypt_secret(body.secret) if body.secret else None
    db.commit()
    write_audit(db, user.username, "update", "alert_channel", str(ch.id), ch.name,
                before=before, after={"name": ch.name, "kind": ch.kind, "enabled": ch.enabled})
    return ChannelOut.from_orm_safe(ch)


@router.delete("/channels/{ch_id}", status_code=204)
def delete_channel(ch_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    ch = db.get(AlertChannel, ch_id) or _404()
    name = ch.name
    db.delete(ch)
    db.commit()
    write_audit(db, user.username, "delete", "alert_channel", str(ch_id), name)
    return Response(status_code=204)


@router.post("/channels/{ch_id}/test")
def test_channel(ch_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    ch = db.get(AlertChannel, ch_id) or _404()
    fake_event = AlertingEvent(
        id=0, rule_id=None, resource_key="test:synthetic", state="firing",
        first_fired_at=utcnow(), last_fired_at=utcnow(),
        payload={"trigger": "test", "context": {"note": "synthetic test from IPForge"}},
        deliveries=[],
    )
    fake_rule = AlertRule(id=0, name="(test)", trigger_type="collision", channel_ids=[ch_id])
    if ch.kind == "smtp":
        result = send_smtp(ch, recipients=["test@example.com"],
                           subject=build_subject(fake_event, fake_rule),
                           body=build_body(fake_event, fake_rule))
    else:
        builder = {"generic": to_generic, "slack": to_slack, "teams": to_teams,
                   "pagerduty": to_pagerduty}.get(ch.kind, to_generic)
        result = send_webhook(ch, payload=builder(fake_event, fake_rule))
    return {"status": result.status, "error": result.error}
