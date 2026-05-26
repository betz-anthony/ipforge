"""Render alert event into transport-specific payloads."""
from app.alerting.models import AlertingEvent, AlertRule


def _trigger_of(event: AlertingEvent, rule: AlertRule | None) -> str:
    if rule is not None:
        return rule.trigger_type
    return (event.payload or {}).get("trigger", "alert")


def _rule_name(rule: AlertRule | None) -> str | None:
    return rule.name if rule is not None else None


def _context(event: AlertingEvent) -> dict:
    return (event.payload or {}).get("context", {})


def build_subject(event: AlertingEvent, rule: AlertRule | None) -> str:
    return f"[IPForge] {_trigger_of(event, rule)}: {event.resource_key} ({event.state})"


def build_body(event: AlertingEvent, rule: AlertRule | None) -> str:
    lines = [
        f"Trigger: {_trigger_of(event, rule)}",
        f"Rule: {_rule_name(rule) or '(deleted)'}",
        f"Resource: {event.resource_key}",
        f"State: {event.state}",
        f"First fired: {event.first_fired_at.isoformat()}Z",
        f"Last fired: {event.last_fired_at.isoformat()}Z",
        "",
        "Context:",
    ]
    for k, v in _context(event).items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def to_generic(event: AlertingEvent, rule: AlertRule | None) -> dict:
    return {
        "trigger": _trigger_of(event, rule),
        "rule": _rule_name(rule),
        "resource": event.resource_key,
        "state": event.state,
        "fired_at": event.first_fired_at.isoformat() + "Z",
        "context": _context(event),
    }


def to_slack(event: AlertingEvent, rule: AlertRule | None) -> dict:
    return {
        "text": build_subject(event, rule),
        "attachments": [{
            "color": "danger" if event.state == "firing" else "good",
            "text": build_body(event, rule),
        }],
    }


def to_teams(event: AlertingEvent, rule: AlertRule | None) -> dict:
    body_lines = build_body(event, rule).split("\n")
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": build_subject(event, rule),
        "themeColor": "FF0000" if event.state == "firing" else "36A64F",
        "title": build_subject(event, rule),
        "sections": [{"text": "  \n".join(body_lines)}],
    }


_PD_SEVERITY = {
    "collision": "error",
    "rogue": "warning",
    "utilization": "warning",
    "sync_error": "error",
    "stale_queue": "info",
    "ip_request_submitted": "info",
    "ip_request_resolved": "info",
}


def to_pagerduty(event: AlertingEvent, rule: AlertRule | None) -> dict:
    trigger = _trigger_of(event, rule)
    return {
        "event_action": "trigger" if event.state == "firing" else "resolve",
        "dedup_key": event.resource_key,
        "payload": {
            "summary": build_subject(event, rule),
            "severity": _PD_SEVERITY.get(trigger, "warning"),
            "source": "ipforge",
            "custom_details": _context(event),
        },
    }
