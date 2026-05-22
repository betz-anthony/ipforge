import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s", force=True)
from fastapi.middleware.cors import CORSMiddleware
from app.database import SessionLocal
from app.config import settings as app_settings, DEFAULT_JWT_SECRET_KEY
from app.api import subnets, addresses, dns, dhcp
from app.api import settings as settings_router
from app.api import sync as sync_router
from app.api import tools as tools_router
from app.api import stats as stats_router
from app.api import scan as scan_router
from app.api import search as search_router
from app.api import provider_configs as provider_configs_router
from app.api import auth as auth_router
from app.api import metrics as metrics_router
from app.api import users as users_router
from app.api import audit as audit_router
from app.api import cache as cache_router
from app.api import importexport as importexport_router
from app.api import allocation as allocation_router
from app.api import reclaim as reclaim_router
from app.api import groups as groups_router
import app.models  # noqa: F401

logger = logging.getLogger(__name__)


def _ensure_jwt_secret(db) -> None:
    """Resolve the JWT signing key. An explicit JWT_SECRET_KEY env var always
    wins; otherwise a strong key is generated once and persisted so issued
    tokens stay valid across restarts. This avoids ever signing with the
    predictable built-in default."""
    key = app_settings.jwt_secret_key
    if key and key != DEFAULT_JWT_SECRET_KEY:
        return  # operator-provided key

    from app.models.setting import AppSetting
    row = db.get(AppSetting, "jwt_secret_key")
    if row and row.value:
        app_settings.jwt_secret_key = row.value
        return

    import secrets
    generated = secrets.token_urlsafe(48)
    if row is None:
        db.add(AppSetting(key="jwt_secret_key", value=generated))
    else:
        row.value = generated
    db.commit()
    app_settings.jwt_secret_key = generated
    logger.warning(
        "JWT_SECRET_KEY not set — generated and persisted one. Set it explicitly "
        "if you run multiple API instances so they share a signing key."
    )


def _run_migrations():
    from alembic.config import Config
    from alembic import command
    import os
    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


def _ensure_default_admin(db):
    from app.models.user import User
    from app.core.security import hash_password
    if db.query(User).count() == 0:
        pw = app_settings.default_admin_password
        db.add(User(
            username="admin",
            hashed_password=hash_password(pw),
            role="admin",
            enabled=True,
        ))
        db.commit()
        if pw == "admin":
            logger.warning("Default admin/admin account created — change the password immediately!")
        else:
            logger.info("Default admin account created.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    db = SessionLocal()
    try:
        _ensure_jwt_secret(db)
        from app.api.settings import apply_db_settings
        apply_db_settings(db)
        _ensure_default_admin(db)
        from app.core.crypto import encrypt_existing_secrets
        try:
            encrypted = encrypt_existing_secrets(db)
            if encrypted:
                logger.info("Encrypted %d previously-plaintext secret value(s) at rest", encrypted)
        except Exception:
            logger.exception("encrypt_existing_secrets failed — continuing startup")
    finally:
        db.close()
    if app_settings.sync_mode == "background":
        from app.sync import sync_all, start_background_sync
        threading.Thread(target=sync_all, daemon=True, name="ipam-initial-sync").start()
        start_background_sync()
    # Scan scheduler runs regardless of sync_mode: DNS/DHCP sync has a K8s CronJob equivalent,
    # but scanning has no CronJob — the scheduler is always needed.
    from app.scan import scan_scheduler_loop
    threading.Thread(target=scan_scheduler_loop, daemon=True, name="ipam-scan-scheduler").start()
    yield


app = FastAPI(title="IPForge", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.core.deps import get_current_user, require_admin, require_operator, require_global_read  # noqa: E402

# Public
app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(metrics_router.router, tags=["ops"])

# Read-only+ (any authenticated user, including scoped)
_ro = [Depends(get_current_user)]
# Global-read (admin/operator/readonly only — scoped users are 403'd)
_gr = [Depends(require_global_read)]
# ro_router must be registered before addresses.router to avoid /{id} capture on /stale
app.include_router(reclaim_router.ro_router, prefix="/api/addresses", tags=["reclaim"], dependencies=_gr)
app.include_router(subnets.router,       prefix="/api/subnets",    tags=["subnets"],    dependencies=_ro)
app.include_router(addresses.router,     prefix="/api/addresses",  tags=["addresses"],  dependencies=_ro)
app.include_router(dns.router,           prefix="/api/dns",        tags=["dns"],        dependencies=_gr)
app.include_router(dhcp.router,          prefix="/api/dhcp",       tags=["dhcp"],       dependencies=_gr)
app.include_router(search_router.router, prefix="/api/search",     tags=["search"],     dependencies=_gr)
app.include_router(stats_router.router,  prefix="/api/stats",      tags=["stats"],      dependencies=_gr)
app.include_router(tools_router.router,  prefix="/api/tools",      tags=["tools"],      dependencies=_gr)
app.include_router(audit_router.router,  prefix="/api/audit",      tags=["audit"],      dependencies=_gr)
app.include_router(importexport_router.router, prefix="/api/importexport", tags=["importexport"], dependencies=_gr)

# Operator+
_op = [Depends(require_operator)]
app.include_router(sync_router.router,   prefix="/api/sync",  tags=["sync"],  dependencies=_op)
app.include_router(scan_router.router,   prefix="/api/scan",  tags=["scan"],  dependencies=_op)
app.include_router(reclaim_router.router, prefix="/api/addresses", tags=["reclaim"], dependencies=_op)

# Allocation: scoped users can reach it (later task adds per-subnet check)
app.include_router(allocation_router.router, prefix="/api/subnets", tags=["allocation"], dependencies=_ro)

# Admin only
_adm = [Depends(require_admin)]
app.include_router(settings_router.router,        prefix="/api/settings",         tags=["settings"],        dependencies=_adm)
app.include_router(provider_configs_router.router, prefix="/api/provider-configs", tags=["provider-configs"], dependencies=_adm)
app.include_router(cache_router.router,            prefix="/api/cache",            tags=["cache"],            dependencies=_adm)
app.include_router(users_router.router,            prefix="/api/users",            tags=["users"],            dependencies=_adm)
app.include_router(groups_router.router,           prefix="/api/groups",           tags=["groups"],           dependencies=_adm)


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


@app.get("/api/providers", tags=["settings"], dependencies=[Depends(get_current_user)])
def get_active_providers():
    from app.providers.registry import get_dns_providers, get_dhcp_providers
    return {
        "dns": [p.source for p in get_dns_providers()],
        "dhcp": [p.source for p in get_dhcp_providers()],
    }
