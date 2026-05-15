import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s", force=True)
from fastapi.middleware.cors import CORSMiddleware
from app.database import SessionLocal
from app.config import settings as app_settings
from app.api import subnets, addresses, dns, dhcp
from app.api import settings as settings_router
from app.api import sync as sync_router
from app.api import tools as tools_router
from app.api import stats as stats_router
from app.api import scan as scan_router
from app.api import search as search_router
from app.api import provider_configs as provider_configs_router
from app.api import auth as auth_router
from app.api import users as users_router
from app.api import audit as audit_router
import app.models  # noqa: F401

logger = logging.getLogger(__name__)


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
        from app.api.settings import apply_db_settings
        apply_db_settings(db)
        _ensure_default_admin(db)
    finally:
        db.close()
    if app_settings.sync_mode == "background":
        from app.sync import sync_all, start_background_sync
        threading.Thread(target=sync_all, daemon=True, name="ipam-initial-sync").start()
        start_background_sync()
    from app.scan import scan_scheduler_loop
    threading.Thread(target=scan_scheduler_loop, daemon=True, name="ipam-scan-scheduler").start()
    yield


app = FastAPI(title="IPAM Forge", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.core.deps import get_current_user, require_admin, require_operator  # noqa: E402

# Public
app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])

# Read-only+ (any authenticated user)
_ro = [Depends(get_current_user)]
app.include_router(subnets.router,       prefix="/api/subnets",    tags=["subnets"],    dependencies=_ro)
app.include_router(addresses.router,     prefix="/api/addresses",  tags=["addresses"],  dependencies=_ro)
app.include_router(dns.router,           prefix="/api/dns",        tags=["dns"],        dependencies=_ro)
app.include_router(dhcp.router,          prefix="/api/dhcp",       tags=["dhcp"],       dependencies=_ro)
app.include_router(search_router.router, prefix="/api/search",     tags=["search"],     dependencies=_ro)
app.include_router(stats_router.router,  prefix="/api/stats",      tags=["stats"],      dependencies=_ro)
app.include_router(tools_router.router,  prefix="/api/tools",      tags=["tools"],      dependencies=_ro)
app.include_router(audit_router.router,  prefix="/api/audit",      tags=["audit"],      dependencies=_ro)

# Operator+
_op = [Depends(require_operator)]
app.include_router(sync_router.router,   prefix="/api/sync",  tags=["sync"],  dependencies=_op)
app.include_router(scan_router.router,   prefix="/api/scan",  tags=["scan"],  dependencies=_op)

# Admin only
_adm = [Depends(require_admin)]
app.include_router(settings_router.router,        prefix="/api/settings",         tags=["settings"],        dependencies=_adm)
app.include_router(provider_configs_router.router, prefix="/api/provider-configs", tags=["provider-configs"], dependencies=_adm)
app.include_router(users_router.router,            prefix="/api/users",            tags=["users"],            dependencies=_adm)


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
