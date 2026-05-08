import ipaddress as _ipaddress


def ip_in_cidr(ip: str, cidr: str) -> bool:
    try:
        return _ipaddress.ip_address(ip) in _ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
