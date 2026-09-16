"""Regression: MSDNSProvider.get_records() was silently dropping CNAME and
NS records. The PowerShell $data extraction checked IPv4Address/IPv6Address/
NameHost/PtrDomainName/DomainName/MailExchange/DescriptiveText — but a
CNAME's RecordData holds its target in HostNameAlias (see add_record's
Add-DnsServerResourceRecordCName and update_record's _RECORD_DATA_FIELD,
both of which already knew the right field name) and an NS record's holds
it in NameServer, not the dead NameHost check that was already there.
$data stayed $null for both, and the pipeline's own `if ($data -ne $null)`
filtered those rows out before they ever reached Python."""
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


def test_get_records_ps_script_checks_nameserver_for_ns():
    p = _provider()
    p._run = lambda ps: (p.calls.append(ps), "[]")[1]
    p.get_records("example.com")
    assert "NameServer" in p.calls[0]


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


def test_get_records_parses_ns_row():
    p = _provider()
    p._run = lambda ps: json.dumps({
        "HostName": "dev", "RecordType": "NS", "Data": "dc01.example.com", "TTL": 3600,
    })
    records = p.get_records("example.com")
    assert len(records) == 1
    assert records[0].record_type == "NS"
    assert records[0].value == "dc01.example.com"


def test_get_records_ps_script_casts_ttl_to_int64():
    """Regression: TTL = [int]$_.TimeToLive.TotalSeconds overflowed System.Int32
    (max 2147483647) for any record with a TTL above ~68 years — legal on the
    wire, and exactly the kind of value a real NS record can carry — and threw
    a terminating PowerShell conversion error that aborted the entire zone's
    get_records() pipeline. [int] must be [int64]/[long]."""
    p = _provider()
    p._run = lambda ps: (p.calls.append(ps), "[]")[1]
    p.get_records("example.com")
    assert "[int64]" in p.calls[0]
    assert "[int]$_.TimeToLive" not in p.calls[0]


def test_get_records_parses_huge_ttl():
    p = _provider()
    p._run = lambda ps: json.dumps({
        "HostName": "dev", "RecordType": "NS", "Data": "dc01.example.com",
        "TTL": 3315690904,  # overflows a signed 32-bit int; observed in the wild
    })
    records = p.get_records("example.com")
    assert records[0].ttl == 3315690904
