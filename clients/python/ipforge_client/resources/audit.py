from typing import Optional

from ..models import AuditEntry
from ..pagination import CursorIterator


class Audit:
    def __init__(self, transport):
        self._t = transport

    def list(self, resource_type: Optional[str] = None, username: Optional[str] = None,
             from_date: Optional[str] = None, to_date: Optional[str] = None) -> CursorIterator:
        params = {k: v for k, v in {
            "resource_type": resource_type, "username": username,
            "from_date": from_date, "to_date": to_date,
        }.items() if v is not None}
        return CursorIterator(
            lambda p: self._t.request("GET", "/audit", params=p), AuditEntry, params)
