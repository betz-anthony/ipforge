import json
import winrm
from app.config import settings
from app.providers.dns.base import DNSProvider, DNSRecord


class MSDNSProvider(DNSProvider):
    def __init__(self):
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = winrm.Session(
                settings.ms_winrm_host,
                auth=(settings.ms_winrm_user, settings.ms_winrm_password),
                transport=settings.ms_winrm_transport,
            )
        return self._session

    def _run(self, ps: str) -> str:
        result = self.session.run_ps(ps)
        if result.status_code != 0:
            raise RuntimeError(result.std_err.decode())
        return result.std_out.decode()

    def get_zones(self) -> list[str]:
        out = self._run(
            f"Get-DnsServerZone -ComputerName '{settings.ms_dns_server}' "
            "| Select-Object -ExpandProperty ZoneName | ConvertTo-Json"
        )
        data = json.loads(out)
        return data if isinstance(data, list) else [data]

    def get_records(self, zone: str) -> list[DNSRecord]:
        # PS 5.1-compatible: no ?? operator; resolve IP objects to strings;
        # convert TimeToLive to int seconds inside PowerShell.
        ps = f"""
Get-DnsServerResourceRecord -ZoneName '{zone}' -ComputerName '{settings.ms_dns_server}' | ForEach-Object {{
    $rd = $_.RecordData
    if ($rd.IPv4Address)      {{ $data = $rd.IPv4Address.IPAddressToString }}
    elseif ($rd.IPv6Address)  {{ $data = $rd.IPv6Address.IPAddressToString }}
    elseif ($rd.NameHost)     {{ $data = $rd.NameHost }}
    elseif ($rd.PtrDomainName){{ $data = $rd.PtrDomainName }}
    elseif ($rd.DomainName)   {{ $data = $rd.DomainName }}
    elseif ($rd.MailExchange) {{ $data = $rd.MailExchange }}
    elseif ($rd.DescriptiveText) {{ $data = $rd.DescriptiveText }}
    else {{ $data = $null }}
    if ($data -ne $null) {{
        [PSCustomObject]@{{
            HostName   = $_.HostName
            RecordType = $_.RecordType
            Data       = $data
            TTL        = [int]$_.TimeToLive.TotalSeconds
        }}
    }}
}} | ConvertTo-Json
"""
        out = self._run(ps)
        if not out.strip():
            return []
        records = json.loads(out)
        if isinstance(records, dict):
            records = [records]
        return [
            DNSRecord(
                name=r["HostName"],
                record_type=r["RecordType"],
                value=r.get("Data") or "",
                zone=zone,
                ttl=r.get("TTL", 3600),
            )
            for r in records
            if r.get("Data")
        ]

    def add_record(self, record: DNSRecord) -> None:
        srv = settings.ms_dns_server
        ttl = f"([System.TimeSpan]::FromSeconds({record.ttl}))"
        if record.record_type == "A":
            self._run(
                f"Add-DnsServerResourceRecordA -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -IPv4Address '{record.value}' "
                f"-TimeToLive {ttl} -ComputerName '{srv}'"
            )
        elif record.record_type == "AAAA":
            self._run(
                f"Add-DnsServerResourceRecordAAAA -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -IPv6Address '{record.value}' "
                f"-TimeToLive {ttl} -ComputerName '{srv}'"
            )
        elif record.record_type == "PTR":
            self._run(
                f"Add-DnsServerResourceRecordPtr -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -PtrDomainName '{record.value}' "
                f"-ComputerName '{srv}'"
            )
        elif record.record_type == "CNAME":
            self._run(
                f"Add-DnsServerResourceRecordCName -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -HostNameAlias '{record.value}' "
                f"-ComputerName '{srv}'"
            )
        else:
            raise NotImplementedError(f"Record type {record.record_type} not supported")

    def delete_record(self, record: DNSRecord) -> None:
        self._run(
            f"Remove-DnsServerResourceRecord -ZoneName '{record.zone}' "
            f"-Name '{record.name}' -RRType '{record.record_type}' -Force "
            f"-ComputerName '{settings.ms_dns_server}'"
        )

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
