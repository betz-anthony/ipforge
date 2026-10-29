"""DNS-DHCP-EDIT-001 P4 — MSDNSProvider.update_record via Set-DnsServerResourceRecord."""
from app.providers.dns.msdns import MSDNSProvider
from app.providers.dns.base import DNSRecord


def _provider():
    p = MSDNSProvider({"dns_server": "dc01", "winrm_host": "dc01"}, "msdns01")
    p.calls = []
    p._run = lambda ps: (p.calls.append(ps), "")[1]
    return p


def test_update_record_a_uses_clone_and_set_in_one_call():
    p = _provider()
    old = DNSRecord(name="web01", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600)
    new = DNSRecord(name="web01", record_type="A", value="10.0.1.9", zone="example.com", ttl=60)
    p.update_record(old, new)

    assert len(p.calls) == 1, "get + clone + modify + set must be one WinRM round trip"
    ps = p.calls[0]
    assert "Get-DnsServerResourceRecord" in ps
    assert ".Clone()" in ps
    assert "Set-DnsServerResourceRecord" in ps
    assert "-OldInputObject" in ps and "-NewInputObject" in ps
    assert "IPv4Address" in ps
    assert "'10.0.1.9'" in ps
    assert "'web01'" in ps


def test_update_record_aaaa_uses_ipv6_field():
    p = _provider()
    old = DNSRecord(name="host6", record_type="AAAA", value="2001:db8::5", zone="example.com", ttl=3600)
    new = DNSRecord(name="host6", record_type="AAAA", value="2001:db8::9", zone="example.com", ttl=3600)
    p.update_record(old, new)
    assert "IPv6Address" in p.calls[0]


def test_update_record_cname_uses_hostnamealias_field():
    p = _provider()
    old = DNSRecord(name="alias", record_type="CNAME", value="target1.example.com", zone="example.com", ttl=3600)
    new = DNSRecord(name="alias", record_type="CNAME", value="target2.example.com", zone="example.com", ttl=3600)
    p.update_record(old, new)
    assert "HostNameAlias" in p.calls[0]
    assert "Clone" in p.calls[0]


def test_update_record_type_change_falls_back_to_delete_add():
    p = _provider()
    old = DNSRecord(name="web01", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600)
    new = DNSRecord(name="web01", record_type="CNAME", value="canonical.example.com", zone="example.com", ttl=3600)
    p.update_record(old, new)

    assert len(p.calls) == 2
    assert "Remove-DnsServerResourceRecord" in p.calls[0]
    assert "Add-DnsServerResourceRecordCName" in p.calls[1]
    assert "Set-DnsServerResourceRecord" not in "".join(p.calls)


def test_update_record_rename_adds_new_then_removes_only_the_old_value():
    # Set-DnsServerResourceRecord cannot change a record's owner name, so a
    # rename must be add-new + remove-old, never a clone/set.
    p = _provider()
    old = DNSRecord(name="web01", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600)
    new = DNSRecord(name="web02", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600)
    p.update_record(old, new)

    assert len(p.calls) == 2
    assert "Add-DnsServerResourceRecordA" in p.calls[0] and "'web02'" in p.calls[0]
    assert "Remove-DnsServerResourceRecord" in p.calls[1] and "'web01'" in p.calls[1]
    assert "'10.0.1.5'" in p.calls[1], "must not remove sibling records of the old name"
    assert "Set-DnsServerResourceRecord" not in "".join(p.calls)


def test_update_record_rename_removes_new_record_if_old_removal_fails():
    p = _provider()
    def run(ps):
        p.calls.append(ps)
        if "Remove-DnsServerResourceRecord" in ps and "'web01'" in ps:
            raise RuntimeError("access denied")
        return ""
    p._run = run
    old = DNSRecord(name="web01", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600)
    new = DNSRecord(name="web02", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600)
    try:
        p.update_record(old, new)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    assert "Remove-DnsServerResourceRecord" in p.calls[-1] and "'web02'" in p.calls[-1]


def test_delete_a_record_matches_on_value_not_just_name_and_type():
    p = _provider()
    p.delete_record(DNSRecord(name="web", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600))
    assert len(p.calls) == 1
    ps = p.calls[0]
    assert "'10.0.1.5'" in ps and "IPv4Address" in ps
    assert "throw 'record not found'" in ps
    assert "-InputObject $rec" in ps


def test_delete_txt_record_matches_on_text():
    p = _provider()
    p.delete_record(DNSRecord(name="@", record_type="TXT", value="v=spf1 -all", zone="example.com", ttl=3600))
    assert "DescriptiveText" in p.calls[0] and "'v=spf1 -all'" in p.calls[0]


def test_delete_srv_record_falls_back_to_name_and_type():
    p = _provider()
    p.delete_record(DNSRecord(name="_sip._tcp", record_type="SRV", value="sip.example.com", zone="example.com", ttl=3600))
    assert "-RRType 'SRV'" in p.calls[0] and "Where-Object" not in p.calls[0]
