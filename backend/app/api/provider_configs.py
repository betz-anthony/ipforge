import json
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.provider_config import ProviderConfig, SECRET_FIELDS
from app.providers.registry import invalidate_provider_cache
from app.core.crypto import encrypt_secret
from app.api.cache import purge_cache

router = APIRouter()

_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}$')

DNS_TYPES  = {"msdns", "pihole", "bind"}
DHCP_TYPES = {"msdhcp", "pihole", "keadhcp"}


def _encrypt_secrets(provider_type: str, cfg: dict) -> dict:
    secrets = SECRET_FIELDS.get(provider_type, [])
    return {k: (encrypt_secret(v) if k in secrets and v else v) for k, v in cfg.items()}


def _mask_config(provider_type: str, cfg: dict) -> tuple[dict, dict[str, bool]]:
    secrets = SECRET_FIELDS.get(provider_type, [])
    masked = {k: ("" if k in secrets else v) for k, v in cfg.items()}
    secrets_set = {k: bool(cfg.get(k)) for k in secrets}
    return masked, secrets_set


def _row_to_dict(row: ProviderConfig) -> dict:
    cfg = json.loads(row.config or "{}")
    masked, secrets_set = _mask_config(row.provider_type, cfg)
    return {
        "id":            row.id,
        "category":      row.category,
        "provider_type": row.provider_type,
        "name":          row.name,
        "config":        masked,
        "secrets_set":   secrets_set,
        "enabled":       row.enabled,
        "sort_order":    row.sort_order,
    }


class ProviderConfigCreate(BaseModel):
    category:      str
    provider_type: str
    name:          str
    config:        dict = {}
    enabled:       bool = True
    sort_order:    int  = 0


class ProviderConfigUpdate(BaseModel):
    name:       str | None = None
    config:     dict | None = None
    enabled:    bool | None = None
    sort_order: int | None = None


@router.get("")
def list_provider_configs(db: Session = Depends(get_db)):
    rows = db.query(ProviderConfig).order_by(ProviderConfig.category, ProviderConfig.sort_order, ProviderConfig.id).all()
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
def create_provider_config(body: ProviderConfigCreate, db: Session = Depends(get_db)):
    if not _SLUG_RE.match(body.name):
        raise HTTPException(400, "name must be lowercase alphanumeric, hyphens, underscores; start with letter/digit")
    if body.category == "dns" and body.provider_type not in DNS_TYPES:
        raise HTTPException(400, f"Unknown DNS provider type: {body.provider_type}")
    if body.category == "dhcp" and body.provider_type not in DHCP_TYPES:
        raise HTTPException(400, f"Unknown DHCP provider type: {body.provider_type}")
    if db.query(ProviderConfig).filter(ProviderConfig.name == body.name).first():
        raise HTTPException(409, f"Provider name {body.name!r} already in use")

    row = ProviderConfig(
        category=body.category,
        provider_type=body.provider_type,
        name=body.name,
        config=json.dumps(_encrypt_secrets(body.provider_type, body.config)),
        enabled=body.enabled,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_provider_cache()
    return _row_to_dict(row)


@router.put("/{config_id}")
def update_provider_config(config_id: int, body: ProviderConfigUpdate, db: Session = Depends(get_db)):
    row = db.get(ProviderConfig, config_id)
    if not row:
        raise HTTPException(404, "Provider config not found")

    if body.name is not None:
        if not _SLUG_RE.match(body.name):
            raise HTTPException(400, "name must be lowercase alphanumeric, hyphens, underscores; start with letter/digit")
        existing = db.query(ProviderConfig).filter(ProviderConfig.name == body.name, ProviderConfig.id != config_id).first()
        if existing:
            raise HTTPException(409, f"Provider name {body.name!r} already in use")
        row.name = body.name

    if body.config is not None:
        # Merge: keep existing secrets if incoming value is empty string
        existing_cfg = json.loads(row.config or "{}")
        secrets = SECRET_FIELDS.get(row.provider_type, [])
        merged = dict(existing_cfg)
        for k, v in body.config.items():
            if k in secrets and v == "":
                pass  # blank = keep existing encrypted value
            else:
                merged[k] = v
        row.config = json.dumps(_encrypt_secrets(row.provider_type, merged))

    if body.enabled is not None:
        row.enabled = body.enabled
    if body.sort_order is not None:
        row.sort_order = body.sort_order

    db.commit()
    db.refresh(row)
    invalidate_provider_cache()
    return _row_to_dict(row)


@router.delete("/{config_id}", status_code=204)
def delete_provider_config(config_id: int, db: Session = Depends(get_db)):
    row = db.get(ProviderConfig, config_id)
    if not row:
        raise HTTPException(404, "Provider config not found")
    source   = row.name
    category = row.category
    db.delete(row)
    purge_cache(db, category, source)
    db.commit()
    invalidate_provider_cache()
