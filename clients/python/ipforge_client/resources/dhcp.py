from typing import List, Optional

from ..models import DHCPLease
from ..pagination import Page, PageIterator


class DHCP:
    def __init__(self, transport):
        self._t = transport

    def list_scopes(self) -> list:
        return self._t.request("GET", "/dhcp/scopes")

    def list_leases(self, scope_id: str, source: Optional[str] = None,
                    q: Optional[str] = None, sort: Optional[str] = None,
                    dir: Optional[str] = None) -> PageIterator:
        params = {k: v for k, v in {
            "source": source, "q": q, "sort": sort, "dir": dir,
        }.items() if v is not None}
        return PageIterator(
            lambda p: self._t.request("GET", f"/dhcp/scopes/{scope_id}/leases", params=p),
            DHCPLease, params)

    def list_leases_page(self, scope_id: str, limit: int = 50, offset: int = 0, **filters) -> Page:
        params = {k: v for k, v in filters.items() if v is not None}
        params.update(limit=limit, offset=offset)
        env = self._t.request("GET", f"/dhcp/scopes/{scope_id}/leases", params=params)
        return Page([DHCPLease(x) for x in env["items"]],
                    env["total"], env["limit"], env["offset"])

    def add_reservation(self, scope_id: str, source: Optional[str] = None, **fields) -> DHCPLease:
        params = {"source": source} if source else None
        return DHCPLease(self._t.request(
            "POST", f"/dhcp/scopes/{scope_id}/reservations", params=params, json=fields))

    def delete_reservation(self, scope_id: str, ip_address: str, source: Optional[str] = None) -> None:
        params = {"source": source} if source else None
        self._t.request(
            "DELETE", f"/dhcp/scopes/{scope_id}/reservations/{ip_address}", params=params)

    def by_ip(self, ip: str) -> List[DHCPLease]:
        return [DHCPLease(x) for x in self._t.request("GET", f"/dhcp/by-ip/{ip}")]
