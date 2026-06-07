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
