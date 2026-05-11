import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI

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
import app.models  # noqa: F401


def _run_migrations():
    from alembic.config import Config
    from alembic import command
    import os
    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    db = SessionLocal()
    try:
        from app.api.settings import apply_db_settings
        apply_db_settings(db)
    finally:
        db.close()
    if app_settings.sync_mode == "background":
        from app.sync import sync_all, start_background_sync
        threading.Thread(target=sync_all, daemon=True, name="ipam-initial-sync").start()
        start_background_sync()
    yield


app = FastAPI(title="IPAM", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(subnets.router, prefix="/api/subnets", tags=["subnets"])
app.include_router(addresses.router, prefix="/api/addresses", tags=["addresses"])
app.include_router(dns.router, prefix="/api/dns", tags=["dns"])
app.include_router(dhcp.router, prefix="/api/dhcp", tags=["dhcp"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(sync_router.router, prefix="/api/sync", tags=["sync"])
app.include_router(tools_router.router, prefix="/api/tools", tags=["tools"])
app.include_router(stats_router.router, prefix="/api/stats", tags=["stats"])
app.include_router(scan_router.router, prefix="/api/scan", tags=["scan"])
app.include_router(search_router.router, prefix="/api/search", tags=["search"])


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


@app.get("/api/providers", tags=["settings"])
def get_active_providers():
    from app.providers.registry import get_dns_providers, get_dhcp_providers
    return {
        "dns": [p.source for p in get_dns_providers()],
        "dhcp": [p.source for p in get_dhcp_providers()],
    }
