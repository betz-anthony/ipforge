from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.models.address import IPAddress, AddressStatus
from app.models.scan import ScanResult
from app.models.subnet import Subnet
from app.models.cache import SyncStatus, CachedDHCPLease, CachedDNSRecord
from app.models.scan import DriftItem, DriftCategory
from app.drift import detect_drift
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
    from app.models.scan import ScanResult, DriftItem, DriftCategory
    assert ScanResult.__tablename__ == "scan_results"
    assert DriftItem.__tablename__ == "drift_items"
    assert DriftCategory.active_but_available == "active_but_available"
    assert DriftCategory.multi_dhcp_scope == "multi_dhcp_scope"
    assert DriftCategory.hostname_mismatch == "hostname_mismatch"


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
    from app.core.time import utcnow as _utcnow
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

    detect_drift(db, subnet.id)

    c = db.query(DriftItem).filter_by(category=DriftCategory.active_but_available.value).first()
    assert c is not None
    assert c.ip_address == "10.0.0.1"
    assert c.resolved is False


def test_collision_not_created_for_assigned_ip(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")
    addr = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.assigned)
    db.add(addr)
    _add_scan_result(db, subnet.id, "10.0.0.1", reachable=True)

    detect_drift(db, subnet.id)

    assert db.query(DriftItem).filter_by(category=DriftCategory.active_but_available.value).count() == 0


def test_collision_auto_resolves_when_condition_clears(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")
    addr = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.available)
    db.add(addr)
    _add_scan_result(db, subnet.id, "10.0.0.1", reachable=True, latency_ms=1.0)
    detect_drift(db, subnet.id)

    c = db.query(DriftItem).filter_by(category=DriftCategory.active_but_available.value).first()
    assert c is not None and c.resolved is False

    # Condition clears: the address is now assigned, so it is no longer a collision.
    addr.status = AddressStatus.assigned
    db.commit()
    detect_drift(db, subnet.id)

    db.refresh(c)
    assert c.resolved is True
    assert c.resolved_at is not None


def test_collision_multi_dhcp_scope(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    from app.core.time import utcnow as _utcnow
    now = _utcnow()
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.5",
                           source="msdhcp", synced_at=now))
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.5",
                           source="pihole", synced_at=now))
    _add_scan_result(db, subnet.id, "10.0.0.5")

    detect_drift(db, subnet.id)

    c = db.query(DriftItem).filter_by(category=DriftCategory.multi_dhcp_scope.value).first()
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
    from app.core.time import utcnow as _utcnow
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.10",
                           name="workstation01", source="msdhcp", synced_at=_utcnow()))
    _add_scan_result(db, subnet.id, "10.0.0.10")

    detect_drift(db, subnet.id)

    c = db.query(DriftItem).filter_by(category=DriftCategory.hostname_mismatch.value).first()
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
    from app.core.time import utcnow as _utcnow
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.10",
                           name="SERVER01", source="msdhcp", synced_at=_utcnow()))
    _add_scan_result(db, subnet.id, "10.0.0.10")

    detect_drift(db, subnet.id)

    assert db.query(DriftItem).filter_by(category=DriftCategory.hostname_mismatch.value).count() == 0


def test_collision_reopen_on_redetection(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/30")
    addr = IPAddress(address="10.0.0.1", subnet_id=subnet.id, status=AddressStatus.available)
    db.add(addr)
    from app.core.time import utcnow as _utcnow
    now = _utcnow()
    existing = DriftItem(
        ip_address="10.0.0.1",
        category=DriftCategory.active_but_available.value,
        details="{}",
        detected_at=now,
        resolved=True,
        resolved_at=now,
    )
    db.add(existing)
    _add_scan_result(db, subnet.id, "10.0.0.1", reachable=True)

    detect_drift(db, subnet.id)

    db.refresh(existing)
    assert existing.resolved is False
    assert existing.resolved_at is None


def test_collision_hostname_mismatch_via_dns(db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    addr = IPAddress(address="10.0.0.10", subnet_id=subnet.id,
                     status=AddressStatus.assigned, hostname="server01")
    db.add(addr)
    from app.core.time import utcnow as _utcnow
    db.add(CachedDNSRecord(name="webserver01", record_type="A",
                           value="10.0.0.10", zone="example.com",
                           ttl=300, source="msdns", synced_at=_utcnow()))
    _add_scan_result(db, subnet.id, "10.0.0.10")

    detect_drift(db, subnet.id)

    c = db.query(DriftItem).filter_by(category=DriftCategory.hostname_mismatch.value).first()
    assert c is not None
    import json
    details = json.loads(c.details)
    assert details["dns"] == "webserver01"


def test_scan_all_eligible_includes_small_ipv6(db):
    _make_subnet(db, cidr="10.0.0.0/24",   name="v4",         ip_version=4)
    _make_subnet(db, cidr="2001:db8::/120", name="v6-small",   ip_version=6)
    _make_subnet(db, cidr="2001:db8::/32",  name="v6-large",   ip_version=6)

    scanned_ids = []

    def _fake_scan(subnet_id, _db=None):
        scanned_ids.append(subnet_id)

    with patch("app.scan.scan_subnet", side_effect=_fake_scan):
        from app.scan import scan_all_eligible
        scan_all_eligible(_db=db)

    v4       = db.query(Subnet).filter_by(name="v4").first()
    v6_small = db.query(Subnet).filter_by(name="v6-small").first()
    v6_large = db.query(Subnet).filter_by(name="v6-large").first()
    assert v4.id       in scanned_ids       # IPv4 /24 — eligible
    assert v6_small.id in scanned_ids       # IPv6 /120 — eligible
    assert v6_large.id not in scanned_ids   # IPv6 /32 — too large, needs range


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
        r = client.post(f"/api/v1/scan/subnets/{subnet.id}")

    assert r.status_code == 200
    assert r.json()["status"] == "triggered"


def test_trigger_scan_404_for_missing_subnet(client):
    r = client.post("/api/v1/scan/subnets/9999")
    assert r.status_code == 404


def test_get_scan_status_never(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    r = client.get(f"/api/v1/scan/subnets/{subnet.id}")
    assert r.status_code == 200
    assert r.json()["status"] == "never"
    assert r.json()["results"] == []


def test_get_scan_status_with_results(client, db):
    subnet = _make_subnet(db, cidr="10.0.0.0/24")
    from app.core.time import utcnow as _utcnow
    now = _utcnow()
    db.add(ScanResult(subnet_id=subnet.id, ip_address="10.0.0.1",
                      reachable=True, latency_ms=1.5, scanned_at=now))
    db.add(SyncStatus(key=f"scan:{subnet.id}", synced_at=now, status="ok"))
    db.commit()

    r = client.get(f"/api/v1/scan/subnets/{subnet.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert len(data["results"]) == 1
    assert data["results"][0]["ip"] == "10.0.0.1"
    assert data["results"][0]["reachable"] is True


# ── IPv6 scan tests ──────────────────────────────────────────────────────────

def test_get_host_list_ipv6_auto_scan_ok(db):
    subnet = _make_subnet(db, cidr="2001:db8::/120", ip_version=6)
    from app.scan import _get_host_list
    hosts = _get_host_list(subnet, None, None)
    assert len(hosts) == 255  # /120 has 256 addresses; IPv6 hosts() excludes only the subnet-router anycast (first)
    assert all(":" in h for h in hosts)


def test_get_host_list_ipv6_too_large_requires_range(db):
    subnet = _make_subnet(db, cidr="2001:db8::/64", ip_version=6)
    from app.scan import _get_host_list
    import pytest
    with pytest.raises(ValueError, match="start_ip and end_ip"):
        _get_host_list(subnet, None, None)


def test_get_host_list_ipv6_with_explicit_range(db):
    subnet = _make_subnet(db, cidr="2001:db8::/64", ip_version=6)
    from app.scan import _get_host_list
    hosts = _get_host_list(subnet, "2001:db8::1", "2001:db8::5")
    assert hosts == [
        "2001:db8::1", "2001:db8::2", "2001:db8::3", "2001:db8::4", "2001:db8::5",
    ]


def test_scan_subnet_ipv6(db):
    subnet = _make_subnet(db, cidr="2001:db8::/120", ip_version=6)
    mock_results = {
        "2001:db8::1": {"ip": "2001:db8::1", "reachable": True,  "latency_ms": 0.5},
        "2001:db8::2": {"ip": "2001:db8::2", "reachable": False, "latency_ms": None},
    }
    with patch("app.scan._scan_host", side_effect=_mock_scan(mock_results)):
        from app.scan import scan_subnet
        scan_subnet(subnet.id, start_ip="2001:db8::1", end_ip="2001:db8::2", _db=db)

    results = db.query(ScanResult).filter_by(subnet_id=subnet.id).all()
    assert len(results) == 2
    reachable = [r for r in results if r.reachable]
    assert len(reachable) == 1
    assert reachable[0].ip_address == "2001:db8::1"


def test_scan_host_uses_ping6_for_ipv6(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        m = MagicMock()
        m.stdout = "1 packets transmitted, 0 received, 100% packet loss"
        m.stderr = ""
        return m

    monkeypatch.setattr("subprocess.run", fake_run)
    import platform
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    from app.scan import _scan_host
    _scan_host("2001:db8::1")
    assert captured["cmd"][0] == "ping6"


def test_scan_host_uses_ping_dash6_on_darwin(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        m = MagicMock()
        m.stdout = "1 packets transmitted, 0 received, 100% packet loss"
        m.stderr = ""
        return m

    monkeypatch.setattr("subprocess.run", fake_run)
    import platform
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    from app.scan import _scan_host
    _scan_host("2001:db8::1")
    assert captured["cmd"][0] == "ping"
    assert "-6" in captured["cmd"]


def test_scan_host_ipv4_unchanged_on_linux(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        m = MagicMock()
        m.stdout = "1 packets transmitted, 0 received, 100% packet loss"
        m.stderr = ""
        return m

    monkeypatch.setattr("subprocess.run", fake_run)
    import platform
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    from app.scan import _scan_host
    _scan_host("10.0.0.1")
    assert captured["cmd"][0] == "ping"
    assert "ping6" not in captured["cmd"][0]
