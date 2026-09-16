"""Regression: MSDNSProvider.get_records() was silently dropping CNAME
records. The PowerShell $data extraction checked IPv4Address/IPv6Address/
NameHost/PtrDomainName/DomainName/MailExchange/DescriptiveText but never
RecordData.HostNameAlias (the field CNAME actually uses — see add_record's
Add-DnsServerResourceRecordCName and update_record's _RECORD_DATA_FIELD,
both of which already knew the right field name). $data stayed $null for
every CNAME row, and the pipeline's own `if ($data -ne $null)` filtered
those rows out before they ever reached Python."""
import json

from app.providers.dns.msdns import MSDNSProvider


def _provider():
    p = MSDNSProvider({"dns_server": "dc01", "winrm_host": "dc01"}, "msdns01")
    p.calls = []
    return p


def test_get_records_ps_script_checks_hostnamealias_for_cname():
    p = _provider()
    p._run = lambda ps: (p.calls.append(ps), "[]")[1]
    p.get_records("example.com")
    assert "HostNameAlias" in p.calls[0]


def test_get_records_parses_cname_row():
    p = _provider()
    p._run = lambda ps: json.dumps({
        "HostName": "alias", "RecordType": "CNAME", "Data": "target.example.com", "TTL": 3600,
    })
    records = p.get_records("example.com")
    assert len(records) == 1
    assert records[0].record_type == "CNAME"
    assert records[0].value == "target.example.com"
    assert records[0].name == "alias"
