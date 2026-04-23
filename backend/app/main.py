from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, SessionLocal
from app.api import subnets, addresses, dns, dhcp
from app.api import settings as settings_router
import app.models  # noqa: F401 — ensures models are registered before create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        from app.api.settings import apply_db_settings
        apply_db_settings(db)
    finally:
        db.close()
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


@app.get("/api/providers", tags=["settings"])
def get_active_providers():
    from app.providers.registry import get_dns_providers, get_dhcp_providers
    return {
        "dns": [p.source for p in get_dns_providers()],
        "dhcp": [p.source for p in get_dhcp_providers()],
    }
