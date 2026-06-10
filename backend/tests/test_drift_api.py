from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.scan import DriftItem
from app.models.cache import CachedDHCPLease, CachedDNSRecord


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _subnet(db, cidr="10.0.0.0/24"):
    s = Subnet(name="N", cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _drift(db, ip, category, **kw):
    d = DriftItem(ip_address=ip, category=category, severity=kw.pop("severity", "warning"),
                  details=kw.pop("details", "{}"), detected_at=_now(), resolved=kw.pop("resolved", False), **kw)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


# ── list / stats ─────────────────────────────────────────────────────────────

def test_list_empty(client):
    assert client.get("/api/v1/drift").json() == []


def test_list_returns_unresolved_only(client, db):
    _drift(db, "10.0.0.1", "active_but_available")
    _drift(db, "10.0.0.2", "orphan_dns", resolved=True, resolved_at=_now())
    data = client.get("/api/v1/drift").json()
    assert [d["ip_address"] for d in data] == ["10.0.0.1"]


def test_list_filters_by_category(client, db):
    _drift(db, "10.0.0.1", "missing_dns")
    _drift(db, "10.0.0.2", "orphan_dns")
    data = client.get("/api/v1/drift", params={"category": "orphan_dns"}).json()
    assert [d["ip_address"] for d in data] == ["10.0.0.2"]


def test_stats(client, db):
    _drift(db, "10.0.0.1", "missing_dns", severity="warning")
    _drift(db, "10.0.0.2", "orphan_dns", severity="info")
    s = client.get("/api/v1/drift/stats").json()
    assert s["total"] == 2
    assert s["by_category"]["missing_dns"] == 1
    assert s["by_severity"]["info"] == 1


# ── scan trigger ──────────────────────────────────────────────────────────────

def test_scan_trigger(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.commit()
    assert client.post("/api/v1/drift/scan").status_code == 200
    assert db.query(DriftItem).filter_by(category="missing_dns").count() == 1


# ── resolve: carried categories ────────────────────────────────────────────────

def test_resolve_dismiss(client, db):
    d = _drift(db, "10.0.0.1", "active_but_available")
    r = client.post(f"/api/v1/drift/{d.id}/resolve")
    assert r.status_code == 200 and r.json()["resolved"] is True
    db.refresh(d)
    assert d.resolved is True


def test_resolve_404(client):
    assert client.post("/api/v1/drift/9999/resolve").status_code == 404


def test_resolve_active_but_available_sets_status(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.1", subnet_id=s.id, status=AddressStatus.available))
    db.commit()
    d = _drift(db, "10.0.0.1", "active_but_available")
    r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"new_status": "assigned"})
    assert r.status_code == 200
    addr = db.query(IPAddress).filter_by(address="10.0.0.1").first()
    assert addr.status == AddressStatus.assigned


def test_resolve_hostname_mismatch_calls_providers(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.10", subnet_id=s.id, status=AddressStatus.assigned, hostname="ws01"))
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.10", name="ws01", source="msdhcp", synced_at=_now()))
    db.add(CachedDNSRecord(name="ws01", record_type="A", value="10.0.0.10", zone="corp", ttl=300, source="msdns", synced_at=_now()))
    db.commit()
    d = _drift(db, "10.0.0.10", "hostname_mismatch")
    mock_dhcp = MagicMock(); mock_dhcp.source = "msdhcp"
    mock_dns = MagicMock(); mock_dns.source = "msdns"
    with patch("app.api.drift.get_dhcp_providers", return_value=[mock_dhcp]), \
         patch("app.api.drift.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"canonical_hostname": "server01"})
    assert r.status_code == 200
    mock_dhcp.update_reservation_name.assert_called_once_with("10.0.0.0", "10.0.0.10", "server01")
    mock_dns.update_record.assert_called_once()


def test_resolve_hostname_mismatch_rolls_back_on_dns_failure(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.10", subnet_id=s.id, status=AddressStatus.assigned, hostname="ws01"))
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.10", name="ws01", source="msdhcp", synced_at=_now()))
    db.add(CachedDNSRecord(name="ws01", record_type="A", value="10.0.0.10", zone="corp", ttl=300, source="msdns", synced_at=_now()))
    db.commit()
    d = _drift(db, "10.0.0.10", "hostname_mismatch")
    mock_dhcp = MagicMock(); mock_dhcp.source = "msdhcp"
    mock_dns = MagicMock(); mock_dns.source = "msdns"
    mock_dns.update_record.side_effect = RuntimeError("DNS down")
    with patch("app.api.drift.get_dhcp_providers", return_value=[mock_dhcp]), \
         patch("app.api.drift.get_dns_providers", return_value=[mock_dns]):
        r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"canonical_hostname": "server01"})
    assert r.status_code == 502
    assert mock_dhcp.update_reservation_name.call_count == 2  # forward + rollback
    db.refresh(d)
    assert d.resolved is False


# ── resolve: new categories ────────────────────────────────────────────────────

def test_resolve_orphan_dhcp_delete(client, db):
    _subnet(db)
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.8", name="x", source="msdhcp", synced_at=_now()))
    db.commit()
    d = _drift(db, "10.0.0.8", "orphan_dhcp", severity="info")
    mock = MagicMock(); mock.source = "msdhcp"
    with patch("app.api.drift.get_dhcp_providers", return_value=[mock]):
        r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"action": "delete"})
    assert r.status_code == 200
    mock.delete_reservation.assert_called_once_with("10.0.0.0", "10.0.0.8")


def test_resolve_orphan_dhcp_import(client, db):
    _subnet(db)
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.8", name="host", mac_address="aa:bb:cc:dd:ee:ff", source="msdhcp", synced_at=_now()))
    db.commit()
    d = _drift(db, "10.0.0.8", "orphan_dhcp", severity="info")
    r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"action": "import"})
    assert r.status_code == 200
    addr = db.query(IPAddress).filter_by(address="10.0.0.8").first()
    assert addr is not None and addr.hostname == "host"


def test_resolve_orphan_dns_import(client, db):
    _subnet(db)
    db.add(CachedDNSRecord(name="ghost", record_type="A", value="10.0.0.9", zone="x", source="msdns", synced_at=_now()))
    db.commit()
    d = _drift(db, "10.0.0.9", "orphan_dns", severity="info")
    r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"action": "import"})
    assert r.status_code == 200
    assert db.query(IPAddress).filter_by(address="10.0.0.9").first() is not None


def test_resolve_mac_mismatch_update_ipam(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, mac_address="aa:aa:aa:aa:aa:aa"))
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.5", mac_address="bb:bb:bb:bb:bb:bb", source="msdhcp", synced_at=_now()))
    db.commit()
    d = _drift(db, "10.0.0.5", "mac_mismatch")
    r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"action": "update_ipam"})
    assert r.status_code == 200
    addr = db.query(IPAddress).filter_by(address="10.0.0.5").first()
    assert addr.mac_address == "bb:bb:bb:bb:bb:bb"


# ── bulk ───────────────────────────────────────────────────────────────────────

def test_bulk_dismiss(client, db):
    d1 = _drift(db, "10.0.0.1", "missing_dns")
    d2 = _drift(db, "10.0.0.2", "missing_dns")
    r = client.post("/api/v1/drift/resolve-bulk", json={"ids": [d1.id, d2.id]})
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["resolved"]) == sorted([d1.id, d2.id])
    assert db.query(DriftItem).filter_by(resolved=False).count() == 0


def test_resolve_requires_operator(client_gr, db):
    d = _drift(db, "10.0.0.1", "missing_dns")
    assert client_gr.post(f"/api/v1/drift/{d.id}/resolve").status_code == 403


def test_resolve_orphan_dhcp_provider_error_returns_envelope(client, db):
    _subnet(db)
    db.add(CachedDHCPLease(scope_id="10.0.0.0", ip_address="10.0.0.8", name="x", source="msdhcp", synced_at=_now()))
    db.commit()
    d = _drift(db, "10.0.0.8", "orphan_dhcp", severity="info")
    mock = MagicMock(); mock.source = "msdhcp"
    mock.delete_reservation.side_effect = Exception("Connection timed out to dc01")
    with patch("app.api.drift.get_dhcp_providers", return_value=[mock]):
        r = client.post(f"/api/v1/drift/{d.id}/resolve", json={"action": "delete"})
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "provider_unreachable"
    assert detail["step"] == "dhcp" and detail["hint"]
