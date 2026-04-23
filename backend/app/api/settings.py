from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setting import AppSetting
from app.config import settings
from app.providers.registry import get_dns_provider, get_dhcp_provider

router = APIRouter()

SETTING_KEYS = [
    "dns_provider",
    "dhcp_provider",
    "ms_winrm_host",
    "ms_winrm_user",
    "ms_winrm_password",
    "ms_winrm_port",
    "ms_winrm_transport",
    "ms_dns_server",
    "ms_dhcp_server",
]


class SettingsResponse(BaseModel):
    dns_provider: str
    dhcp_provider: str
    ms_winrm_host: str
    ms_winrm_user: str
    ms_winrm_password_set: bool
    ms_winrm_port: int
    ms_winrm_transport: str
    ms_dns_server: str
    ms_dhcp_server: str


class SettingsUpdate(BaseModel):
    dns_provider: str | None = None
    dhcp_provider: str | None = None
    ms_winrm_host: str | None = None
    ms_winrm_user: str | None = None
    ms_winrm_password: str | None = None  # None = no change
    ms_winrm_port: int | None = None
    ms_winrm_transport: str | None = None
    ms_dns_server: str | None = None
    ms_dhcp_server: str | None = None


def apply_db_settings(db: Session) -> None:
    rows = db.query(AppSetting).all()
    for row in rows:
        if hasattr(settings, row.key) and row.value != "":
            val = row.value
            if row.key == "ms_winrm_port":
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
        dns_provider=settings.dns_provider,
        dhcp_provider=settings.dhcp_provider,
        ms_winrm_host=settings.ms_winrm_host,
        ms_winrm_user=settings.ms_winrm_user,
        ms_winrm_password_set=bool(settings.ms_winrm_password),
        ms_winrm_port=settings.ms_winrm_port,
        ms_winrm_transport=settings.ms_winrm_transport,
        ms_dns_server=settings.ms_dns_server,
        ms_dhcp_server=settings.ms_dhcp_server,
    )


@router.put("", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        _upsert(db, key, str(value))
        setattr(settings, key, value)
    db.commit()

    # bust provider singletons so next request picks up new config
    get_dns_provider.cache_clear()
    get_dhcp_provider.cache_clear()

    return get_settings()
