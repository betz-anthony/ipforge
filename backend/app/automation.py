"""AUTOMATION-RULES-001 — execute tag/status actions on trigger events."""
import logging

from app.alerting.emit import TriggerEvent
from app.core.audit import write_audit
from app.core.custom_fields import add_tags
from app.models.address import IPAddress, AddressStatus
from app.models.automation import AutomationRule

logger = logging.getLogger(__name__)


def _matches(rule: AutomationRule, te: TriggerEvent) -> bool:
    cond = rule.condition or {}
    cat = cond.get("category")
    if cat and te.context.get("category") != cat:
        return False
    return True


def run_automation(db, te: TriggerEvent) -> None:
    """Apply enabled automation rules for this trigger event to the matching address."""
    rules = (
        db.query(AutomationRule)
        .filter(AutomationRule.trigger_type == te.trigger_type, AutomationRule.enabled.is_(True))
        .all()
    )
    if not rules:
        return
    ip = te.context.get("ip")
    if not ip:
        return
    addr = db.query(IPAddress).filter_by(address=ip).first()
    if addr is None:
        return

    changed = False
    for rule in rules:
        if not _matches(rule, te):
            continue
        action = rule.action or {}
        applied: dict = {}

        new_status = action.get("set_status")
        if new_status:
            try:
                addr.status = AddressStatus(new_status)
                applied["set_status"] = new_status
            except ValueError:
                logger.warning("automation rule %s: invalid status %r", rule.name, new_status)

        tags = action.get("add_tags") or []
        if tags:
            add_tags(db, "address", addr.id, tags)
            applied["add_tags"] = tags

        if applied:
            write_audit(db, f"automation:{rule.name}", "automation", "address", str(addr.id),
                        addr.address, after=applied)
            changed = True

    if changed:
        db.commit()
