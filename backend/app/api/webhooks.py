"""WEBHOOK-OUT-001: admin CRUD for webhook endpoints + delivery log."""
import uuid as _uuid

import requests
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.crypto import encrypt_secret
from app.core.deps import require_admin
from app.core.time import utcnow
from app.database import get_db
from app.models.webhook import WebhookDelivery, WebhookEndpoint
from app.schemas.webhook import (
    WebhookDeliveryOut, WebhookEndpointIn, WebhookEndpointOut, WebhookTestResult,
)
from app.webhook_dispatcher import build_request

router = APIRouter()


def _404():
    raise HTTPException(404, "webhook endpoint not found")


def _out(db: Session, ep: WebhookEndpoint) -> WebhookEndpointOut:
    last = (
        db.query(WebhookDelivery.status)
        .filter(WebhookDelivery.endpoint_id == ep.id)
        .order_by(WebhookDelivery.id.desc())
        .first()
    )
    dead = (
        db.query(func.count(WebhookDelivery.id))
        .filter(WebhookDelivery.endpoint_id == ep.id, WebhookDelivery.status == "dead")
        .scalar()
    )
    return WebhookEndpointOut(
        id=ep.id, name=ep.name, url=ep.url, enabled=ep.enabled,
        has_secret=bool(ep.secret_enc),
        custom_headers=ep.custom_headers or {},
        resource_types=ep.resource_types or [],
        actions=ep.actions or [],
        last_status=last[0] if last else None,
        dead_count=dead or 0,
        created_at=ep.created_at, updated_at=ep.updated_at,
    )


@router.get("", response_model=list[WebhookEndpointOut])
def list_endpoints(db: Session = Depends(get_db)):
    return [_out(db, ep) for ep in db.query(WebhookEndpoint).order_by(WebhookEndpoint.name).all()]


@router.post("", response_model=WebhookEndpointOut)
def create_endpoint(body: WebhookEndpointIn, db: Session = Depends(get_db),
                    user=Depends(require_admin)):
    if db.query(WebhookEndpoint).filter(WebhookEndpoint.name == body.name).first():
        raise HTTPException(409, "webhook name exists")
    ep = WebhookEndpoint(
        name=body.name, url=body.url, enabled=body.enabled,
        custom_headers=body.custom_headers,
        resource_types=body.resource_types, actions=body.actions,
    )
    if body.secret:
        ep.secret_enc = encrypt_secret(body.secret)
    db.add(ep)
    db.flush()
    write_audit(db, user.username, "create", "webhook_endpoint", str(ep.id), ep.name,
                after={"name": ep.name, "url": ep.url, "enabled": ep.enabled})
    db.commit()
    return _out(db, ep)


@router.put("/{ep_id}", response_model=WebhookEndpointOut)
def update_endpoint(ep_id: int, body: WebhookEndpointIn, db: Session = Depends(get_db),
                    user=Depends(require_admin)):
    ep = db.get(WebhookEndpoint, ep_id) or _404()
    dup = db.query(WebhookEndpoint).filter(
        WebhookEndpoint.name == body.name, WebhookEndpoint.id != ep_id).first()
    if dup:
        raise HTTPException(409, "webhook name exists")
    before = {"name": ep.name, "url": ep.url, "enabled": ep.enabled}
    ep.name = body.name
    ep.url = body.url
    ep.enabled = body.enabled
    ep.custom_headers = body.custom_headers
    ep.resource_types = body.resource_types
    ep.actions = body.actions
    if body.secret is not None:
        ep.secret_enc = encrypt_secret(body.secret) if body.secret else None
    write_audit(db, user.username, "update", "webhook_endpoint", str(ep.id), ep.name,
                before=before, after={"name": ep.name, "url": ep.url, "enabled": ep.enabled})
    db.commit()
    db.refresh(ep)
    return _out(db, ep)


@router.delete("/{ep_id}", status_code=204)
def delete_endpoint(ep_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    ep = db.get(WebhookEndpoint, ep_id) or _404()
    name = ep.name
    # ondelete=CASCADE covers Postgres; delete rows explicitly for SQLite tests too
    db.query(WebhookDelivery).filter(WebhookDelivery.endpoint_id == ep_id).delete(
        synchronize_session=False)
    db.delete(ep)
    write_audit(db, user.username, "delete", "webhook_endpoint", str(ep_id), name)
    db.commit()
    return Response(status_code=204)


@router.post("/{ep_id}/test", response_model=WebhookTestResult)
def test_endpoint(ep_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    ep = db.get(WebhookEndpoint, ep_id) or _404()
    payload = {
        "id": str(_uuid.uuid4()),
        "event": "ping",
        "timestamp": utcnow().isoformat() + "Z",
        "actor": user.username,
        "resource_type": "webhook_endpoint",
        "resource_id": str(ep.id),
        "summary": f"Test ping for webhook '{ep.name}'",
        "before": None,
        "after": None,
    }
    body, headers = build_request(ep, payload)
    try:
        r = requests.post(ep.url, data=body, headers=headers, timeout=10)
        if 200 <= r.status_code < 300:
            return WebhookTestResult(status="sent", response_status=r.status_code)
        return WebhookTestResult(status="failed", response_status=r.status_code,
                                 error=f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as exc:
        return WebhookTestResult(status="failed", error=str(exc))


@router.get("/{ep_id}/deliveries")
def list_deliveries(ep_id: int, status: str | None = None, limit: int = 50, offset: int = 0,
                    db: Session = Depends(get_db)):
    db.get(WebhookEndpoint, ep_id) or _404()
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = db.query(WebhookDelivery).filter(WebhookDelivery.endpoint_id == ep_id)
    if status:
        q = q.filter(WebhookDelivery.status == status)
    total = q.count()
    rows = q.order_by(WebhookDelivery.id.desc()).offset(offset).limit(limit).all()
    return {"total": total,
            "items": [WebhookDeliveryOut.model_validate(r) for r in rows]}


@router.post("/deliveries/{d_id}/redeliver", response_model=WebhookDeliveryOut)
def redeliver(d_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    d = db.get(WebhookDelivery, d_id)
    if not d:
        raise HTTPException(404, "delivery not found")
    if d.status == "delivering":
        raise HTTPException(409, "delivery in flight")
    d.status = "pending"
    d.attempts = 0
    d.next_attempt_at = utcnow()
    d.last_error = None
    write_audit(db, user.username, "redeliver", "webhook_delivery", str(d.id), d.event_type)
    db.commit()
    db.refresh(d)
    return WebhookDeliveryOut.model_validate(d)


@router.delete("/deliveries/{d_id}", status_code=204)
def delete_delivery(d_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    d = db.get(WebhookDelivery, d_id)
    if not d:
        raise HTTPException(404, "delivery not found")
    db.delete(d)
    write_audit(db, user.username, "delete", "webhook_delivery", str(d.id), d.event_type)
    db.commit()
    return Response(status_code=204)
