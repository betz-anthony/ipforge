from unittest.mock import patch
from datetime import datetime, timezone

from app.models.address import IPAddress, AddressStatus
from app.models.scan import ScanResult
from app.models.subnet import Subnet
from app.models.cache import SyncStatus
from app.utils import ip_in_cidr


def test_ip_in_cidr_match():
    assert ip_in_cidr("10.0.0.5", "10.0.0.0/24") is True


def test_ip_in_cidr_boundary_low():
    assert ip_in_cidr("10.0.0.1", "10.0.0.0/24") is True


def test_ip_in_cidr_boundary_high():
    assert ip_in_cidr("10.0.0.254", "10.0.0.0/24") is True


def test_ip_in_cidr_miss():
    assert ip_in_cidr("192.168.1.1", "10.0.0.0/24") is False


def test_ip_in_cidr_bad_ip():
    assert ip_in_cidr("notanip", "10.0.0.0/24") is False


def test_ip_in_cidr_bad_cidr():
    assert ip_in_cidr("10.0.0.1", "notacidr") is False


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


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_subnet(db, cidr="10.0.0.0/30", name="Test", ip_version=4):
    s = Subnet(name=name, cidr=cidr, ip_version=ip_version)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mock_scan(results: dict):
    """Returns a side_effect callable that looks up ip in results dict."""
    def _side(ip):
        return results.get(ip, {"ip": ip, "reachable": False, "latency_ms": None})
    return _side


def test_scan_subnet_creates_scan_results(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")  # hosts: 10.0.0.1, 10.0.0.2

    mock_results = {
        "10.0.0.1": {"ip": "10.0.0.1", "reachable": True,  "latency_ms": 1.5},
        "10.0.0.2": {"ip": "10.0.0.2", "reachable": False, "latency_ms": None},
    }

    with patch("app.scan._scan_host", side_effect=_mock_scan(mock_results)):
        from app.scan import scan_subnet
        scan_subnet(subnet.id, _db=db)

    results = db.query(ScanResult).all()
    assert len(results) == 2
    reachable = next(r for r in results if r.ip_address == "10.0.0.1")
    assert reachable.reachable is True
    assert reachable.latency_ms == 1.5
    assert reachable.subnet_id == subnet.id


def test_scan_subnet_creates_discovered_ipaddress(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")

    mock_results = {
        "10.0.0.1": {"ip": "10.0.0.1", "reachable": True,  "latency_ms": 2.0},
        "10.0.0.2": {"ip": "10.0.0.2", "reachable": False, "latency_ms": None},
    }
    with patch("app.scan._scan_host", side_effect=_mock_scan(mock_results)):
        from app.scan import scan_subnet
        scan_subnet(subnet.id, _db=db)

    addr = db.query(IPAddress).filter_by(address="10.0.0.1").first()
    assert addr is not None
    assert addr.status == AddressStatus.discovered
    assert addr.subnet_id == subnet.id
    assert db.query(IPAddress).filter_by(address="10.0.0.2").count() == 0


def test_scan_subnet_does_not_duplicate_tracked_ip(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")
    existing = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.assigned)
    db.add(existing)
    db.commit()

    mock_results = {
        "10.0.0.1": {"ip": "10.0.0.1", "reachable": True,  "latency_ms": 1.0},
        "10.0.0.2": {"ip": "10.0.0.2", "reachable": False, "latency_ms": None},
    }
    with patch("app.scan._scan_host", side_effect=_mock_scan(mock_results)):
        from app.scan import scan_subnet
        scan_subnet(subnet.id, _db=db)

    assert db.query(IPAddress).filter_by(address="10.0.0.1").count() == 1


def test_scan_subnet_sets_sync_status_ok(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")

    mock_results = {
        "10.0.0.1": {"ip": "10.0.0.1", "reachable": False, "latency_ms": None},
        "10.0.0.2": {"ip": "10.0.0.2", "reachable": False, "latency_ms": None},
    }
    with patch("app.scan._scan_host", side_effect=_mock_scan(mock_results)):
        from app.scan import scan_subnet
        scan_subnet(subnet.id, _db=db)

    key = f"scan:{subnet.id}"
    status = db.get(SyncStatus, key)
    assert status is not None
    assert status.status == "ok"


def test_scan_subnet_large_cidr_requires_range(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/16")

    from app.scan import scan_subnet
    # No start_ip/end_ip provided for a /16 — should set status=error, not crash caller
    scan_subnet(subnet.id, _db=db)

    key = f"scan:{subnet.id}"
    status = db.get(SyncStatus, key)
    assert status.status == "error"
    assert "start_ip" in status.error.lower() or "larger" in status.error.lower()


def test_scan_subnet_with_range(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/16")

    mock_results = {
        "10.0.1.1": {"ip": "10.0.1.1", "reachable": True,  "latency_ms": 0.9},
        "10.0.1.2": {"ip": "10.0.1.2", "reachable": False, "latency_ms": None},
    }

    with patch("app.scan._scan_host", side_effect=_mock_scan(mock_results)):
        from app.scan import scan_subnet
        scan_subnet(subnet.id, start_ip="10.0.1.1", end_ip="10.0.1.2", _db=db)

    assert db.query(ScanResult).count() == 2


def test_get_host_list_caps_at_1024(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/16")
    from app.scan import _get_host_list
    hosts = _get_host_list(subnet, "10.0.0.1", "10.0.10.254")
    assert len(hosts) == 1024
