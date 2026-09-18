from unittest.mock import patch, MagicMock
from app.models.cache import CachedDHCPScopePool
from app.providers.dhcp.base import DHCPScope
from tests.conftest import TestingSessionLocal


class _KeaLikeProvider:
    source = "kea01"

    def get_scopes(self):
        return [DHCPScope(scope_id="10.10.0.0/24", name="lan", subnet_mask="/24",
                           start_range="10.10.0.10", end_range="10.10.0.200",
                           source=self.source)]

    def get_scope_pools(self, scope_id):
        return [("10.10.0.10", "10.10.0.50"), ("10.10.0.52", "10.10.0.200")]

    def get_leases(self, scope_id):
        return []


class _MsdhcpLikeProvider:
    source = "msdhcp01"

    def get_scopes(self):
        return [DHCPScope(scope_id="10.20.0.0", name="lan2", subnet_mask="/24",
                           start_range="10.20.0.10", end_range="10.20.0.200",
                           source=self.source)]

    def get_leases(self, scope_id):
        return []


def _make_session():
    return TestingSessionLocal()


def test_multi_pool_provider_writes_every_pool():
    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_KeaLikeProvider()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        rows = db.query(CachedDHCPScopePool).filter_by(scope_id="10.10.0.0/24").order_by(CachedDHCPScopePool.start_ip).all()
        assert [(r.start_ip, r.end_ip) for r in rows] == [
            ("10.10.0.10", "10.10.0.50"), ("10.10.0.52", "10.10.0.200"),
        ]
    finally:
        db.close()


def test_single_pool_provider_writes_one_row():
    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_MsdhcpLikeProvider()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        rows = db.query(CachedDHCPScopePool).filter_by(scope_id="10.20.0.0").all()
        assert len(rows) == 1
        assert (rows[0].start_ip, rows[0].end_ip) == ("10.20.0.10", "10.20.0.200")
    finally:
        db.close()
