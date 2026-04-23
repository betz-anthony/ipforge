from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.setting import AppSetting
from app.config import settings
from app.providers.registry import get_dns_provider, get_dhcp_provider

router = APIRouter()

INT_KEYS = {"ms_winrm_port", "bind_port"}

SETTING_KEYS = [
    "dns_provider", "dhcp_provider",
    # MS
    "ms_winrm_host", "ms_winrm_user", "ms_winrm_password",
    "ms_winrm_port", "ms_winrm_transport", "ms_dns_server", "ms_dhcp_server",
    # Pi-hole
    "pihole_url", "pihole_password",
    # BIND
    "bind_host", "bind_port", "bind_tsig_key_name",
    "bind_tsig_key_secret", "bind_tsig_algorithm", "bind_zones",
    # Kea
    "kea_url", "kea_secret",
]


class SettingsResponse(BaseModel):
    dns_provider: str
    dhcp_provider: str
    # MS
    ms_winrm_host: str
    ms_winrm_user: str
    ms_winrm_password_set: bool
    ms_winrm_port: int
    ms_winrm_transport: str
    ms_dns_server: str
    ms_dhcp_server: str
    # Pi-hole
    pihole_url: str
    pihole_password_set: bool
    # BIND
    bind_host: str
    bind_port: int
    bind_tsig_key_name: str
    bind_tsig_key_secret_set: bool
    bind_tsig_algorithm: str
    bind_zones: str
    # Kea
    kea_url: str
    kea_secret_set: bool


class SettingsUpdate(BaseModel):
    dns_provider: str | None = None
    dhcp_provider: str | None = None
    # MS
    ms_winrm_host: str | None = None
    ms_winrm_user: str | None = None
    ms_winrm_password: str | None = None
    ms_winrm_port: int | None = None
    ms_winrm_transport: str | None = None
    ms_dns_server: str | None = None
    ms_dhcp_server: str | None = None
    # Pi-hole
    pihole_url: str | None = None
    pihole_password: str | None = None
    # BIND
    bind_host: str | None = None
    bind_port: int | None = None
    bind_tsig_key_name: str | None = None
    bind_tsig_key_secret: str | None = None
    bind_tsig_algorithm: str | None = None
    bind_zones: str | None = None
    # Kea
    kea_url: str | None = None
    kea_secret: str | None = None


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
        dns_provider=settings.dns_provider,
        dhcp_provider=settings.dhcp_provider,
        ms_winrm_host=settings.ms_winrm_host,
        ms_winrm_user=settings.ms_winrm_user,
        ms_winrm_password_set=bool(settings.ms_winrm_password),
        ms_winrm_port=settings.ms_winrm_port,
        ms_winrm_transport=settings.ms_winrm_transport,
        ms_dns_server=settings.ms_dns_server,
        ms_dhcp_server=settings.ms_dhcp_server,
        pihole_url=settings.pihole_url,
        pihole_password_set=bool(settings.pihole_password),
        bind_host=settings.bind_host,
        bind_port=settings.bind_port,
        bind_tsig_key_name=settings.bind_tsig_key_name,
        bind_tsig_key_secret_set=bool(settings.bind_tsig_key_secret),
        bind_tsig_algorithm=settings.bind_tsig_algorithm,
        bind_zones=settings.bind_zones,
        kea_url=settings.kea_url,
        kea_secret_set=bool(settings.kea_secret),
    )


@router.put("", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        _upsert(db, key, str(value))
        setattr(settings, key, value)
    db.commit()
    get_dns_provider.cache_clear()
    get_dhcp_provider.cache_clear()
    return get_settings()
