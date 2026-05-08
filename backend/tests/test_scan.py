from unittest.mock import patch
from datetime import datetime, timezone

from app.models.address import IPAddress, AddressStatus
from app.models.scan import ScanResult
from app.models.subnet import Subnet
from app.models.cache import SyncStatus, CachedDHCPLease, CachedDNSRecord
from app.models.scan import Collision, CollisionType
from app.scan import _detect_collisions
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


def _add_scan_result(db, subnet_id, ip, reachable=True, latency_ms=1.0):
    from app.scan import _utcnow
    row = ScanResult(
        subnet_id=subnet_id, ip_address=ip,
        reachable=reachable, latency_ms=latency_ms,
        scanned_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def test_collision_active_but_available(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")
    addr = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.available)
    db.add(addr)
    _add_scan_result(db, subnet.id, "10.0.0.1", reachable=True, latency_ms=1.2)

    _detect_collisions(db, subnet.id)

    c = db.query(Collision).first()
    assert c is not None
    assert c.collision_type == CollisionType.active_but_available
    assert c.ip_address == "10.0.0.1"
    assert c.resolved is False


def test_collision_not_created_for_assigned_ip(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")
    addr = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.assigned)
    db.add(addr)
    _add_scan_result(db, subnet.id, "10.0.0.1", reachable=True)

    _detect_collisions(db, subnet.id)

    assert db.query(Collision).count() == 0


def test_collision_multi_dhcp_scope(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    from app.scan import _utcnow
    now = _utcnow()
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.5",
                           source="msdhcp", synced_at=now))
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.5",
                           source="pihole", synced_at=now))
    _add_scan_result(db, subnet.id, "10.0.0.5")

    _detect_collisions(db, subnet.id)

    c = db.query(Collision).filter_by(collision_type=CollisionType.multi_dhcp_scope).first()
    assert c is not None
    assert c.ip_address == "10.0.0.5"
    import json
    details = json.loads(c.details)
    assert set(details["sources"]) == {"msdhcp", "pihole"}


def test_collision_hostname_mismatch(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    addr = IPAddress(address="10.0.0.10", subnet_id=subnet.id,
                     status=AddressStatus.assigned, hostname="server01")
    db.add(addr)
    from app.scan import _utcnow
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.10",
                           name="workstation01", source="msdhcp", synced_at=_utcnow()))
    _add_scan_result(db, subnet.id, "10.0.0.10")

    _detect_collisions(db, subnet.id)

    c = db.query(Collision).filter_by(collision_type=CollisionType.hostname_mismatch).first()
    assert c is not None
    import json
    details = json.loads(c.details)
    assert details["ipam"] == "server01"
    assert details["dhcp"] == "workstation01"


def test_collision_no_mismatch_when_names_match(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    addr = IPAddress(address="10.0.0.10", subnet_id=subnet.id,
                     status=AddressStatus.assigned, hostname="server01")
    db.add(addr)
    from app.scan import _utcnow
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.10",
                           name="SERVER01", source="msdhcp", synced_at=_utcnow()))
    _add_scan_result(db, subnet.id, "10.0.0.10")

    _detect_collisions(db, subnet.id)

    assert db.query(Collision).count() == 0


def test_collision_reopen_on_redetection(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")
    addr = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.available)
    db.add(addr)
    from app.scan import _utcnow
    now = _utcnow()
    existing = Collision(
        ip_address="10.0.0.1",
        collision_type=CollisionType.active_but_available,
        details="{}",
        detected_at=now,
        resolved=True,
        resolved_at=now,
    )
    db.add(existing)
    _add_scan_result(db, subnet.id, "10.0.0.1", reachable=True)

    _detect_collisions(db, subnet.id)

    db.refresh(existing)
    assert existing.resolved is False
    assert existing.resolved_at is None
