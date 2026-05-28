"""AUTOMATION-RULES-001 — rule CRUD (admin)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import require_admin
from app.database import get_db
from app.models.address import AddressStatus
from app.models.automation import AutomationRule
from app.models.user import User

router = APIRouter()

TriggerType = Literal["rogue", "drift"]


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    trigger_type: TriggerType
    condition: dict = Field(default_factory=dict)
    action: dict = Field(default_factory=dict)
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    trigger_type: TriggerType | None = None
    condition: dict | None = None
    action: dict | None = None
    enabled: bool | None = None


def _validate_action(action: dict) -> None:
    status = action.get("set_status")
    tags = action.get("add_tags")
    if status is not None:
        try:
            AddressStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid set_status: {status}")
    if not status and not tags:
        raise HTTPException(400, "action must set_status and/or add_tags")


def _out(r: AutomationRule) -> dict:
    return {
        "id": r.id, "name": r.name, "trigger_type": r.trigger_type,
        "condition": r.condition, "action": r.action, "enabled": r.enabled,
    }


@router.get("/rules")
def list_rules(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_out(r) for r in db.query(AutomationRule).order_by(AutomationRule.name).all()]


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    _validate_action(body.action)
    if db.query(AutomationRule).filter_by(name=body.name).first():
        raise HTTPException(409, f"Rule {body.name!r} already exists")
    r = AutomationRule(name=body.name, trigger_type=body.trigger_type,
                       condition=body.condition, action=body.action, enabled=body.enabled)
    db.add(r)
    db.flush()
    write_audit(db, current_user.username, "create", "automation_rule", str(r.id), r.name)
    db.commit()
    db.refresh(r)
    return _out(r)


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(AutomationRule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found")
    data = body.model_dump(exclude_unset=True)
    if "action" in data and data["action"] is not None:
        _validate_action(data["action"])
    for k, v in data.items():
        setattr(r, k, v)
    write_audit(db, current_user.username, "update", "automation_rule", str(r.id), r.name)
    db.commit()
    db.refresh(r)
    return _out(r)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    r = db.get(AutomationRule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found")
    write_audit(db, current_user.username, "delete", "automation_rule", str(r.id), r.name)
    db.delete(r)
    db.commit()
    return Response(status_code=204)
