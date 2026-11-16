"""Display names for common DHCPv4 option codes, so every provider's options
read the same regardless of how it spells them."""

OPTION_NAMES: dict[int, str] = {
    1: "Subnet Mask", 2: "Time Offset", 3: "Router", 4: "Time Servers",
    6: "DNS Servers", 7: "Log Servers", 12: "Host Name", 15: "DNS Domain Name",
    26: "Interface MTU", 28: "Broadcast Address", 42: "NTP Servers",
    43: "Vendor Specific Info", 44: "NetBIOS Name Servers", 46: "NetBIOS Node Type",
    51: "Lease Time", 58: "Renewal Time (T1)", 59: "Rebinding Time (T2)",
    60: "Vendor Class ID", 66: "TFTP Server Name", 67: "Boot File Name",
    119: "DNS Search List", 121: "Classless Static Routes", 150: "TFTP Server Address",
}


def option_name(code: int, fallback: str = "") -> str:
    return OPTION_NAMES.get(code) or fallback or f"Option {code}"
