from unittest.mock import patch, MagicMock
from app.models.cache import CachedDHCPScope, CachedDHCPScopePool
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


class _PartialFailureKeaProvider:
    """Two scopes; get_scope_pools raises for one of them (simulating the
    live requests.post() call KeaDHCPProvider.get_scope_pools makes)."""
    source = "kea02"

    def get_scopes(self):
        return [
            DHCPScope(scope_id="10.30.0.0/24", name="ok", subnet_mask="/24",
                       start_range="10.30.0.10", end_range="10.30.0.200",
                       source=self.source),
            DHCPScope(scope_id="10.31.0.0/24", name="broken", subnet_mask="/24",
                       start_range="10.31.0.10", end_range="10.31.0.200",
                       source=self.source),
        ]

    def get_scope_pools(self, scope_id):
        if scope_id == "10.31.0.0/24":
            raise RuntimeError("simulated get_scope_pools failure")
        return [("10.30.0.10", "10.30.0.200")]

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


def test_scope_pool_failure_for_one_scope_does_not_block_others():
    """get_scope_pools raising for scope N must not abort the rest of the
    provider's scopes: the other scope still gets its pools populated, and
    both scopes still get their CachedDHCPScope row + land in scope_list
    (proven here indirectly by both rows existing after sync_dhcp completes
    without raising)."""
    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_PartialFailureKeaProvider()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        ok_rows = db.query(CachedDHCPScopePool).filter_by(scope_id="10.30.0.0/24").all()
        assert [(r.start_ip, r.end_ip) for r in ok_rows] == [("10.30.0.10", "10.30.0.200")]

        broken_rows = db.query(CachedDHCPScopePool).filter_by(scope_id="10.31.0.0/24").all()
        assert broken_rows == []

        scope_ids = {
            r.scope_id for r in db.query(CachedDHCPScope).filter_by(source="kea02").all()
        }
        assert scope_ids == {"10.30.0.0/24", "10.31.0.0/24"}
    finally:
        db.close()


def test_scope_pool_failure_leaves_existing_cache_rows_untouched():
    """When get_scope_pools fails for a scope that already had cached pool
    rows from a prior sync, those rows must be left as-is (not deleted
    without replacement)."""
    db = TestingSessionLocal()
    try:
        db.add(CachedDHCPScopePool(
            scope_id="10.31.0.0/24", source="kea02",
            start_ip="10.31.0.10", end_ip="10.31.0.200",
        ))
        db.commit()
    finally:
        db.close()

    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_PartialFailureKeaProvider()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        rows = db.query(CachedDHCPScopePool).filter_by(scope_id="10.31.0.0/24").all()
        assert [(r.start_ip, r.end_ip) for r in rows] == [("10.31.0.10", "10.31.0.200")]
    finally:
        db.close()
