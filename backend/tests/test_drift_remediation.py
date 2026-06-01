import json
from unittest.mock import MagicMock, patch

from app.drift_remediation import remediate_drift, SAFE_CATEGORIES
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.scan import DriftItem, DriftPolicy, DriftCategory
from app.models.gitops import GitopsManaged
from app.models.cache import CachedDNSRecord, CachedDHCPLease
from app.core.time import utcnow


def _subnet(db, cidr="10.0.0.0/24"):
    s = Subnet(name="N", cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    return s


def _drift(db, ip, category, details=None, subnet_id=None):
    d = DriftItem(ip_address=ip, category=category, severity="info",
                  subnet_id=subnet_id, details=json.dumps(details or {}),
                  detected_at=utcnow(), resolved=False)
    db.add(d)
    db.commit()
    return d


def _policy(db, category, mode="auto", dry_run=False, params=None):
    p = DriftPolicy(category=category, mode=mode, dry_run=dry_run, params=params or {}, enabled=True)
    db.add(p)
    db.commit()
    return p


def test_orphan_dhcp_auto_import(db):
    s = _subnet(db)
    d = _drift(db, "10.0.0.8", DriftCategory.orphan_dhcp.value,
               details={"name": "host", "mac": "aa:bb:cc:dd:ee:ff"})
    _policy(db, DriftCategory.orphan_dhcp.value)
    remediate_drift(db)
    a = db.query(IPAddress).filter_by(address="10.0.0.8").first()
    assert a is not None and a.hostname == "host" and a.mac_address == "aa:bb:cc:dd:ee:ff"
    db.refresh(d)
    assert d.resolved is True


def test_mac_mismatch_auto_update(db):
    s = _subnet(db)
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, mac_address="11:11:11:11:11:11")
    db.add(a); db.commit()
    _drift(db, "10.0.0.5", DriftCategory.mac_mismatch.value,
           details={"ipam_mac": "11:11:11:11:11:11", "dhcp_mac": "22:22:22:22:22:22"}, subnet_id=s.id)
    _policy(db, DriftCategory.mac_mismatch.value)
    remediate_drift(db)
    db.refresh(a)
    assert a.mac_address == "22:22:22:22:22:22"


def test_active_set_status(db):
    s = _subnet(db)
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.available)
    db.add(a); db.commit()
    _drift(db, "10.0.0.5", DriftCategory.active_but_available.value, subnet_id=s.id)
    _policy(db, DriftCategory.active_but_available.value, params={"target_status": "assigned"})
    remediate_drift(db)
    db.refresh(a)
    assert a.status == AddressStatus.assigned


def test_dry_run_makes_no_change(db):
    s = _subnet(db)
    d = _drift(db, "10.0.0.8", DriftCategory.orphan_dhcp.value, details={"name": "x"})
    _policy(db, DriftCategory.orphan_dhcp.value, dry_run=True)
    remediate_drift(db)
    assert db.query(IPAddress).filter_by(address="10.0.0.8").count() == 0
    db.refresh(d)
    assert d.resolved is False


def test_review_mode_flags_needs_review(db):
    _subnet(db)
    d = _drift(db, "10.0.0.9", DriftCategory.multi_dhcp_scope.value)
    _policy(db, DriftCategory.multi_dhcp_scope.value, mode="review")
    remediate_drift(db)
    db.refresh(d)
    assert d.needs_review is True
    assert d.resolved is False


def test_no_policy_untouched(db):
    s = _subnet(db)
    d = _drift(db, "10.0.0.8", DriftCategory.orphan_dhcp.value, details={"name": "x"})
    remediate_drift(db)
    assert db.query(IPAddress).filter_by(address="10.0.0.8").count() == 0
    db.refresh(d)
    assert d.resolved is False and d.needs_review is False


def test_gitops_managed_skipped(db):
    s = _subnet(db)
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, mac_address="11:11:11:11:11:11")
    db.add(a); db.commit()
    db.add(GitopsManaged(source="prod", resource_type="address", resource_id=a.id))
    _drift(db, "10.0.0.5", DriftCategory.mac_mismatch.value,
           details={"dhcp_mac": "22:22:22:22:22:22"}, subnet_id=s.id)
    _policy(db, DriftCategory.mac_mismatch.value)
    remediate_drift(db)
    db.refresh(a)
    assert a.mac_address == "11:11:11:11:11:11"  # unchanged — gitops authoritative


def test_safe_categories_constant():
    assert DriftCategory.orphan_dhcp.value in SAFE_CATEGORIES
    assert DriftCategory.hostname_mismatch.value not in SAFE_CATEGORIES


# ── subnet-scoped policies ───────────────────────────────────────────────────

def test_subnet_policy_overrides_global(db):
    s = _subnet(db)
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.available)
    db.add(a); db.commit()
    _drift(db, "10.0.0.5", DriftCategory.active_but_available.value, subnet_id=s.id)
    # Global sets assigned, subnet sets reserved
    _policy(db, DriftCategory.active_but_available.value, params={"target_status": "assigned"})
    p_sub = DriftPolicy(category=DriftCategory.active_but_available.value, subnet_id=s.id,
                        mode="auto", dry_run=False, params={"target_status": "reserved"}, enabled=True)
    db.add(p_sub); db.commit()
    remediate_drift(db)
    db.refresh(a)
    assert a.status == AddressStatus.reserved


def test_global_policy_used_when_no_subnet_policy(db):
    s = _subnet(db)
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.available)
    db.add(a); db.commit()
    _drift(db, "10.0.0.5", DriftCategory.active_but_available.value, subnet_id=s.id)
    _policy(db, DriftCategory.active_but_available.value, params={"target_status": "assigned"})
    remediate_drift(db)
    db.refresh(a)
    assert a.status == AddressStatus.assigned


# ── provider action: delete_provider ────────────────────────────────────────

def test_provider_delete_orphan_dns(db):
    _subnet(db)
    rec = CachedDNSRecord(name="ghost", record_type="A", value="10.0.0.9",
                          zone="x", source="msdns", synced_at=utcnow())
    db.add(rec); db.commit()
    d = _drift(db, "10.0.0.9", DriftCategory.orphan_dns.value,
               details={"name": "ghost", "zone": "x", "source": "msdns"})
    _policy(db, DriftCategory.orphan_dns.value, params={"action": "delete_provider"})

    mock_prov = MagicMock()
    mock_prov.source = "msdns"
    with patch("app.drift_remediation.get_dns_providers", return_value=[mock_prov]):
        remediate_drift(db)

    mock_prov.delete_record.assert_called_once()
    db.refresh(d)
    assert d.resolved is True


def test_provider_delete_orphan_dhcp(db):
    _subnet(db)
    lease = CachedDHCPLease(scope_id="sc1", ip_address="10.0.0.9",
                            name="x", source="msdhcp", synced_at=utcnow())
    db.add(lease); db.commit()
    d = _drift(db, "10.0.0.9", DriftCategory.orphan_dhcp.value,
               details={"name": "x", "scope_id": "sc1", "source": "msdhcp"})
    _policy(db, DriftCategory.orphan_dhcp.value, params={"action": "delete_provider"})

    mock_prov = MagicMock()
    mock_prov.source = "msdhcp"
    with patch("app.drift_remediation.get_dhcp_providers", return_value=[mock_prov]):
        remediate_drift(db)

    mock_prov.delete_reservation.assert_called_once_with("sc1", "10.0.0.9")
    db.refresh(d)
    assert d.resolved is True


# ── provider action: push_dns ────────────────────────────────────────────────

def test_provider_push_dns_missing_dns(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="web"))
    db.commit()
    d = _drift(db, "10.0.0.5", DriftCategory.missing_dns.value,
               details={"hostname": "web", "status": "assigned"}, subnet_id=s.id)
    _policy(db, DriftCategory.missing_dns.value, params={"action": "push_dns", "zone": "example.com"})

    mock_prov = MagicMock()
    with patch("app.drift_remediation.get_dns_providers", return_value=[mock_prov]):
        remediate_drift(db)

    mock_prov.add_record.assert_called_once()
    call_record = mock_prov.add_record.call_args[0][0]
    assert call_record.name == "web" and call_record.value == "10.0.0.5"
    db.refresh(d)
    assert d.resolved is True


def test_provider_push_dns_skips_without_zone(db):
    s = _subnet(db)
    d = _drift(db, "10.0.0.5", DriftCategory.missing_dns.value,
               details={"hostname": "web", "status": "assigned"}, subnet_id=s.id)
    _policy(db, DriftCategory.missing_dns.value, params={"action": "push_dns"})

    mock_prov = MagicMock()
    with patch("app.drift_remediation.get_dns_providers", return_value=[mock_prov]):
        remediate_drift(db)

    mock_prov.add_record.assert_not_called()
    db.refresh(d)
    assert d.resolved is False


# ── provider action: push_hostname ──────────────────────────────────────────

def test_provider_push_hostname(db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, hostname="newname"))
    rec = CachedDNSRecord(name="oldname", record_type="A", value="10.0.0.5",
                          zone="x", source="msdns", synced_at=utcnow())
    db.add(rec); db.commit()
    d = _drift(db, "10.0.0.5", DriftCategory.hostname_mismatch.value,
               details={"ipam": "newname", "dns": "oldname", "dhcp": None}, subnet_id=s.id)
    _policy(db, DriftCategory.hostname_mismatch.value, params={"action": "push_hostname"})

    mock_dns = MagicMock()
    mock_dns.source = "msdns"
    with patch("app.drift_remediation.get_dns_providers", return_value=[mock_dns]), \
         patch("app.drift_remediation.get_dhcp_providers", return_value=[]):
        remediate_drift(db)

    mock_dns.update_record.assert_called_once()
    old_r, new_r = mock_dns.update_record.call_args[0]
    assert old_r.name == "oldname" and new_r.name == "newname"
    db.refresh(d)
    assert d.resolved is True
