from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import desc
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import require_admin, require_operator, require_global_read
from app.core.audit import write_audit
from app.core.crypto import encrypt_secret
from app.core.time import utcnow
from app.alerting.models import AlertChannel, AlertRule, AlertingEvent
from app.alerting.schemas import ChannelIn, ChannelOut, RuleIn, RuleOut, EventOut
from app.alerting.delivery import send_smtp, send_webhook
from app.alerting.payload import (
    to_generic, to_slack, to_teams, to_pagerduty, build_subject, build_body,
)
from app.alerting.state import transition_to_resolved

router = APIRouter()


def _404():
    raise HTTPException(404, "not found")


# ------------- channels -------------
@router.get("/channels", response_model=list[ChannelOut],
            dependencies=[Depends(require_admin)])
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


# ------------- rules -------------
def _validate_rule(db: Session, body: RuleIn) -> None:
    for cid in body.channel_ids:
        ch = db.get(AlertChannel, cid)
        if not ch:
            raise HTTPException(400, f"channel {cid} not found")
    smtp_in_rule = any(db.get(AlertChannel, cid).kind == "smtp" for cid in body.channel_ids)
    if smtp_in_rule and not body.recipients:
        raise HTTPException(400, "recipients required when an SMTP channel is selected")


@router.get("/rules", response_model=list[RuleOut],
            dependencies=[Depends(require_admin)])
def list_rules(db: Session = Depends(get_db)):
    return [RuleOut.from_orm(r) for r in db.query(AlertRule).order_by(AlertRule.name).all()]


@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(body: RuleIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    if db.query(AlertRule).filter_by(name=body.name).first():
        raise HTTPException(409, "rule name exists")
    _validate_rule(db, body)
    r = AlertRule(name=body.name, trigger_type=body.trigger_type, condition=body.condition,
                  channel_ids=body.channel_ids, recipients=body.recipients,
                  renotify_minutes=body.renotify_minutes, enabled=body.enabled)
    db.add(r); db.commit(); db.refresh(r)
    write_audit(db, user.username, "create", "alert_rule", str(r.id), r.name,
                after={"name": r.name, "trigger": r.trigger_type})
    return RuleOut.from_orm(r)


@router.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, body: RuleIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    r = db.get(AlertRule, rule_id) or _404()
    dup = db.query(AlertRule).filter(AlertRule.name == body.name, AlertRule.id != rule_id).first()
    if dup:
        raise HTTPException(409, "rule name exists")
    _validate_rule(db, body)
    before = {"name": r.name, "trigger": r.trigger_type, "enabled": r.enabled}
    r.name, r.trigger_type, r.condition = body.name, body.trigger_type, body.condition
    r.channel_ids, r.recipients, r.renotify_minutes, r.enabled = (
        body.channel_ids, body.recipients, body.renotify_minutes, body.enabled
    )
    db.commit()
    write_audit(db, user.username, "update", "alert_rule", str(r.id), r.name,
                before=before, after={"name": r.name, "trigger": r.trigger_type, "enabled": r.enabled})
    return RuleOut.from_orm(r)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    r = db.get(AlertRule, rule_id) or _404()
    name = r.name
    db.delete(r); db.commit()
    write_audit(db, user.username, "delete", "alert_rule", str(rule_id), name)
    return Response(status_code=204)


# ------------- events -------------
@router.get("/events", response_model=list[EventOut], dependencies=[Depends(require_global_read)])
def list_events(state: str | None = None, trigger_type: str | None = None,
                limit: int = 200, db: Session = Depends(get_db)):
    q = db.query(AlertingEvent)
    if state:
        q = q.filter(AlertingEvent.state == state)
    if trigger_type:
        q = q.join(AlertRule, AlertingEvent.rule_id == AlertRule.id).filter(AlertRule.trigger_type == trigger_type)
    q = q.order_by(desc(AlertingEvent.last_fired_at)).limit(min(limit, 1000))
    return [EventOut.from_orm(e) for e in q.all()]


@router.post("/events/{event_id}/ack", response_model=EventOut)
def ack_event(event_id: int, db: Session = Depends(get_db), user=Depends(require_operator)):
    e = db.get(AlertingEvent, event_id) or _404()
    if e.state == "firing":
        transition_to_resolved(db, e)
        write_audit(db, user.username, "update", "alert_event", str(event_id),
                    e.resource_key, after={"state": "resolved"})
    return EventOut.from_orm(e)
