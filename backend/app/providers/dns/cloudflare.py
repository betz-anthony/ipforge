"""Cloudflare DNS provider (CLOUD-DNS-001).

Cloudflare API v4. Auth: bearer API token. Only `_req` touches the network, so
record mapping is unit-testable with mocks.
"""
import requests

from app.providers.dns.base import DNSProvider, DNSRecord

_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareDNSProvider(DNSProvider):
    supports_ptr = True

    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._token = cfg.get("api_token", "")
        self._zone_ids: dict[str, str] = {}

    def _req(self, method: str, path: str, **kwargs) -> dict:
        r = requests.request(
            method, f"{_BASE}{path}",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            timeout=15, **kwargs,
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    def _zone_id(self, zone: str) -> str:
        if not self._zone_ids:
            for z in self._req("GET", "/zones").get("result", []):
                self._zone_ids[z["name"]] = z["id"]
        zid = self._zone_ids.get(zone)
        if zid is None:
            raise RuntimeError(f"Cloudflare zone {zone!r} not found")
        return zid

    def get_zones(self) -> list[str]:
        return [z["name"] for z in self._req("GET", "/zones").get("result", [])]

    def get_records(self, zone: str) -> list[DNSRecord]:
        zid = self._zone_id(zone)
        out: list[DNSRecord] = []
        for r in self._req("GET", f"/zones/{zid}/dns_records").get("result", []):
            out.append(DNSRecord(
                name=r["name"], record_type=r["type"], value=r["content"],
                zone=zone, ttl=r.get("ttl", 1), source=self.source,
            ))
        return out

    def _find_id(self, zid: str, record: DNSRecord) -> str | None:
        for r in self._req("GET", f"/zones/{zid}/dns_records").get("result", []):
            if (r["type"] == record.record_type and r["name"] == record.name
                    and r["content"] == record.value):
                return r["id"]
        return None

    def add_record(self, record: DNSRecord) -> None:
        zid = self._zone_id(record.zone)
        self._req("POST", f"/zones/{zid}/dns_records", json={
            "type": record.record_type, "name": record.name,
            "content": record.value, "ttl": record.ttl,
        })

    def delete_record(self, record: DNSRecord) -> None:
        zid = self._zone_id(record.zone)
        rid = self._find_id(zid, record)
        if rid:
            self._req("DELETE", f"/zones/{zid}/dns_records/{rid}")

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        zid = self._zone_id(old.zone)
        rid = self._find_id(zid, old)
        if rid is None:
            raise RuntimeError(f"Cloudflare record {old.name} {old.record_type} not found")
        self._req("PUT", f"/zones/{zid}/dns_records/{rid}", json={
            "type": new.record_type, "name": new.name,
            "content": new.value, "ttl": new.ttl,
        })
