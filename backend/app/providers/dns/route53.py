"""AWS Route 53 DNS provider (CLOUD-DNS-001).

Uses boto3 (SigV4). Only `_client` touches AWS, so record mapping is unit-testable
with a mocked client.
"""
from app.providers.dns.base import DNSProvider, DNSRecord


def _strip(name: str) -> str:
    return name[:-1] if name.endswith(".") else name


class Route53DNSProvider(DNSProvider):
    supports_ptr = True

    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._cfg = cfg
        self._zone_ids: dict[str, str] = {}

    def _client(self):
        import boto3  # lazy so tests need no boto3
        kwargs = {
            "aws_access_key_id": self._cfg.get("aws_access_key_id"),
            "aws_secret_access_key": self._cfg.get("aws_secret_access_key"),
        }
        if self._cfg.get("region"):
            kwargs["region_name"] = self._cfg["region"]
        return boto3.client("route53", **kwargs)

    def _zone_id(self, zone: str, client=None) -> str:
        client = client or self._client()
        if not self._zone_ids:
            for z in client.list_hosted_zones().get("HostedZones", []):
                self._zone_ids[_strip(z["Name"])] = z["Id"]
        zid = self._zone_ids.get(zone)
        if zid is None:
            raise RuntimeError(f"Route53 hosted zone {zone!r} not found")
        return zid

    def get_zones(self) -> list[str]:
        return [_strip(z["Name"]) for z in self._client().list_hosted_zones().get("HostedZones", [])]

    def get_records(self, zone: str) -> list[DNSRecord]:
        client = self._client()
        zid = self._zone_id(zone, client)
        out: list[DNSRecord] = []
        kwargs = {"HostedZoneId": zid}
        while True:
            resp = client.list_resource_record_sets(**kwargs)
            for rrset in resp.get("ResourceRecordSets", []):
                rtype = rrset.get("Type", "")
                ttl = rrset.get("TTL", 3600)
                for rr in rrset.get("ResourceRecords", []):
                    out.append(DNSRecord(
                        name=_strip(rrset["Name"]), record_type=rtype,
                        value=rr["Value"], zone=zone, ttl=ttl, source=self.source,
                    ))
            if not resp.get("IsTruncated"):
                break
            kwargs.update(
                StartRecordName=resp.get("NextRecordName"),
                StartRecordType=resp.get("NextRecordType"),
            )
        return out

    def _change(self, record: DNSRecord, action: str) -> None:
        client = self._client()
        zid = self._zone_id(record.zone, client)
        client.change_resource_record_sets(
            HostedZoneId=zid,
            ChangeBatch={"Changes": [{
                "Action": action,
                "ResourceRecordSet": {
                    "Name": record.name, "Type": record.record_type,
                    "TTL": record.ttl, "ResourceRecords": [{"Value": record.value}],
                },
            }]},
        )

    def add_record(self, record: DNSRecord) -> None:
        self._change(record, "UPSERT")

    def delete_record(self, record: DNSRecord) -> None:
        self._change(record, "DELETE")

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        # UPSERT replaces the rrset for this name+type with the new value/ttl.
        self._change(new, "UPSERT")
