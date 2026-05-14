from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog

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


@router.get("", response_model=list[AuditEntryRead])
def list_audit(
    resource_type: str | None = Query(None),
    username:      str | None = Query(None),
    from_date:     str | None = Query(None),
    to_date:       str | None = Query(None),
    limit:         int        = Query(100, le=500),
    offset:        int        = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if username:
        q = q.filter(AuditLog.username == username)
    if from_date:
        q = q.filter(AuditLog.timestamp >= datetime.fromisoformat(from_date))
    if to_date:
        q = q.filter(AuditLog.timestamp <= datetime.fromisoformat(to_date))
    return q.offset(offset).limit(limit).all()
