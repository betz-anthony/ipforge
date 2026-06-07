"""Translate provider/upstream exceptions into friendly, role-gated errors."""
import logging
import re
from dataclasses import dataclass, replace

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_STEP_LABELS = {"dns": "DNS", "dhcp": "DHCP", "discovery": "discovery"}


def _label(step: str) -> str:
    return _STEP_LABELS.get(step, step)


@dataclass
class ErrorInfo:
    code: str
    message: str   # may contain "{step}" -> replaced with the step label
    hint: str
    status: int = 502


# Ordered: first matching rule wins. Matched (case-insensitive) against str(exc).
_PROVIDER_RULES: list[tuple[re.Pattern, ErrorInfo]] = [
    (re.compile(r"401|unauthorized|access is denied|authentication|credential", re.I),
     ErrorInfo("provider_auth_failed",
               "Could not authenticate to the {step} server.",
               "Check the provider credentials in Settings → Providers.")),
    (re.compile(r"connection|timed?\s*out|unreachable|no route|refused|getaddrinfo|name resolution", re.I),
     ErrorInfo("provider_unreachable",
               "Could not reach the {step} server.",
               "Verify the host is online and WinRM/the provider API is reachable.")),
    (re.compile(r"9714|objectnotfound|does not exist|not found|no such", re.I),
     ErrorInfo("record_not_found",
               "The record was not found on the {step} server.",
               "It may already be gone — refresh to confirm.")),
    (re.compile(r"zone .*not found|no such zone|zone does not exist", re.I),
     ErrorInfo("zone_not_found",
               "The target zone does not exist on the {step} server.",
               "Create the zone on the provider or pick an existing one.")),
    (re.compile(r"403|forbidden|permission|not authorized", re.I),
     ErrorInfo("provider_forbidden",
               "The {step} provider rejected the request (insufficient permission).",
               "Check the account/token permissions for the provider.")),
]

_GENERIC = ErrorInfo("provider_error",
                     "The {step} provider rejected the request.",
                     "Check the server logs for details.")


def classify_provider_error(exc: Exception, step: str) -> ErrorInfo:
    text = str(exc)
    for pattern, info in _PROVIDER_RULES:
        if pattern.search(text):
            return replace(info, message=info.message.format(step=_label(step)))
    return replace(_GENERIC, message=_GENERIC.message.format(step=_label(step)))


from typing import NoReturn

_PRIVILEGED_ROLES = {"admin", "operator"}


def _envelope(info: ErrorInfo, step: str, exc: Exception | None, user) -> dict:
    detail = {
        "code": info.code,
        "message": info.message.format(step=_label(step)),
        "hint": info.hint,
        "step": step,
    }
    if exc is not None and user is not None and getattr(user, "role", None) in _PRIVILEGED_ROLES:
        detail["detail"] = str(exc)
    return detail


def raise_provider_error(exc: Exception, *, step: str, user=None,
                         status: int | None = None) -> NoReturn:
    info = classify_provider_error(exc, step)
    logger.error("provider error [%s] step=%s: %s", info.code, step, exc, exc_info=True)
    raise HTTPException(status or info.status, detail=_envelope(info, step, exc, user))


def provider_unconfigured(step: str) -> NoReturn:
    info = ErrorInfo("provider_not_configured",
                     "No {step} provider is configured.",
                     "Add one in Settings → Providers.", status=502)
    raise HTTPException(info.status, detail=_envelope(info, step, None, None))
