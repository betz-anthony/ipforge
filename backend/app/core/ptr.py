import ipaddress
from app.providers.dns.base import DNSRecord


def _reverse_labels(ip: str) -> tuple[list[str], str]:
    """Return the reverse-DNS labels (most-significant last) and arpa suffix for an IP."""
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv4Address):
        return list(reversed(str(addr).split('.'))), "in-addr.arpa"
    return list(reversed(addr.exploded.replace(':', ''))), "ip6.arpa"


def find_reverse_zone(ip: str, zones: list[str]) -> str | None:
    """Return the most-specific reverse zone from zones that covers ip, or None."""
    labels, arpa = _reverse_labels(ip)
    zone_set = set(zones)
    for i in range(len(labels)):
        candidate = f"{'.'.join(labels[i:])}.{arpa}"
        if candidate in zone_set:
            return candidate
    return None


def build_ptr_record(
    ip: str,
    hostname: str,
    reverse_zone: str,
    provider: str,
    ttl: int = 3600,
) -> DNSRecord:
    """Construct a PTR DNSRecord for ip within reverse_zone."""
    if not reverse_zone:
        raise ValueError("reverse_zone must not be empty or None")

    labels, arpa = _reverse_labels(ip)
    full_ptr = f"{'.'.join(labels)}.{arpa}"

    suffix = f".{reverse_zone}"
    name = full_ptr[: -len(suffix)] if full_ptr.endswith(suffix) else full_ptr

    return DNSRecord(
        name=name,
        record_type="PTR",
        value=f"{hostname.rstrip('.')}.",
        zone=reverse_zone,
        ttl=ttl,
        source=provider,
    )
