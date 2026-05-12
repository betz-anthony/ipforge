import json
from app.providers.dns.base import DNSProvider
from app.providers.dhcp.base import DHCPProvider

_dns_cache: list[DNSProvider] | None = None
_dhcp_cache: list[DHCPProvider] | None = None


def _make_dns(provider_type: str, cfg: dict, name: str) -> DNSProvider:
    if provider_type == "msdns":
        from app.providers.dns.msdns import MSDNSProvider
        return MSDNSProvider(cfg, name)
    if provider_type == "pihole":
        from app.providers.dns.pihole import PiholeDNSProvider
        return PiholeDNSProvider(cfg, name)
    if provider_type == "bind":
        from app.providers.dns.bind import BINDDNSProvider
        return BINDDNSProvider(cfg, name)
    raise ValueError(f"Unknown DNS provider type: {provider_type}")


def _make_dhcp(provider_type: str, cfg: dict, name: str) -> DHCPProvider:
    if provider_type == "msdhcp":
        from app.providers.dhcp.msdhcp import MSDHCPProvider
        return MSDHCPProvider(cfg, name)
    if provider_type == "pihole":
        from app.providers.dhcp.pihole import PiholeDHCPProvider
        return PiholeDHCPProvider(cfg, name)
    if provider_type == "keadhcp":
        from app.providers.dhcp.isc import KeaDHCPProvider
        return KeaDHCPProvider(cfg, name)
    raise ValueError(f"Unknown DHCP provider type: {provider_type}")


def _load_from_db() -> tuple[list[DNSProvider], list[DHCPProvider]]:
    from app.database import SessionLocal
    from app.models.provider_config import ProviderConfig

    db = SessionLocal()
    try:
        rows = (
            db.query(ProviderConfig)
            .filter(ProviderConfig.enabled == True)  # noqa: E712
            .order_by(ProviderConfig.sort_order, ProviderConfig.id)
            .all()
        )
        dns: list[DNSProvider] = []
        dhcp: list[DHCPProvider] = []
        for row in rows:
            cfg = json.loads(row.config or "{}")
            try:
                if row.category == "dns":
                    dns.append(_make_dns(row.provider_type, cfg, row.name))
                elif row.category == "dhcp":
                    dhcp.append(_make_dhcp(row.provider_type, cfg, row.name))
            except ValueError:
                pass  # skip unknown types gracefully
        return dns, dhcp
    finally:
        db.close()


def get_dns_providers() -> list[DNSProvider]:
    global _dns_cache, _dhcp_cache
    if _dns_cache is None:
        _dns_cache, _dhcp_cache = _load_from_db()
    return _dns_cache


def get_dhcp_providers() -> list[DHCPProvider]:
    global _dns_cache, _dhcp_cache
    if _dhcp_cache is None:
        _dns_cache, _dhcp_cache = _load_from_db()
    return _dhcp_cache


def invalidate_provider_cache() -> None:
    global _dns_cache, _dhcp_cache
    _dns_cache = None
    _dhcp_cache = None
