"""Google Cloud DNS provider (CLOUD-DNS-001).

google-cloud-dns + a service-account key. Only `_client` touches GCP; record
mapping is unit-testable with a mocked client.
"""
import json

from app.providers.dns.base import DNSProvider, DNSRecord


def _strip(name: str) -> str:
    return name[:-1] if name.endswith(".") else name


def _dotted(name: str) -> str:
    return name if name.endswith(".") else name + "."


class GCPDNSProvider(DNSProvider):
    supports_ptr = True

    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._cfg = cfg

    def _client(self):
        from google.cloud import dns
        from google.oauth2 import service_account
        info = json.loads(self._cfg.get("service_account_json") or "{}")
        creds = service_account.Credentials.from_service_account_info(info)
        return dns.Client(project=self._cfg.get("project_id"), credentials=creds)

    def _zone(self, client, zone: str):
        for z in client.list_zones():
            if _strip(z.dns_name) == zone:
                return client.zone(z.name)
        raise RuntimeError(f"GCP managed zone for {zone!r} not found")

    def get_zones(self) -> list[str]:
        return [_strip(z.dns_name) for z in self._client().list_zones()]

    def get_records(self, zone: str) -> list[DNSRecord]:
        client = self._client()
        gz = self._zone(client, zone)
        out: list[DNSRecord] = []
        for rs in gz.list_resource_record_sets():
            for value in rs.rrdatas:
                out.append(DNSRecord(
                    name=_strip(rs.name), record_type=rs.record_type, value=value,
                    zone=zone, ttl=rs.ttl, source=self.source,
                ))
        return out

    def _change(self, record: DNSRecord, action: str) -> None:
        client = self._client()
        gz = self._zone(client, record.zone)
        rrset = gz.resource_record_set(_dotted(record.name), record.record_type, record.ttl, [record.value])
        changes = gz.changes()
        if action == "add":
            changes.add_record_set(rrset)
        else:
            changes.delete_record_set(rrset)
        changes.create()

    def add_record(self, record: DNSRecord) -> None:
        self._change(record, "add")

    def delete_record(self, record: DNSRecord) -> None:
        self._change(record, "delete")

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
