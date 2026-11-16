"""Scope-defined DHCP options + lease duration: providers, sync cache, API."""
import json
from unittest.mock import patch

from app.models.cache import CachedDHCPScopeConfig
from app.providers.dhcp.base import DHCPScope, DHCPScopeConfig, DHCPScopeOption
from app.providers.dhcp.isc import KeaDHCPProvider
from app.providers.dhcp.msdhcp import MSDHCPProvider
from tests.conftest import TestingSessionLocal


def _msdhcp(outputs):
    p = MSDHCPProvider({"dhcp_server": "dc01", "winrm_host": "dc01"}, "ms1")
    p.calls = []

    def run(ps):
        p.calls.append(ps)
        return outputs[len(p.calls) - 1]
    p._run = run
    return p


def test_msdhcp_scope_config_options_and_lease():
    p = _msdhcp([
        json.dumps([
            {"OptionId": 6, "Name": "DNS Servers", "Value": ["10.0.0.2", "10.0.0.3"]},
            {"OptionId": 3, "Name": "Router", "Value": ["10.0.0.1"]},
            {"OptionId": 42, "Name": "x", "Value": ["10.0.0.9"]},
        ]),
        json.dumps({"LeaseSeconds": 691200}),
    ])
    cfg = p.get_scope_config("10.0.0.0")
    assert "-All" not in p.calls[0] and "Get-DhcpServerv4OptionValue" in p.calls[0]
    assert [(o.code, o.name, o.value) for o in cfg.options] == [
        (3, "Router", "10.0.0.1"), (6, "DNS Servers", "10.0.0.2, 10.0.0.3"), (42, "NTP Servers", "10.0.0.9"),
    ]
    assert cfg.lease_seconds == 691200


def test_msdhcp_scope_config_empty_scope_and_v6():
    p = _msdhcp(["[]", "[]"])
    cfg = p.get_scope_config("10.0.0.0")
    assert cfg.options == [] and cfg.lease_seconds is None
    assert MSDHCPProvider({"dhcp_server": "d", "winrm_host": "d"}, "m").get_scope_config("2001:db8::") == DHCPScopeConfig()


def test_kea_scope_config_subnet_only():
    p = KeaDHCPProvider({"url": "http://kea:8000"}, "kea1")
    p._get_subnets = lambda service="dhcp4": [
        {"subnet": "10.1.0.0/24", "valid-lifetime": 3600, "option-data": [
            {"name": "routers", "code": 3, "data": "10.1.0.1"},
            {"name": "ntp-servers", "code": 42, "data": "10.1.0.5, 10.1.0.6"},
        ]},
        {"subnet": "10.2.0.0/24", "option-data": []},
    ]
    cfg = p.get_scope_config("10.1.0.0/24")
    assert [(o.code, o.name, o.value) for o in cfg.options] == [
        (3, "Router", "10.1.0.1"), (42, "NTP Servers", "10.1.0.5, 10.1.0.6"),
    ]
    assert cfg.lease_seconds == 3600
    assert p.get_scope_config("10.2.0.0/24").lease_seconds is None


class _Prov:
    source = "kea1"

    def __init__(self, fail=False):
        self.fail = fail

    def get_scopes(self):
        return [DHCPScope(scope_id="10.1.0.0/24", name="a", subnet_mask="", start_range="10.1.0.10",
                          end_range="10.1.0.20", source="kea1")]

    def get_leases(self, scope_id):
        return []

    def get_scope_config(self, scope_id):
        if self.fail:
            raise RuntimeError("boom")
        return DHCPScopeConfig(options=[DHCPScopeOption(code=6, name="DNS Servers", value="10.1.0.2")],
                               lease_seconds=7200)


def _sync(prov):
    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[prov]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=TestingSessionLocal):
        sync_module.sync_dhcp()


def test_sync_caches_config_and_api_returns_it(client, db):
    _sync(_Prov())
    scope = client.get("/api/v1/dhcp/scopes").json()[0]
    assert scope["lease_seconds"] == 7200
    assert scope["options"] == [{"code": 6, "name": "DNS Servers", "value": "10.1.0.2"}]


def test_failed_config_fetch_keeps_last_good_cache(client, db):
    _sync(_Prov())
    _sync(_Prov(fail=True))
    scope = client.get("/api/v1/dhcp/scopes").json()[0]
    assert scope["lease_seconds"] == 7200
    assert db.query(CachedDHCPScopeConfig).count() == 1
