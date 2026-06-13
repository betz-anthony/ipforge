"""DRIFT-001 v2 — auto-remediation sweep.

Applies per-category drift_policies to open drift items. Subnet-specific
policies override global ones. Safe (IPAM-only, reversible) actions can
auto-apply; provider actions require explicit params.action configuration.
gitops-managed resources are skipped (the declared document is authoritative).
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
from app.providers.registry import get_dns_providers, get_dhcp_providers

logger = logging.getLogger(__name__)

SAFE_CATEGORIES = {
    DriftCategory.orphan_dns.value,
    DriftCategory.orphan_dhcp.value,
    DriftCategory.mac_mismatch.value,
    DriftCategory.active_but_available.value,
}

PROVIDER_ACTIONS = {"push_dns", "delete_provider", "push_hostname"}

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


def _apply_provider_action(db, item: DriftItem, action: str, params: dict) -> bool:
    """Execute a provider-side action. Returns True if action was performed."""
    from app.providers.dns.base import DNSRecord
    from app.models.cache import CachedDNSRecord, CachedDHCPLease

    ip = item.ip_address
    details: dict = {}
    try:
        details = json.loads(item.details) if item.details else {}
    except ValueError:
        pass

    if action == "delete_provider":
        if item.category == DriftCategory.orphan_dns.value:
            rec = db.query(CachedDNSRecord).filter(
                CachedDNSRecord.value == ip,
                CachedDNSRecord.record_type.in_(["A", "AAAA"]),
            ).first()
            if not rec:
                return False
            providers = get_dns_providers()
            prov = next((p for p in providers if p.source == rec.source),
                        providers[0] if providers else None)
            if not prov:
                return False
            prov.delete_record(DNSRecord(
                name=rec.name, record_type=rec.record_type, value=rec.value,
                zone=rec.zone, ttl=rec.ttl, source=rec.source))
            return True

        if item.category == DriftCategory.orphan_dhcp.value:
            lease = db.query(CachedDHCPLease).filter_by(ip_address=ip).first()
            if not lease:
                return False
            providers = get_dhcp_providers()
            prov = next((p for p in providers if p.source == lease.source),
                        providers[0] if providers else None)
            if not prov:
                return False
            prov.delete_reservation(lease.scope_id, ip)
            return True

    if action == "push_dns":
        if item.category != DriftCategory.missing_dns.value:
            return False
        hostname = details.get("hostname")
        zone = params.get("zone", "")
        if not hostname or not zone:
            logger.warning("push_dns: hostname or zone missing for %s — configure params.zone", ip)
            return False
        providers = get_dns_providers()
        if not providers:
            return False
        rtype = "AAAA" if ":" in ip else "A"
        providers[0].add_record(DNSRecord(name=hostname, record_type=rtype, value=ip, zone=zone))
        return True

    if action == "push_hostname":
        if item.category != DriftCategory.hostname_mismatch.value:
            return False
        ipam_name = details.get("ipam", "")
        if not ipam_name:
            return False
        changed = False

        rec = db.query(CachedDNSRecord).filter(
            CachedDNSRecord.value == ip,
            CachedDNSRecord.record_type.in_(["A", "AAAA"]),
        ).first()
        if rec and details.get("dns") and details["dns"].lower() != ipam_name.lower():
            dns_providers = get_dns_providers()
            prov = next((p for p in dns_providers if p.source == rec.source),
                        dns_providers[0] if dns_providers else None)
            if prov:
                old_rec = DNSRecord(name=details["dns"], record_type=rec.record_type,
                                    value=ip, zone=rec.zone, ttl=rec.ttl, source=rec.source)
                new_rec = DNSRecord(name=ipam_name, record_type=rec.record_type,
                                    value=ip, zone=rec.zone, ttl=rec.ttl, source=rec.source)
                prov.update_record(old_rec, new_rec)
                changed = True

        lease = db.query(CachedDHCPLease).filter_by(ip_address=ip).first()
        if lease and details.get("dhcp") and details["dhcp"].lower() != ipam_name.lower():
            dhcp_providers = get_dhcp_providers()
            prov = next((p for p in dhcp_providers if p.source == lease.source),
                        dhcp_providers[0] if dhcp_providers else None)
            if prov:
                prov.update_reservation_name(lease.scope_id, ip, ipam_name)
                changed = True

        return changed

    return False


def _set_status_value(item_params: dict) -> str:
    return item_params.get("target_status") or "reserved"


def _apply_with_params(db, item: DriftItem, params: dict) -> bool:
    action = (params or {}).get("action", "")
    if action in PROVIDER_ACTIONS:
        return _apply_provider_action(db, item, action, params)
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


def remediate_drift(db, subnet_id: int | None = None) -> None:
    all_policies = db.query(DriftPolicy).filter_by(enabled=True).all()
    if not all_policies:
        return

    # Subnet-specific policies override globals.
    global_policies: dict[str, DriftPolicy] = {}
    subnet_policies: dict[tuple[str, int], DriftPolicy] = {}
    for p in all_policies:
        if p.subnet_id is None:
            global_policies[p.category] = p
        else:
            subnet_policies[(p.category, p.subnet_id)] = p

    def _get_policy(category: str, sid: int | None) -> DriftPolicy | None:
        if sid is not None:
            sp = subnet_policies.get((category, sid))
            if sp is not None:
                return sp
        return global_policies.get(category)

    q = db.query(DriftItem).filter(DriftItem.resolved.is_(False))
    if subnet_id is not None:
        q = q.filter(DriftItem.subnet_id == subnet_id)

    changed = False
    for item in q.all():
        policy = _get_policy(item.category, item.subnet_id)
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

        action_type = (policy.params or {}).get("action", "")
        is_provider = action_type in PROVIDER_ACTIONS
        if policy.mode == "auto" and (item.category in SAFE_CATEGORIES or is_provider):
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


def remediate_drift_bg() -> None:
    db = SessionLocal()
    try:
        remediate_drift(db)
    except Exception:
        logger.exception("remediate_drift_bg failed")
    finally:
        db.close()
