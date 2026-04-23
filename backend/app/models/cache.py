from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base


class CachedDNSZone(Base):
    __tablename__ = "cache_dns_zones"
    zone      = Column(String, primary_key=True)
    source    = Column(String, primary_key=True)
    synced_at = Column(DateTime, nullable=False)


class CachedDNSRecord(Base):
    __tablename__ = "cache_dns_records"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String, nullable=False)
    record_type = Column(String, nullable=False)
    value       = Column(String, nullable=False)
    zone        = Column(String, nullable=False, index=True)
    ttl         = Column(Integer, default=3600)
    source      = Column(String, nullable=False, index=True)
    synced_at   = Column(DateTime, nullable=False)


class CachedDHCPScope(Base):
    __tablename__ = "cache_dhcp_scopes"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    scope_id    = Column(String, nullable=False)
    name        = Column(String, default="")
    subnet_mask = Column(String, default="")
    start_range = Column(String, default="")
    end_range   = Column(String, default="")
    description = Column(String, default="")
    active      = Column(Boolean, default=True)
    ip_version  = Column(Integer, default=4)
    source      = Column(String, nullable=False, index=True)
    synced_at   = Column(DateTime, nullable=False)


class CachedDHCPLease(Base):
    __tablename__ = "cache_dhcp_leases"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    scope_id    = Column(String, nullable=False, index=True)
    ip_address  = Column(String, nullable=False)
    mac_address = Column(String, default="")
    client_duid = Column(String, default="")
    iaid        = Column(Integer, default=0)
    name        = Column(String, default="")
    description = Column(String, default="")
    source      = Column(String, nullable=False)
    synced_at   = Column(DateTime, nullable=False)


class SyncStatus(Base):
    __tablename__ = "sync_status"
    key       = Column(String, primary_key=True)
    synced_at = Column(DateTime, nullable=True)
    status    = Column(String, default="never")
    error     = Column(String, nullable=True)
