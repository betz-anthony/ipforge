from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setting import AppSetting
from app.config import settings

router = APIRouter()

INT_KEYS = {
    "util_warn_threshold", "util_critical_threshold", "util_dashboard_top_n",
    "scan_interval_minutes", "stale_reclaim_days",
}

SETTING_KEYS = [
    "util_warn_threshold", "util_critical_threshold", "util_dashboard_top_n",
    "scan_interval_minutes", "stale_reclaim_days",
]


class SettingsResponse(BaseModel):
    util_warn_threshold:     int
    util_critical_threshold: int
    util_dashboard_top_n:    int
    scan_interval_minutes:   int
    stale_reclaim_days:      int


class SettingsUpdate(BaseModel):
    util_warn_threshold:     int | None = None
    util_critical_threshold: int | None = None
    util_dashboard_top_n:    int | None = None
    scan_interval_minutes:   int | None = Field(default=None, ge=1)
    stale_reclaim_days:      int | None = Field(default=None, ge=0)


LDAP_BOOL_KEYS = {"ldap_enabled", "ldap_use_ssl"}
LDAP_INT_KEYS  = {"ldap_port"}
LDAP_SECRET_KEYS = {"ldap_bind_password"}


def apply_db_settings(db: Session) -> None:
    from app.core.crypto import decrypt_secret
    rows = db.query(AppSetting).all()
    for row in rows:
        if not hasattr(settings, row.key) or row.value == "":
            continue
        key = row.key
        val: object = row.value
        if key in INT_KEYS | LDAP_INT_KEYS:
            val = int(val)
        elif key in LDAP_BOOL_KEYS:
            val = val == "true"
        elif key in LDAP_SECRET_KEYS:
            val = decrypt_secret(val)
        setattr(settings, key, val)


def _upsert(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


class LdapSettingsResponse(BaseModel):
    ldap_enabled:        bool
    ldap_host:           str
    ldap_port:           int
    ldap_use_ssl:        bool
    ldap_bind_dn:        str
    ldap_bind_password:  str = ""
    ldap_base_dn:        str
    ldap_user_filter:    str
    ldap_group_admin:    str
    ldap_group_operator: str
    ldap_group_readonly: str
    ldap_default_role:   str


class LdapSettingsUpdate(BaseModel):
    ldap_enabled:        bool | None = None
    ldap_host:           str | None = None
    ldap_port:           int | None = Field(default=None, ge=1, le=65535)
    ldap_use_ssl:        bool | None = None
    ldap_bind_dn:        str | None = None
    ldap_bind_password:  str | None = None
    ldap_base_dn:        str | None = None
    ldap_user_filter:    str | None = None
    ldap_group_admin:    str | None = None
    ldap_group_operator: str | None = None
    ldap_group_readonly: str | None = None
    ldap_default_role:   str | None = None


@router.get("/ldap", response_model=LdapSettingsResponse)
def get_ldap_settings():
    return LdapSettingsResponse(
        ldap_enabled=settings.ldap_enabled,
        ldap_host=settings.ldap_host,
        ldap_port=settings.ldap_port,
        ldap_use_ssl=settings.ldap_use_ssl,
        ldap_bind_dn=settings.ldap_bind_dn,
        ldap_bind_password="",
        ldap_base_dn=settings.ldap_base_dn,
        ldap_user_filter=settings.ldap_user_filter,
        ldap_group_admin=settings.ldap_group_admin,
        ldap_group_operator=settings.ldap_group_operator,
        ldap_group_readonly=settings.ldap_group_readonly,
        ldap_default_role=settings.ldap_default_role,
    )


@router.put("/ldap", response_model=LdapSettingsResponse)
def update_ldap_settings(body: LdapSettingsUpdate, db: Session = Depends(get_db)):
    from app.core.crypto import encrypt_secret
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        if key in LDAP_SECRET_KEYS and value:
            db_value = encrypt_secret(value)
        elif key in LDAP_BOOL_KEYS:
            db_value = "true" if value else "false"
        else:
            db_value = str(value)
        _upsert(db, key, db_value)
        if key not in LDAP_SECRET_KEYS:
            setattr(settings, key, value)
        elif value:
            setattr(settings, key, value)
    db.commit()
    return get_ldap_settings()


@router.get("", response_model=SettingsResponse)
def get_settings():
    return SettingsResponse(
        util_warn_threshold=settings.util_warn_threshold,
        util_critical_threshold=settings.util_critical_threshold,
        util_dashboard_top_n=settings.util_dashboard_top_n,
        scan_interval_minutes=settings.scan_interval_minutes,
        stale_reclaim_days=settings.stale_reclaim_days,
    )


@router.put("", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        _upsert(db, key, str(value))
        setattr(settings, key, value)
    db.commit()
    return get_settings()
