from unittest.mock import patch, MagicMock
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

    c = db.query(Collision).filter_by(collision_type=CollisionType.active_but_available).first()
    assert c is not None
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


def test_collision_hostname_mismatch_via_dns(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    addr = IPAddress(address="10.0.0.10", subnet_id=subnet.id,
                     status=AddressStatus.assigned, hostname="server01")
    db.add(addr)
    from app.scan import _utcnow
    db.add(CachedDNSRecord(name="webserver01", record_type="A",
                           value="10.0.0.10", zone="example.com",
                           ttl=300, source="msdns", synced_at=_utcnow()))
    _add_scan_result(db, subnet.id, "10.0.0.10")

    _detect_collisions(db, subnet.id)

    c = db.query(Collision).filter_by(collision_type=CollisionType.hostname_mismatch).first()
    assert c is not None
    import json
    details = json.loads(c.details)
    assert details["dns"] == "webserver01"


def test_scan_all_eligible_skips_ipv6(db):
    _make_subnet(db, cidr="10.0.0.0/24", name="v4", ip_version=4)
    _make_subnet(db, cidr="2001:db8::/32",  name="v6", ip_version=6)

    scanned_ids = []

    def _fake_scan(subnet_id, _db=None):
        scanned_ids.append(subnet_id)

    with patch("app.scan.scan_subnet", side_effect=_fake_scan):
        from app.scan import scan_all_eligible
        scan_all_eligible(_db=db)

    v4 = db.query(Subnet).filter_by(name="v4").first()
    v6 = db.query(Subnet).filter_by(name="v6").first()
    assert v4.id in scanned_ids
    assert v6.id not in scanned_ids


def test_scan_all_eligible_skips_large_subnets(db):
    _make_subnet(db, cidr="10.0.0.0/24", name="small", ip_version=4)
    _make_subnet(db, cidr="10.1.0.0/16", name="large", ip_version=4)

    scanned_ids = []

    def _fake_scan(subnet_id, _db=None):
        scanned_ids.append(subnet_id)

    with patch("app.scan.scan_subnet", side_effect=_fake_scan):
        from app.scan import scan_all_eligible
        scan_all_eligible(_db=db)

    small = db.query(Subnet).filter_by(name="small").first()
    large = db.query(Subnet).filter_by(name="large").first()
    assert small.id in scanned_ids
    assert large.id not in scanned_ids


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

def test_trigger_scan_returns_triggered(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")

    with patch("app.api.scan.threading.Thread") as mock_thread:
        mock_thread.return_value.start = lambda: None
        r = client.post(f"/api/scan/subnets/{subnet.id}")

    assert r.status_code == 200
    assert r.json()["status"] == "triggered"


def test_trigger_scan_404_for_missing_subnet(client):
    r = client.post("/api/scan/subnets/9999")
    assert r.status_code == 404


def test_get_scan_status_never(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    r = client.get(f"/api/scan/subnets/{subnet.id}")
    assert r.status_code == 200
    assert r.json()["status"] == "never"
    assert r.json()["results"] == []


def test_get_scan_status_with_results(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    from app.scan import _utcnow
    now = _utcnow()
    db.add(ScanResult(subnet_id=subnet.id, ip_address="10.0.0.1",
                      reachable=True, latency_ms=1.5, scanned_at=now))
    db.add(SyncStatus(key=f"scan:{subnet.id}", synced_at=now, status="ok"))
    db.commit()

    r = client.get(f"/api/scan/subnets/{subnet.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert len(data["results"]) == 1
    assert data["results"][0]["ip"] == "10.0.0.1"
    assert data["results"][0]["reachable"] is True


def test_list_collisions_empty(client):
    r = client.get("/api/scan/collisions")
    assert r.status_code == 200
    assert r.json() == []


def test_list_collisions_returns_unresolved(client, db):
    from app.scan import _utcnow
    now = _utcnow()
    db.add(Collision(ip_address="10.0.0.1", collision_type="active_but_available",
                     details='{"ipam_status":"available"}', detected_at=now, resolved=False))
    db.add(Collision(ip_address="10.0.0.2", collision_type="multi_dhcp_scope",
                     details='{"sources":["a","b"]}', detected_at=now,
                     resolved=True, resolved_at=now))
    db.commit()

    r = client.get("/api/scan/collisions")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["ip_address"] == "10.0.0.1"


def test_resolve_collision(client, db):
    from app.scan import _utcnow
    c = Collision(ip_address="10.0.0.1", collision_type="active_but_available",
                  details="{}", detected_at=_utcnow(), resolved=False)
    db.add(c)
    db.commit()
    db.refresh(c)

    r = client.put(f"/api/scan/collisions/{c.id}/resolve")
    assert r.status_code == 200
    assert r.json()["resolved"] is True

    db.refresh(c)
    assert c.resolved is True
    assert c.resolved_at is not None


def test_resolve_collision_404(client):
    r = client.put("/api/scan/collisions/9999/resolve")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Guided resolve tests
# ---------------------------------------------------------------------------


def test_resolve_active_but_available_updates_ipam_status(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    addr = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.available)
    db.add(addr)
    c = Collision(
        ip_address="10.0.0.1", collision_type="active_but_available",
        details='{"ipam_status":"available","latency_ms":1.2}',
        detected_at=_now(), resolved=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    db.refresh(addr)

    r = client.put(f"/api/scan/collisions/{c.id}/resolve",
                   json={"new_status": "assigned"})
    assert r.status_code == 200
    assert r.json()["resolved"] is True

    db.refresh(addr)
    assert addr.status == AddressStatus.assigned
    db.refresh(c)
    assert c.resolved is True


def test_resolve_active_but_available_invalid_status_returns_422(client, db):
    c = Collision(
        ip_address="10.0.0.99", collision_type="active_but_available",
        details="{}", detected_at=_now(), resolved=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    r = client.put(f"/api/scan/collisions/{c.id}/resolve",
                   json={"new_status": "bogus_value"})
    assert r.status_code == 422


def test_resolve_hostname_mismatch_calls_providers(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    addr = IPAddress(address="10.0.0.10", subnet_id=subnet.id,
                     status=AddressStatus.assigned, hostname="workstation01")
    db.add(addr)
    db.add(CachedDHCPLease(
        scope_id="10.0.0.0", ip_address="10.0.0.10",
        name="workstation01", source="msdhcp",
        mac_address="aa:bb:cc:dd:ee:ff", synced_at=_now(),
    ))
    db.add(CachedDNSRecord(
        name="workstation01", record_type="A", value="10.0.0.10",
        zone="corp.local", ttl=300, source="msdns", synced_at=_now(),
    ))
    c = Collision(
        ip_address="10.0.0.10", collision_type="hostname_mismatch",
        details='{"ipam":"workstation01","dhcp":"workstation01","dns":"oldname"}',
        detected_at=_now(), resolved=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    mock_dhcp = MagicMock()
    mock_dhcp.source = "msdhcp"
    mock_dns = MagicMock()
    mock_dns.source = "msdns"

    with patch("app.api.scan.get_dhcp_providers", return_value=[mock_dhcp]), \
         patch("app.api.scan.get_dns_providers",  return_value=[mock_dns]):
        r = client.put(f"/api/scan/collisions/{c.id}/resolve",
                       json={"canonical_hostname": "server01"})

    assert r.status_code == 200
    mock_dhcp.update_reservation_name.assert_called_once_with("10.0.0.0", "10.0.0.10", "server01")
    mock_dns.update_record.assert_called_once()
    dns_new = mock_dns.update_record.call_args[0][1]
    assert dns_new.name == "server01"
    db.refresh(addr)
    assert addr.hostname == "server01"
    db.refresh(c)
    assert c.resolved is True


def test_resolve_hostname_mismatch_rolls_back_dhcp_on_dns_failure(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    addr = IPAddress(address="10.0.0.10", subnet_id=subnet.id,
                     status=AddressStatus.assigned, hostname="workstation01")
    db.add(addr)
    db.add(CachedDHCPLease(
        scope_id="10.0.0.0", ip_address="10.0.0.10",
        name="workstation01", source="msdhcp", synced_at=_now(),
    ))
    db.add(CachedDNSRecord(
        name="workstation01", record_type="A", value="10.0.0.10",
        zone="corp.local", ttl=300, source="msdns", synced_at=_now(),
    ))
    c = Collision(
        ip_address="10.0.0.10", collision_type="hostname_mismatch",
        details='{"ipam":"workstation01","dhcp":"workstation01","dns":"workstation01"}',
        detected_at=_now(), resolved=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    mock_dhcp = MagicMock()
    mock_dhcp.source = "msdhcp"
    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    mock_dns.update_record.side_effect = RuntimeError("DNS unreachable")

    with patch("app.api.scan.get_dhcp_providers", return_value=[mock_dhcp]), \
         patch("app.api.scan.get_dns_providers",  return_value=[mock_dns]):
        r = client.put(f"/api/scan/collisions/{c.id}/resolve",
                       json={"canonical_hostname": "server01"})

    assert r.status_code == 502
    # DHCP called once forward, once rollback
    assert mock_dhcp.update_reservation_name.call_count == 2
    rollback_call = mock_dhcp.update_reservation_name.call_args_list[1]
    assert rollback_call[0][2] == "workstation01"  # original hostname restored
    db.refresh(c)
    assert c.resolved is False


def test_resolve_multi_dhcp_scope_deletes_selected_source(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    db.add(CachedDHCPLease(
        scope_id="10.0.0.0", ip_address="10.0.0.5",
        mac_address="aa:bb:cc:dd:ee:01", name="device1",
        source="msdhcp", synced_at=_now(),
    ))
    db.add(CachedDHCPLease(
        scope_id="10.0.0.0", ip_address="10.0.0.5",
        mac_address="aa:bb:cc:dd:ee:02", name="device1",
        source="pihole", synced_at=_now(),
    ))
    c = Collision(
        ip_address="10.0.0.5", collision_type="multi_dhcp_scope",
        details='{"sources":["msdhcp","pihole"]}',
        detected_at=_now(), resolved=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    mock_dhcp1 = MagicMock()
    mock_dhcp1.source = "msdhcp"
    mock_dhcp2 = MagicMock()
    mock_dhcp2.source = "pihole"

    with patch("app.api.scan.get_dhcp_providers", return_value=[mock_dhcp1, mock_dhcp2]):
        r = client.put(f"/api/scan/collisions/{c.id}/resolve",
                       json={"sources_to_remove": ["pihole"]})

    assert r.status_code == 200
    mock_dhcp1.delete_reservation.assert_not_called()
    mock_dhcp2.delete_reservation.assert_called_once_with("10.0.0.0", "10.0.0.5")
    db.refresh(c)
    assert c.resolved is True


def test_resolve_multi_dhcp_scope_rolls_back_on_failure(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    db.add(CachedDHCPLease(
        scope_id="10.0.0.0", ip_address="10.0.0.5",
        mac_address="aa:bb:cc:dd:ee:01", name="device1",
        source="msdhcp", synced_at=_now(),
    ))
    db.add(CachedDHCPLease(
        scope_id="10.0.0.0", ip_address="10.0.0.5",
        mac_address="aa:bb:cc:dd:ee:02", name="device1",
        source="pihole", synced_at=_now(),
    ))
    c = Collision(
        ip_address="10.0.0.5", collision_type="multi_dhcp_scope",
        details='{"sources":["msdhcp","pihole"]}',
        detected_at=_now(), resolved=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    mock_dhcp1 = MagicMock()
    mock_dhcp1.source = "msdhcp"
    mock_dhcp2 = MagicMock()
    mock_dhcp2.source = "pihole"
    mock_dhcp2.delete_reservation.side_effect = RuntimeError("DHCP unreachable")

    with patch("app.api.scan.get_dhcp_providers", return_value=[mock_dhcp1, mock_dhcp2]):
        r = client.put(f"/api/scan/collisions/{c.id}/resolve",
                       json={"sources_to_remove": ["msdhcp", "pihole"]})

    assert r.status_code == 502
    # msdhcp deleted, pihole failed → msdhcp re-added via add_reservation
    mock_dhcp1.delete_reservation.assert_called_once()
    mock_dhcp1.add_reservation.assert_called_once()
    db.refresh(c)
    assert c.resolved is False
