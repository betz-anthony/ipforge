from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.api import subnets, addresses, dns, dhcp
import app.models  # noqa: F401 — ensures models are registered before create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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
