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


def test_sync_resolves_most_specific_subnet_not_first_match():
    """A scope's start_range can fall inside both a supernet and a child
    subnet (subnet hierarchy). The child (longest-prefix / most specific)
    match must win, regardless of insertion order — a naive first-match scan
    would typically pick whichever subnet was created first (often the
    supernet)."""
    db = TestingSessionLocal()
    supernet = Subnet(name="supernet", cidr="10.0.0.0/16", ip_version=4)
    child = Subnet(name="child", cidr="10.0.1.0/24", ip_version=4)
    db.add(supernet)
    db.add(child)
    db.commit()
    supernet_id, child_id = supernet.id, child.id  # capture while session is open
    db.close()

    class _Provider:
        source = "msdhcp01"

        def get_scopes(self):
            return [DHCPScope(scope_id="10.0.1.0", name="lan", subnet_mask="/24",
                               start_range="10.0.1.10", end_range="10.0.1.200",
                               source=self.source)]

        def get_leases(self, scope_id):
            return []

        def get_scope_gateway(self, scope_id):
            return "10.0.1.1"

        def get_scope_exclusions(self, scope_id):
            return []

    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_Provider()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        child_rows = db.query(SubnetRange).filter_by(subnet_id=child_id, source="msdhcp01").all()
        supernet_rows = db.query(SubnetRange).filter_by(subnet_id=supernet_id, source="msdhcp01").all()
        assert len(child_rows) == 1
        assert child_rows[0].start_ip == "10.0.1.1"
        assert supernet_rows == []
    finally:
        db.close()


class _ProviderTwoScopesSameSubnet:
    """Two scopes from one provider, both resolving to the same subnet
    (e.g. split pools represented as separate DHCP scopes). Only scope-a
    reports a gateway, so the aggregation-order question (which scope's
    gateway "wins") doesn't matter for this test — the point is that both
    scopes' exclusions must survive, not that scope-b's write clobbers
    scope-a's."""
    source = "msdhcp01"

    def get_scopes(self):
        return [
            DHCPScope(scope_id="scope-a", name="lan-a", subnet_mask="/24",
                       start_range="10.10.0.10", end_range="10.10.0.100",
                       source=self.source),
            DHCPScope(scope_id="scope-b", name="lan-b", subnet_mask="/24",
                       start_range="10.10.0.150", end_range="10.10.0.200",
                       source=self.source),
        ]

    def get_leases(self, scope_id):
        return []

    def get_scope_gateway(self, scope_id):
        return "10.10.0.1" if scope_id == "scope-a" else None

    def get_scope_exclusions(self, scope_id):
        if scope_id == "scope-a":
            return [("10.10.0.2", "10.10.0.9")]
        return [("10.10.0.240", "10.10.0.250")]


def test_sync_aggregates_multiple_scopes_for_same_subnet_without_clobbering():
    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id  # capture while session is still open
    db.close()

    from app import sync as sync_module
    with patch("app.providers.registry.get_dhcp_providers", return_value=[_ProviderTwoScopesSameSubnet()]), \
         patch("app.providers.registry.get_dns_providers", return_value=[]), \
         patch("app.sync.SessionLocal", side_effect=_make_session):
        sync_module.sync_dhcp()

    db = TestingSessionLocal()
    try:
        rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id, source="msdhcp01").all()
        by_kind = {(r.kind, r.start_ip, r.end_ip) for r in rows}
        # Both scopes' exclusions present — the second scope's write did not
        # wipe out the first's.
        assert ("gateway", "10.10.0.1", "10.10.0.1") in by_kind
        assert ("excluded", "10.10.0.2", "10.10.0.9") in by_kind
        assert ("excluded", "10.10.0.240", "10.10.0.250") in by_kind
        assert len(rows) == 3
    finally:
        db.close()


def test_write_reserved_ranges_drops_malformed_gateway_and_logs_warning(caplog):
    """A malformed provider value (e.g. Pi-hole's raw, unvalidated 'router'
    config string) must not reach SubnetRange.start_ip unparsed — downstream
    readers (subnet_map, reserved_ip_set, allocation candidate search) assume
    every row parses cleanly as an IP."""
    from app import sync as sync_module

    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id
    db.close()

    db = TestingSessionLocal()
    try:
        with caplog.at_level("WARNING"):
            sync_module._write_reserved_ranges(db, subnet_id, "pihole01", "not-an-ip", [])
        assert any("not-an-ip" in r.message for r in caplog.records)
        rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id, source="pihole01").all()
        assert rows == []
    finally:
        db.close()


def test_write_reserved_ranges_drops_out_of_subnet_exclusion_and_keeps_valid_ones():
    """A mix of one bad exclusion (outside the subnet CIDR) and one good one —
    the bad one is dropped, the good one and the gateway still get written
    exactly as before this fix."""
    from app import sync as sync_module

    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id
    db.close()

    db = TestingSessionLocal()
    try:
        sync_module._write_reserved_ranges(
            db, subnet_id, "msdhcp01", "10.10.0.1",
            [("10.10.0.2", "10.10.0.9"), ("192.168.99.1", "192.168.99.5")],
        )
        rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id, source="msdhcp01").all()
        by_kind = {(r.kind, r.start_ip, r.end_ip) for r in rows}
        assert by_kind == {
            ("gateway", "10.10.0.1", "10.10.0.1"),
            ("excluded", "10.10.0.2", "10.10.0.9"),
        }
    finally:
        db.close()


def test_write_reserved_ranges_drops_version_mismatch():
    """A v6 value against a v4 subnet is dropped, not written."""
    from app import sync as sync_module

    db = TestingSessionLocal()
    subnet = _seed_subnet(db)
    subnet_id = subnet.id
    db.close()

    db = TestingSessionLocal()
    try:
        sync_module._write_reserved_ranges(db, subnet_id, "msdhcp01", "fe80::1", [])
        rows = db.query(SubnetRange).filter_by(subnet_id=subnet_id, source="msdhcp01").all()
        assert rows == []
    finally:
        db.close()
