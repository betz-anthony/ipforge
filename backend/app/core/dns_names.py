"""DNSNAME-001 — detect record names that repeat their own zone."""


def short_name_for_zone(name: str, zone: str) -> str | None:
    """Return the zone-relative name if `name` ends in `.<zone>`, else None.

    DNS servers treat a name without a trailing dot as relative to the zone, so
    `host.example.com` added to zone `example.com` becomes
    `host.example.com.example.com`. A name with a trailing dot is absolute, so
    nothing is appended and it is never reported. Comparison ignores case.
    The apex (`@`, or the zone name itself) is not reported.
    """
    n = name.strip()
    if n.endswith("."):
        return None
    z = zone.strip().rstrip(".")
    if not n or not z:
        return None
    suffix = "." + z.lower()
    if n.lower().endswith(suffix) and len(n) > len(suffix):
        return n[: -len(suffix)]
    return None
