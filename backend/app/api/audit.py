from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog
from app.core.pagination import _encode_cursor, _decode_cursor

router = APIRouter()


class AuditEntryRead(BaseModel):
    id:            int
    timestamp:     datetime
    username:      str
    action:        str
    resource_type: str
    resource_id:   str
    summary:       str | None
    before_state:  str | None
    after_state:   str | None

    model_config = ConfigDict(from_attributes=True)


class CursorAuditRead(BaseModel):
    items:       list[AuditEntryRead]
    next_cursor: str | None
    limit:       int


@router.get("", response_model=CursorAuditRead)
def list_audit(
    resource_type: str | None = Query(None),
    username:      str | None = Query(None),
    from_date:     datetime | None = Query(None),
    to_date:       datetime | None = Query(None),
    limit:         int             = Query(50, ge=1, le=200),
    cursor:        str | None      = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if username:
        q = q.filter(AuditLog.username == username)
    if from_date:
        q = q.filter(AuditLog.timestamp >= from_date)
    if to_date:
        q = q.filter(AuditLog.timestamp <= to_date)

    decoded = _decode_cursor(cursor)
    if decoded is not None:
        cur_ts, cur_id = decoded
        q = q.filter(
            (AuditLog.timestamp < cur_ts) |
            ((AuditLog.timestamp == cur_ts) & (AuditLog.id < cur_id))
        )

    rows = q.limit(limit + 1).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode_cursor(last.timestamp, last.id)
    return CursorAuditRead(items=items, next_cursor=next_cursor, limit=limit)
