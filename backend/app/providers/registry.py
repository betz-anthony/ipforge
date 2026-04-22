from functools import lru_cache
from app.config import settings
from app.providers.dns.base import DNSProvider
from app.providers.dhcp.base import DHCPProvider


@lru_cache()
def get_dns_provider() -> DNSProvider:
    if settings.dns_provider == "msdns":
        from app.providers.dns.msdns import MSDNSProvider
        return MSDNSProvider()
    raise ValueError(f"Unknown DNS provider: {settings.dns_provider}")


@lru_cache()
def get_dhcp_provider() -> DHCPProvider:
    if settings.dhcp_provider == "msdhcp":
        from app.providers.dhcp.msdhcp import MSDHCPProvider
        return MSDHCPProvider()
    raise ValueError(f"Unknown DHCP provider: {settings.dhcp_provider}")
