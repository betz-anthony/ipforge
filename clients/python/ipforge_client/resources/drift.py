from typing import List, Optional

from ..models import DriftItem


class Drift:
    def __init__(self, transport):
        self._t = transport

    def list(self, category: Optional[str] = None, severity: Optional[str] = None,
             needs_review: Optional[bool] = None) -> List[DriftItem]:
        params = {k: v for k, v in {
            "category": category, "severity": severity, "needs_review": needs_review,
        }.items() if v is not None}
        return [DriftItem(x) for x in self._t.request("GET", "/drift", params=params or None)]
