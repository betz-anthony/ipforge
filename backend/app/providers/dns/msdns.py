import json
import threading
import winrm
from winrm.exceptions import WinRMTransportError
from app.providers.dns.base import DNSProvider, DNSRecord

try:
    from spnego.exceptions import BadMICError as _BadMICError
    _WINRM_RETRY = (WinRMTransportError, _BadMICError)
except ImportError:
    _WINRM_RETRY = (WinRMTransportError,)


class MSDNSProvider(DNSProvider):
    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._winrm_host = cfg.get("winrm_host", "")
        self._winrm_user = cfg.get("winrm_user", "")
        self._winrm_password = cfg.get("winrm_password", "")
        self._winrm_transport = cfg.get("winrm_transport", "ntlm")
        self._dns_server = cfg.get("dns_server", "")
        self._session = None
        self._lock = threading.Lock()

    @property
    def session(self):
        if self._session is None:
            self._session = winrm.Session(
                self._winrm_host,
                auth=(self._winrm_user, self._winrm_password),
                transport=self._winrm_transport,
            )
        return self._session

    def _run(self, ps: str) -> str:
        with self._lock:
            try:
                result = self.session.run_ps(ps)
            except _WINRM_RETRY:
                self._session = None
                result = self.session.run_ps(ps)
            if result.status_code != 0:
                raise RuntimeError(result.std_err.decode())
            return result.std_out.decode()

    def get_zones(self) -> list[str]:
        out = self._run(
            f"Get-DnsServerZone -ComputerName '{self._dns_server}' "
            "| Select-Object -ExpandProperty ZoneName | ConvertTo-Json"
        )
        data = json.loads(out)
        return data if isinstance(data, list) else [data]

    def get_records(self, zone: str) -> list[DNSRecord]:
        ps = f"""
Get-DnsServerResourceRecord -ZoneName '{zone}' -ComputerName '{self._dns_server}' | ForEach-Object {{
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
        ttl = f"([System.TimeSpan]::FromSeconds({record.ttl}))"
        if record.record_type == "A":
            self._run(
                f"Add-DnsServerResourceRecordA -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -IPv4Address '{record.value}' "
                f"-TimeToLive {ttl} -ComputerName '{self._dns_server}'"
            )
        elif record.record_type == "AAAA":
            self._run(
                f"Add-DnsServerResourceRecordAAAA -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -IPv6Address '{record.value}' "
                f"-TimeToLive {ttl} -ComputerName '{self._dns_server}'"
            )
        elif record.record_type == "PTR":
            self._run(
                f"Add-DnsServerResourceRecordPtr -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -PtrDomainName '{record.value}' "
                f"-ComputerName '{self._dns_server}'"
            )
        elif record.record_type == "CNAME":
            self._run(
                f"Add-DnsServerResourceRecordCName -Name '{record.name}' "
                f"-ZoneName '{record.zone}' -HostNameAlias '{record.value}' "
                f"-ComputerName '{self._dns_server}'"
            )
        else:
            raise NotImplementedError(f"Record type {record.record_type} not supported")

    def delete_record(self, record: DNSRecord) -> None:
        self._run(
            f"Remove-DnsServerResourceRecord -ZoneName '{record.zone}' "
            f"-Name '{record.name}' -RRType '{record.record_type}' -Force "
            f"-ComputerName '{self._dns_server}'"
        )

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
