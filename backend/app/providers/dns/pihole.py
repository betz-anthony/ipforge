import requests
from app.config import settings
from app.providers.dns.base import DNSProvider, DNSRecord

# Pi-hole v6 FTL REST API provider.
# Zones: returns single pseudo-zone "pihole-local" containing all custom records.


class PiholeDNSProvider(DNSProvider):
    source = "pihole"
    ZONE = "pihole-local"

    def __init__(self):
        self._sid: str | None = None

    def _authenticate(self) -> str:
        r = requests.post(
            f"{settings.pihole_url}/api/auth",
            json={"password": settings.pihole_password},
            verify=False,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["session"]["sid"]

    def _headers(self) -> dict:
        if not self._sid:
            self._sid = self._authenticate()
        return {"X-FTL-SID": self._sid}

    def _req(self, method: str, path: str, **kwargs):
        r = requests.request(
            method,
            f"{settings.pihole_url}/api{path}",
            headers=self._headers(),
            verify=False,
            timeout=10,
            **kwargs,
        )
        if r.status_code == 401:
            self._sid = None
            r = requests.request(
                method,
                f"{settings.pihole_url}/api{path}",
                headers=self._headers(),
                verify=False,
                timeout=10,
                **kwargs,
            )
        r.raise_for_status()
        return r

    def get_zones(self) -> list[str]:
        return [self.ZONE]

    def get_records(self, zone: str) -> list[DNSRecord]:
        records: list[DNSRecord] = []

        for rec in self._req("GET", "/dns/records").json().get("records", []):
            ip = rec.get("ip", "")
            records.append(DNSRecord(
                name=rec.get("name", ""),
                record_type="AAAA" if ":" in ip else "A",
                value=ip,
                zone=zone,
                ttl=0,
            ))

        for rec in self._req("GET", "/dns/cname").json().get("cname_records", []):
            records.append(DNSRecord(
                name=rec.get("domain", ""),
                record_type="CNAME",
                value=rec.get("target", ""),
                zone=zone,
                ttl=0,
            ))

        return records

    def add_record(self, record: DNSRecord) -> None:
        if record.record_type in ("A", "AAAA"):
            self._req("POST", "/dns/records", json={"ip": record.value, "name": record.name})
        elif record.record_type == "CNAME":
            self._req("POST", "/dns/cname", json={"domain": record.name, "target": record.value})
        else:
            raise NotImplementedError(f"Pi-hole does not support {record.record_type} records via API")

    def delete_record(self, record: DNSRecord) -> None:
        if record.record_type in ("A", "AAAA"):
            self._req("DELETE", "/dns/records", json={"ip": record.value, "name": record.name})
        elif record.record_type == "CNAME":
            self._req("DELETE", "/dns/cname", json={"domain": record.name, "target": record.value})
        else:
            raise NotImplementedError(f"Pi-hole does not support {record.record_type} records via API")

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
