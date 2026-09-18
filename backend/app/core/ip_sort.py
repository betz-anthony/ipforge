import ipaddress


def ip_sort_key(ip: str) -> bytes | None:
    """16-byte big-endian sort key: numeric order via plain byte comparison
    in both Postgres (bytea) and SQLite (BLOB), no per-dialect SQL needed.
    IPv4 is left-padded with zero bytes into the same 16-byte space IPv6
    already occupies, so every v4 address sorts before every v6 address —
    not the RFC 4291 ::ffff:0:0/96 mapped-address form (that would use
    0xffff in bytes 10-11, not zeros); this is purely an ordering
    convenience, not a claim that a v4 and its mapped-v6 spelling are "the
    same" address here. Returns None for anything that doesn't parse as an
    IP — callers should tolerate that rather than crash a write on bad
    data."""
    try:
        packed = ipaddress.ip_address(ip).packed
    except ValueError:
        return None
    return packed.rjust(16, b"\x00")
