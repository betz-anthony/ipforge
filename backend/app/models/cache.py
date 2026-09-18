from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime
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
    ttl         = Column(BigInteger, default=3600)  # spec allows up to uint32; overflows a plain Integer
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


class CachedDHCPScopePool(Base):
    """Every pool range configured on a DHCP scope (a Kea subnet can have
    more than one; msdhcp/pihole get exactly one row each), refreshed every
    sync pass.

    Currently write-only from the application's perspective: nothing in
    app/ outside tests reads this table. KeaDHCPProvider.get_scope_exclusions
    derives its exclusion gaps by calling the provider directly
    (get_scope_pools), not by reading these cached rows — providers reading
    back from the app's own DB would be the wrong layering. This table exists
    as staging for a possible future DHCP-page UI surfacing per-pool detail
    (the DHCP page currently only shows a scope's collapsed min/max
    start_range/end_range across all pools).
    """
    __tablename__ = "cache_dhcp_scope_pools"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    scope_id   = Column(String, nullable=False, index=True)
    source     = Column(String, nullable=False, index=True)
    start_ip   = Column(String, nullable=False)
    end_ip     = Column(String, nullable=False)


class CachedDHCPLease(Base):
    __tablename__ = "cache_dhcp_leases"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    scope_id    = Column(String, nullable=False, index=True)
    ip_address  = Column(String, nullable=False)
    mac_address = Column(String, default="")
    client_duid = Column(String, default="")
    iaid        = Column(BigInteger, default=0)  # DHCPv6 IAID is uint32 (RFC 8415)
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
