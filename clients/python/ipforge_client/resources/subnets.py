from typing import List, Optional

from ..models import Subnet


class Subnets:
    def __init__(self, transport):
        self._t = transport

    def list(self) -> List[Subnet]:
        return [Subnet(x) for x in self._t.request("GET", "/subnets")]

    def get(self, subnet_id: int) -> Subnet:
        return Subnet(self._t.request("GET", f"/subnets/{subnet_id}"))

    def create(self, **fields) -> Subnet:
        return Subnet(self._t.request("POST", "/subnets", json=fields))

    def update(self, subnet_id: int, **fields) -> Subnet:
        return Subnet(self._t.request("PUT", f"/subnets/{subnet_id}", json=fields))

    def delete(self, subnet_id: int) -> None:
        self._t.request("DELETE", f"/subnets/{subnet_id}")

    def map(self, subnet_id: int) -> dict:
        return self._t.request("GET", f"/subnets/{subnet_id}/map")

    def ranges(self, subnet_id: int) -> list:
        return self._t.request("GET", f"/subnets/{subnet_id}/ranges")

    def add_range(self, subnet_id: int, **fields) -> dict:
        return self._t.request("POST", f"/subnets/{subnet_id}/ranges", json=fields)

    def delete_range(self, subnet_id: int, range_id: int) -> None:
        self._t.request("DELETE", f"/subnets/{subnet_id}/ranges/{range_id}")

    def allocate(self, subnet_id: int, hostname: str, mac: Optional[str] = None,
                 register_dns: bool = False, register_dhcp: bool = False,
                 dns_zone: Optional[str] = None) -> dict:
        body = {"hostname": hostname, "register_dns": register_dns,
                "register_dhcp": register_dhcp}
        if mac:
            body["mac_address"] = mac
        if dns_zone:
            body["dns_zone"] = dns_zone
        return self._t.request("POST", f"/subnets/{subnet_id}/allocate", json=body)
