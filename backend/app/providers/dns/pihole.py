import requests
from urllib.parse import quote
from app.config import settings
from app.providers.dns.base import DNSProvider, DNSRecord

# Pi-hole v6 FTL REST API provider.
# Custom DNS stored in config: dns.hosts (A/AAAA) and dns.cnameRecords (CNAME).
# Auth: POST /api/auth → session.sid → X-FTL-SID header.


class PiholeDNSProvider(DNSProvider):
    source = "pihole"
    ZONE = "pihole-local"

    def __init__(self):
        self._sid: str | None = None

    @property
    def _base(self) -> str:
        return settings.pihole_url.rstrip("/")

    def _authenticate(self) -> str:
        r = requests.post(
            f"{self._base}/api/auth",
            json={"password": settings.pihole_password},
            verify=False, timeout=10,
        )
        r.raise_for_status()
        return r.json()["session"]["sid"]

    def _headers(self) -> dict:
        if not self._sid:
            self._sid = self._authenticate()
        return {"X-FTL-SID": self._sid}

    def _req(self, method: str, path: str, **kwargs):
        url = f"{self._base}/api{path}"
        r = requests.request(method, url, headers=self._headers(), verify=False, timeout=10, **kwargs)
        if r.status_code == 401:
            self._sid = None
            r = requests.request(method, url, headers=self._headers(), verify=False, timeout=10, **kwargs)
        r.raise_for_status()
        return r

    def _dns_config(self) -> dict:
        data = self._req("GET", "/config/dns").json()
        return data.get("config", {}).get("dns", {})

    def get_zones(self) -> list[str]:
        return [self.ZONE]

    def get_records(self, zone: str) -> list[DNSRecord]:
        records: list[DNSRecord] = []
        cfg = self._dns_config()

        # dns.hosts: ["192.168.1.10 hostname", ...]
        for entry in cfg.get("hosts", []):
            parts = entry.split(None, 1)
            if len(parts) == 2:
                ip, name = parts
                records.append(DNSRecord(
                    name=name,
                    record_type="AAAA" if ":" in ip else "A",
                    value=ip, zone=zone, ttl=0,
                ))

        # dns.cnameRecords: ["alias,target" or "alias,target,ttl", ...]
        for entry in cfg.get("cnameRecords", []):
            parts = entry.split(",")
            if len(parts) >= 2:
                ttl = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
                records.append(DNSRecord(
                    name=parts[0], record_type="CNAME", value=parts[1],
                    zone=zone, ttl=ttl,
                ))

        return records

    def add_record(self, record: DNSRecord) -> None:
        if record.record_type in ("A", "AAAA"):
            entry = quote(f"{record.value} {record.name}", safe="")
            self._req("PUT", f"/config/dns/hosts/{entry}")
        elif record.record_type == "CNAME":
            entry = quote(f"{record.name},{record.value}", safe="")
            self._req("PUT", f"/config/dns/cnameRecords/{entry}")
        else:
            raise NotImplementedError(f"Pi-hole does not support {record.record_type} records via API")

    def delete_record(self, record: DNSRecord) -> None:
        if record.record_type in ("A", "AAAA"):
            entry = quote(f"{record.value} {record.name}", safe="")
            self._req("DELETE", f"/config/dns/hosts/{entry}")
        elif record.record_type == "CNAME":
            entry = quote(f"{record.name},{record.value}", safe="")
            self._req("DELETE", f"/config/dns/cnameRecords/{entry}")
        else:
            raise NotImplementedError(f"Pi-hole does not support {record.record_type} records via API")

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
