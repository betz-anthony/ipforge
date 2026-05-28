import json

from app.drift_remediation import remediate_drift, SAFE_CATEGORIES
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.scan import DriftItem, DriftPolicy, DriftCategory
from app.models.gitops import GitopsManaged
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
