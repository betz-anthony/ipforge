import threading
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.cache import SyncStatus

router = APIRouter()


def _age(synced_at) -> int | None:
    if synced_at is None:
        return None
    return max(0, int((datetime.now(timezone.utc).replace(tzinfo=None) - synced_at).total_seconds()))


@router.get("/status")
def get_sync_status(db: Session = Depends(get_db)):
    result = {}
    for key in ("dns", "dhcp"):
        row = db.get(SyncStatus, key)
        if row:
            result[key] = {
                "synced_at": row.synced_at.isoformat() + "Z" if row.synced_at else None,
                "age_seconds": _age(row.synced_at),
                "status": row.status,
                "error": row.error,
            }
        else:
            result[key] = {"synced_at": None, "age_seconds": None, "status": "never", "error": None}
    return result


@router.post("/trigger")
def trigger_sync(type: str | None = Query(None)):
    from app.sync import sync_dns, sync_dhcp, sync_all
    fn = {"dns": sync_dns, "dhcp": sync_dhcp}.get(type or "", sync_all)
    threading.Thread(target=fn, daemon=True).start()
    return {"status": "triggered"}
