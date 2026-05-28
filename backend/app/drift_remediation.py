"""DRIFT-001 v2 — auto-remediation sweep.

Applies per-category drift_policies to open drift items. Safe (IPAM-only,
reversible) actions can auto-apply; destructive/provider actions are never
automated — they are flagged needs_review for a human. gitops-managed resources
are skipped (the declared document is authoritative).
"""
import ipaddress
import json
import logging

from app.core.audit import write_audit
from app.core.time import utcnow
from app.database import SessionLocal
from app.models.address import IPAddress, AddressStatus
from app.models.gitops import GitopsManaged
from app.models.scan import DriftItem, DriftPolicy, DriftCategory
from app.models.subnet import Subnet

logger = logging.getLogger(__name__)

SAFE_CATEGORIES = {
    DriftCategory.orphan_dns.value,
    DriftCategory.orphan_dhcp.value,
    DriftCategory.mac_mismatch.value,
    DriftCategory.active_but_available.value,
}

_ACTOR = "drift-remediation"


def _subnet_id_for(db, ip: str) -> int | None:
    for s in db.query(Subnet).all():
        try:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(s.cidr, strict=False):
                return s.id
        except ValueError:
            continue
    return None


def _is_gitops_managed(db, address_id: int) -> bool:
    return db.query(GitopsManaged).filter_by(resource_type="address", resource_id=address_id).first() is not None


def _apply_safe(db, item: DriftItem) -> bool:
    """Apply the IPAM-only remediation for a safe category. Returns True if changed."""
    cat = item.category
    ip = item.ip_address
    details = {}
    try:
        details = json.loads(item.details) if item.details else {}
    except ValueError:
        details = {}

    if cat in (DriftCategory.orphan_dns.value, DriftCategory.orphan_dhcp.value):
        if db.query(IPAddress).filter_by(address=ip).first():
            return False  # already exists
        sid = _subnet_id_for(db, ip)
        if sid is None:
            return False
        db.add(IPAddress(
            address=ip, subnet_id=sid, status=AddressStatus.discovered,
            hostname=details.get("name") or None, mac_address=details.get("mac") or None,
        ))
        return True

    if cat == DriftCategory.mac_mismatch.value:
        addr = db.query(IPAddress).filter_by(address=ip).first()
        dhcp_mac = details.get("dhcp_mac")
        if addr and dhcp_mac:
            addr.mac_address = dhcp_mac
            return True
        return False

    return False


def _set_status_value(item_params: dict) -> str:
    return item_params.get("target_status") or "reserved"


def remediate_drift(db, subnet_id: int | None = None) -> None:
    policies = {p.category: p for p in db.query(DriftPolicy).filter_by(enabled=True).all()}
    if not policies:
        return

    q = db.query(DriftItem).filter(DriftItem.resolved.is_(False))
    if subnet_id is not None:
        q = q.filter(DriftItem.subnet_id == subnet_id)

    changed = False
    for item in q.all():
        policy = policies.get(item.category)
        if policy is None:
            continue

        addr = db.query(IPAddress).filter_by(address=item.ip_address).first()
        if addr is not None and _is_gitops_managed(db, addr.id):
            continue  # declared state is authoritative

        if policy.mode == "review":
            if not item.needs_review:
                item.needs_review = True
                changed = True
            continue

        if policy.mode == "auto" and item.category in SAFE_CATEGORIES:
            if policy.dry_run:
                write_audit(db, _ACTOR, "drift_remediate_dryrun", "drift", str(item.id),
                            f"{item.category} {item.ip_address}")
                logger.info("drift dry-run: would remediate %s %s", item.category, item.ip_address)
                changed = True
                continue
            try:
                applied = _apply_with_params(db, item, policy.params)
                if applied:
                    item.resolved = True
                    item.resolved_at = utcnow()
                    write_audit(db, _ACTOR, "drift_remediate", "drift", str(item.id),
                                f"{item.category} {item.ip_address}")
                    changed = True
            except Exception:
                logger.exception("drift remediation failed for %s %s", item.category, item.ip_address)

    if changed:
        db.commit()


def _apply_with_params(db, item: DriftItem, params: dict) -> bool:
    if item.category == DriftCategory.active_but_available.value:
        addr = db.query(IPAddress).filter_by(address=item.ip_address).first()
        if addr is None:
            return False
        try:
            addr.status = AddressStatus(_set_status_value(params))
        except ValueError:
            return False
        return True
    return _apply_safe(db, item)


def remediate_drift_bg() -> None:
    db = SessionLocal()
    try:
        remediate_drift(db)
    except Exception:
        logger.exception("remediate_drift_bg failed")
    finally:
        db.close()
