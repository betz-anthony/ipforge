"""Azure DNS provider (CLOUD-DNS-001).

azure-identity + azure-mgmt-dns. Only `_client` touches Azure; record mapping is
unit-testable with a mocked DnsManagementClient.
"""
from app.providers.dns.base import DNSProvider, DNSRecord

_VALUE_FIELDS = {
    "A":     lambda rs: [r.ipv4_address for r in (rs.a_records or [])],
    "AAAA":  lambda rs: [r.ipv6_address for r in (rs.aaaa_records or [])],
    "CNAME": lambda rs: [rs.cname_record.cname] if getattr(rs, "cname_record", None) else [],
    "PTR":   lambda rs: [r.ptrdname for r in (getattr(rs, "ptr_records", None) or [])],
    "TXT":   lambda rs: [" ".join(r.value) for r in (getattr(rs, "txt_records", None) or [])],
}


class AzureDNSProvider(DNSProvider):
    supports_ptr = True

    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._cfg = cfg
        self._rg = cfg.get("resource_group", "")

    def _client(self):
        from azure.identity import ClientSecretCredential
        from azure.mgmt.dns import DnsManagementClient
        cred = ClientSecretCredential(
            tenant_id=self._cfg.get("tenant_id"),
            client_id=self._cfg.get("client_id"),
            client_secret=self._cfg.get("client_secret"),
        )
        return DnsManagementClient(cred, self._cfg.get("subscription_id"))

    def _relative(self, fqdn: str, zone: str) -> str:
        if fqdn == zone:
            return "@"
        suffix = "." + zone
        return fqdn[:-len(suffix)] if fqdn.endswith(suffix) else fqdn

    def get_zones(self) -> list[str]:
        return [z.name for z in self._client().zones.list_by_resource_group(self._rg)]

    def get_records(self, zone: str) -> list[DNSRecord]:
        client = self._client()
        out: list[DNSRecord] = []
        for rs in client.record_sets.list_by_dns_zone(self._rg, zone):
            rtype = rs.type.split("/")[-1] if "/" in rs.type else rs.type
            extractor = _VALUE_FIELDS.get(rtype)
            if extractor is None:
                continue
            fqdn = zone if rs.name == "@" else f"{rs.name}.{zone}"
            for value in extractor(rs):
                out.append(DNSRecord(name=fqdn, record_type=rtype, value=value,
                                     zone=zone, ttl=rs.ttl or 3600, source=self.source))
        return out

    def _record_set(self, record: DNSRecord):
        from azure.mgmt.dns.models import (
            RecordSet, ARecord, AaaaRecord, CnameRecord, PtrRecord, TxtRecord,
        )
        t = record.record_type
        if t == "A":
            return RecordSet(ttl=record.ttl, a_records=[ARecord(ipv4_address=record.value)])
        if t == "AAAA":
            return RecordSet(ttl=record.ttl, aaaa_records=[AaaaRecord(ipv6_address=record.value)])
        if t == "CNAME":
            return RecordSet(ttl=record.ttl, cname_record=CnameRecord(cname=record.value))
        if t == "PTR":
            return RecordSet(ttl=record.ttl, ptr_records=[PtrRecord(ptrdname=record.value)])
        if t == "TXT":
            return RecordSet(ttl=record.ttl, txt_records=[TxtRecord(value=[record.value])])
        raise RuntimeError(f"Azure DNS: unsupported record type {t}")

    def add_record(self, record: DNSRecord) -> None:
        self._client().record_sets.create_or_update(
            self._rg, record.zone, self._relative(record.name, record.zone),
            record.record_type, self._record_set(record),
        )

    def delete_record(self, record: DNSRecord) -> None:
        self._client().record_sets.delete(
            self._rg, record.zone, self._relative(record.name, record.zone), record.record_type,
        )

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.add_record(new)  # create_or_update replaces the record set
