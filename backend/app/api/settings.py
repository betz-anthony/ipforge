from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setting import AppSetting
from app.config import settings

router = APIRouter()

INT_KEYS = {
    "util_warn_threshold", "util_critical_threshold", "util_dashboard_top_n",
    "scan_interval_minutes",
}

SETTING_KEYS = [
    "util_warn_threshold", "util_critical_threshold", "util_dashboard_top_n",
    "scan_interval_minutes",
]


class SettingsResponse(BaseModel):
    util_warn_threshold:     int
    util_critical_threshold: int
    util_dashboard_top_n:    int
    scan_interval_minutes:   int


class SettingsUpdate(BaseModel):
    util_warn_threshold:     int | None = None
    util_critical_threshold: int | None = None
    util_dashboard_top_n:    int | None = None
    scan_interval_minutes:   int | None = Field(default=None, ge=1)


def apply_db_settings(db: Session) -> None:
    rows = db.query(AppSetting).all()
    for row in rows:
        if hasattr(settings, row.key) and row.value != "":
            val: str | int = row.value
            if row.key in INT_KEYS:
                val = int(val)
            setattr(settings, row.key, val)


def _upsert(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


@router.get("", response_model=SettingsResponse)
def get_settings():
    return SettingsResponse(
        util_warn_threshold=settings.util_warn_threshold,
        util_critical_threshold=settings.util_critical_threshold,
        util_dashboard_top_n=settings.util_dashboard_top_n,
        scan_interval_minutes=settings.scan_interval_minutes,
    )


@router.put("", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        _upsert(db, key, str(value))
        setattr(settings, key, value)
    db.commit()
    return get_settings()
