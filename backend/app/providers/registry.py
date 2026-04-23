from functools import lru_cache
from app.config import settings
from app.providers.dns.base import DNSProvider
from app.providers.dhcp.base import DHCPProvider


def _make_dns_provider(name: str) -> DNSProvider:
    name = name.strip()
    if name == "msdns":
        from app.providers.dns.msdns import MSDNSProvider
        return MSDNSProvider()
    if name == "pihole":
        from app.providers.dns.pihole import PiholeDNSProvider
        return PiholeDNSProvider()
    if name == "bind":
        from app.providers.dns.bind import BINDDNSProvider
        return BINDDNSProvider()
    raise ValueError(f"Unknown DNS provider: {name}")


def _make_dhcp_provider(name: str) -> DHCPProvider:
    name = name.strip()
    if name == "msdhcp":
        from app.providers.dhcp.msdhcp import MSDHCPProvider
        return MSDHCPProvider()
    if name == "pihole":
        from app.providers.dhcp.pihole import PiholeDHCPProvider
        return PiholeDHCPProvider()
    if name == "keadhcp":
        from app.providers.dhcp.isc import KeaDHCPProvider
        return KeaDHCPProvider()
    raise ValueError(f"Unknown DHCP provider: {name}")


@lru_cache()
def get_dns_providers() -> list[DNSProvider]:
    return [_make_dns_provider(n) for n in settings.dns_provider.split(",") if n.strip()]


@lru_cache()
def get_dhcp_providers() -> list[DHCPProvider]:
    return [_make_dhcp_provider(n) for n in settings.dhcp_provider.split(",") if n.strip()]
