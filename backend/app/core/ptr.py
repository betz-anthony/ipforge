import ipaddress
from app.providers.dns.base import DNSRecord


def find_reverse_zone(ip: str, zones: list[str]) -> str | None:
    """Return the most-specific reverse zone from zones that covers ip, or None."""
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv4Address):
        octets = ip.split('.')
        candidates = [
            f"{'.'.join(reversed(octets[:n]))}.in-addr.arpa"
            for n in range(len(octets), 0, -1)
        ]
    else:
        expanded = addr.exploded.replace(':', '')
        candidates = [
            f"{'.'.join(reversed(list(expanded[:n])))}.ip6.arpa"
            for n in range(len(expanded), 0, -1)
        ]
    zone_set = set(zones)
    for candidate in candidates:
        if candidate in zone_set:
            return candidate
    return None


def build_ptr_record(
    ip: str,
    hostname: str,
    reverse_zone: str,
    provider: str = "",
    ttl: int = 3600,
) -> DNSRecord:
    """Construct a PTR DNSRecord for ip within reverse_zone."""
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv4Address):
        octets = ip.split('.')
        full_ptr = f"{'.'.join(reversed(octets))}.in-addr.arpa"
    else:
        expanded = addr.exploded.replace(':', '')
        full_ptr = f"{'.'.join(reversed(list(expanded)))}.ip6.arpa"

    suffix = f".{reverse_zone}"
    name = full_ptr[: -len(suffix)] if full_ptr.endswith(suffix) else full_ptr

    return DNSRecord(
        name=name,
        record_type="PTR",
        value=f"{hostname}.",
        zone=reverse_zone,
        ttl=ttl,
        source=provider,
    )
