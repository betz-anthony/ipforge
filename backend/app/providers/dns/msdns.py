import json
import threading
from winrm.exceptions import WinRMTransportError
from app.providers.dns.base import DNSProvider, DNSRecord
from app.providers._ps import ps_quote
from app.providers._winrm import build_session, check_result

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
            self._session = build_session(
                self._winrm_host,
                self._winrm_user,
                self._winrm_password,
                self._winrm_transport,
            )
        return self._session

    def _run(self, ps: str) -> str:
        with self._lock:
            try:
                result = self.session.run_ps(ps)
            except _WINRM_RETRY:
                self._session = None
                result = self.session.run_ps(ps)
            return check_result(result)

    def _parse_json(self, out: str) -> list:
        # An empty pipeline produces no ConvertTo-Json output at all — a
        # server with zero zones/records is not an error.
        if not out.strip():
            return []
        data = json.loads(out)
        return data if isinstance(data, list) else [data]

    def get_zones(self) -> list[str]:
        out = self._run(
            f"Get-DnsServerZone -ComputerName {ps_quote(self._dns_server)} "
            "| Select-Object -ExpandProperty ZoneName | ConvertTo-Json"
        )
        return self._parse_json(out)

    def get_records(self, zone: str) -> list[DNSRecord]:
        ps = f"""
Get-DnsServerResourceRecord -ZoneName {ps_quote(zone)} -ComputerName {ps_quote(self._dns_server)} | ForEach-Object {{
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
                f"Add-DnsServerResourceRecordA -Name {ps_quote(record.name)} "
                f"-ZoneName {ps_quote(record.zone)} -IPv4Address {ps_quote(record.value)} "
                f"-TimeToLive {ttl} -ComputerName {ps_quote(self._dns_server)}"
            )
        elif record.record_type == "AAAA":
            self._run(
                f"Add-DnsServerResourceRecordAAAA -Name {ps_quote(record.name)} "
                f"-ZoneName {ps_quote(record.zone)} -IPv6Address {ps_quote(record.value)} "
                f"-TimeToLive {ttl} -ComputerName {ps_quote(self._dns_server)}"
            )
        elif record.record_type == "PTR":
            self._run(
                f"Add-DnsServerResourceRecordPtr -Name {ps_quote(record.name)} "
                f"-ZoneName {ps_quote(record.zone)} -PtrDomainName {ps_quote(record.value)} "
                f"-ComputerName {ps_quote(self._dns_server)}"
            )
        elif record.record_type == "CNAME":
            self._run(
                f"Add-DnsServerResourceRecordCName -Name {ps_quote(record.name)} "
                f"-ZoneName {ps_quote(record.zone)} -HostNameAlias {ps_quote(record.value)} "
                f"-ComputerName {ps_quote(self._dns_server)}"
            )
        else:
            raise NotImplementedError(f"Record type {record.record_type} not supported")

    def delete_record(self, record: DNSRecord) -> None:
        self._run(
            f"Remove-DnsServerResourceRecord -ZoneName {ps_quote(record.zone)} "
            f"-Name {ps_quote(record.name)} -RRType {ps_quote(record.record_type)} -Force "
            f"-ComputerName {ps_quote(self._dns_server)}"
        )

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
