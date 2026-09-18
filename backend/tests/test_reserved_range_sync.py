from unittest.mock import patch
from app.models.subnet import Subnet
from app.models.subnet_range import SubnetRange
from app.providers.dhcp.base import DHCPScope
from app.core.time import utcnow
from tests.conftest import TestingSessionLocal


def _make_session():
    return TestingSessionLocal()


class _ProviderWithGatewayAndExclusions:
    source = "msdhcp01"

    def get_scopes(self):
        return [DHCPScope(scope_id="10.10.0.0", name="lan", subnet_mask="/24",
                           start_range="10.10.0.10", end_range="10.10.0.200",
                           source=self.source)]

    def get_leases(self, scope_id):
        return []

    def get_scope_gateway(self, scope_id):
        return "10.10.0.1"

    def get_scope_exclusions(self, scope_id):
        return [("10.10.0.2", "10.10.0.9")]


def _seed_subnet(db):
    s = Subnet(name="lan", cidr="10.10.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    return s


def test_sync_creates_gateway_and_exclusion_ranges():
    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id  # capture while session is still open (expire_on_commit)
    db.close()

    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_ProviderWithGatewayAndExclusions()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id, source="msdhcp01").all()
        by_kind = {(r.kind, r.start_ip, r.end_ip) for r in rows}
        assert ("gateway", "10.10.0.1", "10.10.0.1") in by_kind
        assert ("excluded", "10.10.0.2", "10.10.0.9") in by_kind
    finally:
        db.close()


def test_sync_never_touches_manual_ranges():
    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id  # capture while session is still open (expire_on_commit)
    db.add(SubnetRange(subnet_id=subnet_id, start_ip="10.10.0.250", end_ip="10.10.0.250",
                        kind="static", label="printer", source=None))
    db.commit()
    db.close()

    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_ProviderWithGatewayAndExclusions()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        manual = db.query(SubnetRange).filter_by(subnet_id=subnet_id, source=None).all()
        assert len(manual) == 1
        assert manual[0].label == "printer"
    finally:
        db.close()


def test_sync_skips_auto_row_matching_an_existing_manual_range():
    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id  # capture while session is still open (expire_on_commit)
    # Operator already manually added the exact gateway range before auto-sync existed.
    db.add(SubnetRange(subnet_id=subnet_id, start_ip="10.10.0.1", end_ip="10.10.0.1",
                        kind="gateway", label="manual gw", source=None))
    db.commit()
    db.close()

    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_ProviderWithGatewayAndExclusions()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        gw_rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id, start_ip="10.10.0.1", end_ip="10.10.0.1").all()
        assert len(gw_rows) == 1  # the manual one — no duplicate auto row created
        assert gw_rows[0].source is None
    finally:
        db.close()


class _FailingProvider:
    source = "msdhcp01"

    def get_scopes(self):
        return [DHCPScope(scope_id="10.10.0.0", name="lan", subnet_mask="/24",
                           start_range="10.10.0.10", end_range="10.10.0.200",
                           source=self.source)]

    def get_leases(self, scope_id):
        return []

    def get_scope_gateway(self, scope_id):
        raise RuntimeError("WinRM timed out")

    def get_scope_exclusions(self, scope_id):
        raise RuntimeError("WinRM timed out")


def test_sync_preserves_existing_auto_rows_on_fetch_failure():
    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id  # capture while session is still open (expire_on_commit)
    db.add(SubnetRange(subnet_id=subnet_id, start_ip="10.10.0.1", end_ip="10.10.0.1",
                        kind="gateway", source="msdhcp01"))
    db.commit()
    db.close()

    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_FailingProvider()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id, source="msdhcp01").all()
        assert len(rows) == 1
        assert rows[0].start_ip == "10.10.0.1"
    finally:
        db.close()
