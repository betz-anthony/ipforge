from typing import List, Optional

from ..models import DNSRecord, Model
from ..pagination import Page, PageIterator


class DNS:
    def __init__(self, transport):
        self._t = transport

    def list_zones(self) -> list:
        return self._t.request("GET", "/dns/zones")

    def list_records(self, zone: str, q: Optional[str] = None,
                     sort: Optional[str] = None, dir: Optional[str] = None) -> PageIterator:
        params = {k: v for k, v in {"q": q, "sort": sort, "dir": dir}.items() if v is not None}
        return PageIterator(
            lambda p: self._t.request("GET", f"/dns/zones/{zone}/records", params=p),
            DNSRecord, params)

    def list_records_page(self, zone: str, limit: int = 50, offset: int = 0, **filters) -> Page:
        params = {k: v for k, v in filters.items() if v is not None}
        params.update(limit=limit, offset=offset)
        env = self._t.request("GET", f"/dns/zones/{zone}/records", params=params)
        return Page([DNSRecord(x) for x in env["items"]],
                    env["total"], env["limit"], env["offset"])

    def create_record(self, zone: str, register_ptr: bool = False, **fields) -> DNSRecord:
        body = dict(fields)
        if register_ptr:
            body["register_ptr"] = True
        return DNSRecord(self._t.request("POST", f"/dns/zones/{zone}/records", json=body))

    def delete_record(self, zone: str, record, delete_ptr: bool = False) -> None:
        body = dict(record.raw) if isinstance(record, Model) else dict(record)
        if delete_ptr:
            body["delete_ptr"] = True
        self._t.request("DELETE", f"/dns/zones/{zone}/records", json=body)

    def by_ip(self, ip: str) -> List[DNSRecord]:
        return [DNSRecord(x) for x in self._t.request("GET", f"/dns/by-ip/{ip}")]
