"""Thread-safe in-memory queue for alert trigger events.

emit() is called from API/scan/sync code paths. The dispatcher thread drains
the queue on each tick and processes events.
"""
import queue
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from app.core.time import utcnow


@dataclass
class TriggerEvent:
    trigger_type: str
    resource_key: str
    context: dict[str, Any] = field(default_factory=dict)
    emitted_at: datetime = field(default_factory=utcnow)


_queue: "queue.Queue[TriggerEvent]" = queue.Queue()


def emit(trigger_type: str, resource_key: str, context: dict | None = None) -> None:
    _queue.put(TriggerEvent(trigger_type=trigger_type, resource_key=resource_key, context=context or {}))


def drain_queue() -> list[TriggerEvent]:
    items = []
    while True:
        try:
            items.append(_queue.get_nowait())
        except queue.Empty:
            break
    return items
