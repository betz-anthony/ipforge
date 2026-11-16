"""Subnet auto-creation from DHCP scopes (sync._auto_create_subnets)."""
import json
from unittest.mock import patch

from app.models.audit_log import AuditLog
from app.models.dhcp_scope_override import DHCPScopeSubnetAutoCreateExclusion
from app.models.provider_config import ProviderConfig
from app.models.subnet import Subnet
from app.providers.dhcp.base import DHCPScope
from tests.conftest import TestingSessionLocal


class _P:
    def __init__(self, source, scopes):
        self.source = source
        self._scopes = scopes

    def get_scopes(self):
        return self._scopes

    def get_leases(self, scope_id):
        return []


def _scope(scope_id, mask="", name="s", start="", end=""):
    return DHCPScope(scope_id=scope_id, name=name, subnet_mask=mask,
                     start_range=start, end_range=end, source="")


def _provider_cfg(db, name, enabled=True, auto=True):
    db.add(ProviderConfig(category="dhcp", provider_type="msdhcp", name=name,
                          config=json.dumps({"auto_create_subnets": auto}), enabled=enabled))
    db.commit()


def _run(providers):
    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=providers), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=TestingSessionLocal):
        sync_module.sync_dhcp()


def _cidrs(db):
    db.expire_all()
    return {s.cidr: s for s in db.query(Subnet).all()}


def test_creates_subnet_from_msdhcp_dotted_mask(db):
    _provider_cfg(db, "dhcp1")
    _run([_P("dhcp1", [_scope("10.10.0.0", "255.255.252.0", "lan", "10.10.0.10", "10.10.3.200")])])
    subs = _cidrs(db)
    assert set(subs) == {"10.10.0.0/22"}
    assert subs["10.10.0.0/22"].dhcp_provider_name == "dhcp1"
    assert db.query(AuditLog).filter_by(resource_type="subnet", action="create").count() == 1


def test_creates_subnet_from_kea_cidr_and_v6_prefix(db):
    _provider_cfg(db, "kea1")
    sc6 = DHCPScope(scope_id="2001:db8::", name="v6", subnet_mask="/64",
                    start_range="", end_range="", ip_version=6, source="")
    _run([_P("kea1", [_scope("10.20.0.0/24"), sc6])])
    assert set(_cidrs(db)) == {"10.20.0.0/24", "2001:db8::/64"}


def test_off_by_default_and_when_provider_flag_false(db):
    _provider_cfg(db, "dhcp1", auto=False)
    _run([_P("dhcp1", [_scope("10.10.0.0", "255.255.252.0")])])
    assert _cidrs(db) == {}


def test_disabled_provider_creates_nothing(db):
    """A disabled provider isn't loaded, so its (possibly still cached)
    scopes must not produce subnets even with the flag on."""
    from app.models.cache import CachedDHCPScope
    from app.core.time import utcnow
    _provider_cfg(db, "dhcp-test", enabled=False)
    db.add(CachedDHCPScope(scope_id="10.10.0.0", name="t", subnet_mask="255.255.252.0",
                           start_range="10.10.0.31", end_range="10.10.3.254",
                           source="dhcp-test", synced_at=utcnow()))
    db.commit()
    _run([])
    assert _cidrs(db) == {}


def test_per_scope_opt_out(db):
    _provider_cfg(db, "dhcp1")
    db.add(DHCPScopeSubnetAutoCreateExclusion(source="dhcp1", scope_id="10.10.0.0"))
    db.commit()
    _run([_P("dhcp1", [_scope("10.10.0.0", "255.255.252.0"), _scope("10.30.0.0", "255.255.255.0")])])
    assert set(_cidrs(db)) == {"10.30.0.0/24"}


def test_nests_under_supernet_and_reparents_children(db):
    _provider_cfg(db, "dhcp1")
    sup = Subnet(name="sup", cidr="10.0.0.0/8", ip_version=4)
    db.add(sup)
    db.flush()
    child = Subnet(name="child", cidr="10.10.1.0/24", ip_version=4, parent_id=sup.id)
    db.add(child)
    db.commit()
    _run([_P("dhcp1", [_scope("10.10.0.0", "255.255.252.0")])])
    subs = _cidrs(db)
    assert subs["10.10.0.0/22"].parent_id == subs["10.0.0.0/8"].id
    assert subs["10.10.1.0/24"].parent_id == subs["10.10.0.0/22"].id


def test_existing_subnet_untouched_and_idempotent(db):
    _provider_cfg(db, "dhcp1")
    db.add(Subnet(name="mine", cidr="10.10.0.0/22", ip_version=4, description="keep"))
    db.commit()
    _run([_P("dhcp1", [_scope("10.10.0.0", "255.255.252.0", "other")])])
    _run([_P("dhcp1", [_scope("10.10.0.0", "255.255.252.0", "other")])])
    subs = _cidrs(db)
    assert list(subs) == ["10.10.0.0/22"]
    assert subs["10.10.0.0/22"].name == "mine"


def test_non_network_scope_is_skipped(db):
    _provider_cfg(db, "pihole1")
    _run([_P("pihole1", [_scope("pihole-dhcp", "", "Pi-hole DHCP", "192.168.1.50", "192.168.1.150")])])
    assert _cidrs(db) == {}


def test_scope_toggle_endpoint(client, db):
    from app.models.cache import CachedDHCPScope
    from app.core.time import utcnow
    db.add(CachedDHCPScope(scope_id="10.10.0.0", name="t", subnet_mask="255.255.252.0",
                           start_range="", end_range="", source="dhcp1", synced_at=utcnow()))
    db.commit()
    scope = lambda: next(s for s in client.get("/api/v1/dhcp/scopes").json() if s["scope_id"] == "10.10.0.0")
    assert scope()["auto_create_subnet"] is True
    r = client.request("PUT", "/api/v1/dhcp/scopes/10.10.0.0/auto-create-subnet?source=dhcp1",
                       json={"enabled": False})
    assert r.status_code == 200, r.text
    assert scope()["auto_create_subnet"] is False
    client.request("PUT", "/api/v1/dhcp/scopes/10.10.0.0/auto-create-subnet?source=dhcp1",
                   json={"enabled": True})
    assert scope()["auto_create_subnet"] is True


def test_scope_list_reports_provider_flag(client, db):
    from app.models.cache import CachedDHCPScope
    from app.core.time import utcnow
    _provider_cfg(db, "on1", auto=True)
    _provider_cfg(db, "off1", auto=False)
    _provider_cfg(db, "dis1", enabled=False, auto=True)
    for src in ("on1", "off1", "dis1"):
        db.add(CachedDHCPScope(scope_id="10.1.0.0", name=src, subnet_mask="255.255.255.0",
                               start_range="", end_range="", source=src, synced_at=utcnow()))
    db.commit()
    flags = {s["source"]: s["provider_auto_create_subnets"]
             for s in client.get("/api/v1/dhcp/scopes").json()}
    assert flags == {"on1": True, "off1": False, "dis1": False}
