from datetime import datetime, timedelta

from app.drift import detect_drift
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.scan import DriftItem, DriftCategory, ScanResult
from app.models.cache import CachedDNSRecord, CachedDHCPLease
from app.core.time import utcnow


def _subnet(db, cidr="10.0.0.0/24"):
    s = Subnet(name="N", cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    return s


def _cats(db):
    return {(d.ip_address, d.category) for d in db.query(DriftItem).filter_by(resolved=False).all()}


def test_missing_dns(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.missing_dns.value) in _cats(db)


def test_missing_dns_satisfied_by_record(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.missing_dns.value) not in _cats(db)


def test_orphan_dns(db):
    _subnet(db)
    db.add(CachedDNSRecord(name="ghost", record_type="A", value="10.0.0.9", zone="x", source="msdns", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    cats = _cats(db)
    assert ("10.0.0.9", DriftCategory.orphan_dns.value) in cats


def test_orphan_dhcp(db):
    _subnet(db)
    db.add(CachedDHCPLease(scope_id="s", ip_address="10.0.0.8", name="x", source="msdhcp", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.8", DriftCategory.orphan_dhcp.value) in _cats(db)


def test_mac_mismatch(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, mac_address="aa:bb:cc:dd:ee:ff"))
    db.add(CachedDHCPLease(scope_id="s", ip_address="10.0.0.5", mac_address="11:22:33:44:55:66", source="msdhcp", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.mac_mismatch.value) in _cats(db)


def test_mac_match_no_drift(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, mac_address="AA-BB-CC-DD-EE-FF"))
    db.add(CachedDHCPLease(scope_id="s", ip_address="10.0.0.5", mac_address="aa:bb:cc:dd:ee:ff", source="msdhcp", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.mac_mismatch.value) not in _cats(db)


def test_active_but_available_carried(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.available))
    now = utcnow()
    db.add(ScanResult(subnet_id=s.id, ip_address="10.0.0.5", reachable=True, latency_ms=1.0, scanned_at=now))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.active_but_available.value) in _cats(db)


def test_severity_and_subnet_id_set(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.commit()
    detect_drift(db)
    item = db.query(DriftItem).filter_by(category=DriftCategory.missing_dns.value).first()
    assert item.severity == "warning"
    assert item.subnet_id == s.id


def test_auto_resolve_when_cleared(db):
    s = _subnet(db)
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web")
    db.add(a)
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.missing_dns.value) in _cats(db)
    # add the missing record -> next detect clears it
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.missing_dns.value) not in _cats(db)
    cleared = db.query(DriftItem).filter_by(category=DriftCategory.missing_dns.value).first()
    assert cleared.resolved is True


# ── v2 categories ────────────────────────────────────────────────────────────

def test_missing_dhcp(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.missing_dhcp.value) in _cats(db)


def test_missing_dhcp_satisfied_by_lease(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.add(CachedDHCPLease(scope_id="s", ip_address="10.0.0.5", name="web", source="msdhcp", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.missing_dhcp.value) not in _cats(db)


def test_missing_dhcp_not_flagged_for_available(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.available))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.missing_dhcp.value) not in _cats(db)


def test_ptr_mismatch(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    # PTR points to a different name
    db.add(CachedDNSRecord(name="5.0.0.10.in-addr.arpa", record_type="PTR", value="other.example.com.", zone="x", source="msdns", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.ptr_mismatch.value) in _cats(db)


def test_ptr_mismatch_ok_when_fqdn(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    # PTR is web.example.com — starts with A record name, so OK
    db.add(CachedDNSRecord(name="5.0.0.10.in-addr.arpa", record_type="PTR", value="web.example.com.", zone="x", source="msdns", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.ptr_mismatch.value) not in _cats(db)


def test_ptr_no_record_no_mismatch(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.ptr_mismatch.value) not in _cats(db)


def test_unreachable_assigned(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(ScanResult(subnet_id=s.id, ip_address="10.0.0.5", reachable=False, latency_ms=None, scanned_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.unreachable_assigned.value) in _cats(db)


def test_unreachable_available_not_flagged(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.available))
    db.add(ScanResult(subnet_id=s.id, ip_address="10.0.0.5", reachable=False, latency_ms=None, scanned_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.unreachable_assigned.value) not in _cats(db)


def test_unreachable_assigned_stale_scan_no_flag(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned))
    stale = utcnow() - timedelta(hours=30)
    db.add(ScanResult(subnet_id=s.id, ip_address="10.0.0.5", reachable=False, latency_ms=None, scanned_at=stale))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.unreachable_assigned.value) not in _cats(db)


def test_unreachable_reachable_no_flag(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(ScanResult(subnet_id=s.id, ip_address="10.0.0.5", reachable=True, latency_ms=1.0, scanned_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.unreachable_assigned.value) not in _cats(db)


# ── PROVIDER-CONFLICT-001: dns_source_conflict ──────────────────────────────

def _drift(db, ip, category):
    return (
        db.query(DriftItem)
        .filter_by(ip_address=ip, category=category, resolved=False)
        .one_or_none()
    )


def test_dns_source_conflict_two_providers_same_ip(db):
    """Same IP has an A record in two DNS providers → conflict flagged."""
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="bind", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    d = _drift(db, "10.0.0.5", DriftCategory.dns_source_conflict.value)
    assert d is not None
    import json
    details = json.loads(d.details)
    assert sorted(details["sources"]) == ["bind", "msdns"]
    assert details["divergent_names"] is False


def test_dns_source_conflict_divergent_names(db):
    """Two providers claim the same IP with different names → divergent flag set."""
    _subnet(db)
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    db.add(CachedDNSRecord(name="www", record_type="A", value="10.0.0.5", zone="x", source="cloudflare", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    d = _drift(db, "10.0.0.5", DriftCategory.dns_source_conflict.value)
    assert d is not None
    import json
    assert json.loads(d.details)["divergent_names"] is True


def test_dns_source_conflict_single_provider_no_flag(db):
    """One provider with the record (even multiple names) is not a conflict."""
    _subnet(db)
    db.add(CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    db.add(CachedDNSRecord(name="alias", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("10.0.0.5", DriftCategory.dns_source_conflict.value) not in _cats(db)


def test_dns_source_conflict_out_of_scope_ignored(db):
    """A conflicting IP outside every managed subnet is not flagged."""
    _subnet(db, cidr="10.0.0.0/24")
    db.add(CachedDNSRecord(name="x", record_type="A", value="192.168.9.9", zone="x", source="msdns", synced_at=utcnow()))
    db.add(CachedDNSRecord(name="x", record_type="A", value="192.168.9.9", zone="x", source="bind", synced_at=utcnow()))
    db.commit()
    detect_drift(db)
    assert ("192.168.9.9", DriftCategory.dns_source_conflict.value) not in _cats(db)


def test_dns_source_conflict_auto_resolves(db):
    """When one provider's record disappears, the conflict auto-resolves."""
    _subnet(db)
    r1 = CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="msdns", synced_at=utcnow())
    r2 = CachedDNSRecord(name="web", record_type="A", value="10.0.0.5", zone="x", source="bind", synced_at=utcnow())
    db.add_all([r1, r2])
    db.commit()
    detect_drift(db)
    assert _drift(db, "10.0.0.5", DriftCategory.dns_source_conflict.value) is not None
    db.delete(r2)
    db.commit()
    detect_drift(db)
    assert _drift(db, "10.0.0.5", DriftCategory.dns_source_conflict.value) is None
