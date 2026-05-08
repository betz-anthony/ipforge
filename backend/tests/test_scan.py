def test_scan_models_importable():
    from app.models.scan import ScanResult, Collision, CollisionType
    assert ScanResult.__tablename__ == "scan_results"
    assert Collision.__tablename__ == "collisions"
    assert CollisionType.active_but_available == "active_but_available"
    assert CollisionType.multi_dhcp_scope == "multi_dhcp_scope"
    assert CollisionType.hostname_mismatch == "hostname_mismatch"


def test_discovered_status_exists():
    from app.models.address import AddressStatus
    assert AddressStatus.discovered == "discovered"
