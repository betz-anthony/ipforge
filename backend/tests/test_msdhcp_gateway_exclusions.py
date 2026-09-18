import json
from app.providers.dhcp.msdhcp import MSDHCPProvider


def _provider():
    p = MSDHCPProvider({"dhcp_server": "dc01", "winrm_host": "dc01"}, "msdhcp01")
    p.calls = []
    return p


def test_get_scope_gateway_ps_script_queries_option_3():
    p = _provider()
    p._run = lambda ps: (p.calls.append(ps), json.dumps({"Value": ["10.10.0.1"]}))[1]
    gw = p.get_scope_gateway("10.10.0.0")
    assert "-OptionId 3" in p.calls[0]
    assert "Get-DhcpServerv4OptionValue" in p.calls[0]
    assert gw == "10.10.0.1"


def test_get_scope_gateway_none_when_no_value():
    p = _provider()
    p._run = lambda ps: "[]"
    assert p.get_scope_gateway("10.10.0.0") is None


def test_get_scope_exclusions_ps_script_and_parsing():
    p = _provider()
    p._run = lambda ps: (p.calls.append(ps), json.dumps({
        "StartRange": {"IPAddressToString": "10.10.0.1"},
        "EndRange": {"IPAddressToString": "10.10.0.9"},
    }))[1]
    excl = p.get_scope_exclusions("10.10.0.0")
    assert "Get-DhcpServerv4ExclusionRange" in p.calls[0]
    assert excl == [("10.10.0.1", "10.10.0.9")]


def test_get_scope_exclusions_empty_when_none_configured():
    p = _provider()
    p._run = lambda ps: "[]"
    assert p.get_scope_exclusions("10.10.0.0") == []
