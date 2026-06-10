from typing import Optional

from ..models import Address
from ..pagination import Page, PageIterator


class Addresses:
    def __init__(self, transport):
        self._t = transport

    def list(self, subnet_id: Optional[int] = None, status: Optional[str] = None,
             tag: Optional[str] = None, q: Optional[str] = None,
             sort: Optional[str] = None, dir: Optional[str] = None) -> PageIterator:
        params = {k: v for k, v in {
            "subnet_id": subnet_id, "status": status, "tag": tag,
            "q": q, "sort": sort, "dir": dir,
        }.items() if v is not None}
        return PageIterator(
            lambda p: self._t.request("GET", "/addresses", params=p), Address, params)

    def list_page(self, limit: int = 50, offset: int = 0, **filters) -> Page:
        params = {k: v for k, v in filters.items() if v is not None}
        params.update(limit=limit, offset=offset)
        env = self._t.request("GET", "/addresses", params=params)
        return Page([Address(x) for x in env["items"]],
                    env["total"], env["limit"], env["offset"])

    def get(self, address_id: int) -> Address:
        return Address(self._t.request("GET", f"/addresses/{address_id}"))

    def create(self, **fields) -> Address:
        return Address(self._t.request("POST", "/addresses", json=fields))

    def update(self, address_id: int, **fields) -> Address:
        return Address(self._t.request("PUT", f"/addresses/{address_id}", json=fields))

    def delete(self, address_id: int) -> None:
        self._t.request("DELETE", f"/addresses/{address_id}")

    def by_ip(self, ip: str) -> Address:
        return Address(self._t.request("GET", f"/addresses/by-ip/{ip}"))

    def history(self, address_id: int) -> dict:
        return self._t.request("GET", f"/addresses/{address_id}/history")

    def history_by_ip(self, ip: str, as_of: Optional[str] = None) -> dict:
        params = {"as_of": as_of} if as_of else None
        return self._t.request("GET", f"/addresses/by-ip/{ip}/history", params=params)
