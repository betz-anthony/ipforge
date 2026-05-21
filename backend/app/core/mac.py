import re

_HEX12 = re.compile(r"^[0-9a-f]{12}$")


def normalize_mac(raw: str) -> str:
    """Normalize a MAC address to canonical lowercase colon form (aa:bb:cc:dd:ee:ff).

    Accepts any common vendor format — colon, hyphen, dot (Cisco), space, or no
    delimiter, in any case. Raises ValueError if the input is not 12 hex digits.
    """
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", raw).lower()
    if not _HEX12.match(hex_only):
        raise ValueError(f"invalid MAC address: {raw!r}")
    return ":".join(hex_only[i:i + 2] for i in range(0, 12, 2))
