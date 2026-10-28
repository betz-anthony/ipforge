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


def _ptr_target(hostname: str, forward_zone: str | None) -> str:
    name = hostname.strip()
    zone = (forward_zone or "").strip().rstrip(".")
    if zone and not name.endswith("."):
        if name == "@":
            name = zone
        elif name.lower() != zone.lower() and not name.lower().endswith("." + zone.lower()):
            name = f"{name}.{zone}"
    return f"{name.rstrip('.')}."


def build_ptr_record(
    ip: str,
    hostname: str,
    reverse_zone: str,
    provider: str,
    ttl: int = 3600,
    forward_zone: str | None = None,
) -> DNSRecord:
    """Construct a PTR DNSRecord for ip within reverse_zone.

    Forward records are often zone-relative (``web01`` in ``example.com``),
    but a PTR target must be the full name. When ``forward_zone`` is given, a
    relative hostname is qualified with it; a name already inside the zone, or
    absolute (trailing dot), is left as is.
    """
    if not reverse_zone:
        raise ValueError("reverse_zone must not be empty or None")

    labels, arpa = _reverse_labels(ip)
    full_ptr = f"{'.'.join(labels)}.{arpa}"

    suffix = f".{reverse_zone}"
    name = full_ptr[: -len(suffix)] if full_ptr.endswith(suffix) else full_ptr

    return DNSRecord(
        name=name,
        record_type="PTR",
        value=_ptr_target(hostname, forward_zone),
        zone=reverse_zone,
        ttl=ttl,
        source=provider,
    )
