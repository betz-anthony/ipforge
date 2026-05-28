"""DRIFT-001 — reconciliation API: list, stats, scan, resolve, bulk-resolve."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import get_current_user, require_operator
from app.core.time import utcnow
from app.database import get_db
from app.drift import detect_drift
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord
from app.models.scan import DriftItem
from app.models.subnet import Subnet
from app.models.user import User
from app.providers.dhcp.base import DHCPReservation
from app.providers.dns.base import DNSRecord
from app.providers.registry import get_dhcp_providers, get_dns_providers
from app.utils import ip_in_cidr

logger = logging.getLogger(__name__)
router = APIRouter()


class DriftResponse(BaseModel):
    id: int
    ip_address: str
    category: str
    severity: str
    subnet_id: int | None
    details: str | None
    detected_at: str | None
    resolved: bool
    resolved_at: str | None


class ResolveRequest(BaseModel):
    # carried categories
    new_status:         str | None       = None  # active_but_available
    canonical_hostname: str | None       = None  # hostname_mismatch
    sources_to_remove:  list[str] | None = None  # multi_dhcp_scope
    # new categories
    action:             str | None       = None  # orphan_dns/orphan_dhcp: import|delete; mac_mismatch: update_ipam


class ResolveResponse(BaseModel):
    id: int
    resolved: bool


class BulkResolveRequest(BaseModel):
    ids: list[int]
    action: str | None = None  # dismiss|delete|import (same-category simple actions)


def _out(d: DriftItem) -> DriftResponse:
    return DriftResponse(
        id=d.id, ip_address=d.ip_address, category=d.category, severity=d.severity,
        subnet_id=d.subnet_id, details=d.details,
        detected_at=d.detected_at.isoformat() + "Z" if d.detected_at else None,
        resolved=d.resolved,
        resolved_at=d.resolved_at.isoformat() + "Z" if d.resolved_at else None,
    )


@router.get("", response_model=list[DriftResponse])
def list_drift(
    resolved:  bool = Query(False),
    category:  str | None = Query(None),
    severity:  str | None = Query(None),
    subnet_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(DriftItem).filter(DriftItem.resolved == resolved)
    if category is not None:
        q = q.filter(DriftItem.category == category)
    if severity is not None:
        q = q.filter(DriftItem.severity == severity)
    if subnet_id is not None:
        q = q.filter(DriftItem.subnet_id == subnet_id)
    return [_out(d) for d in q.order_by(DriftItem.detected_at.desc()).all()]


@router.get("/stats")
def drift_stats(db: Session = Depends(get_db)):
    by_cat = dict(
        db.query(DriftItem.category, func.count(DriftItem.id))
        .filter(DriftItem.resolved.is_(False))
        .group_by(DriftItem.category).all()
    )
    by_sev = dict(
        db.query(DriftItem.severity, func.count(DriftItem.id))
        .filter(DriftItem.resolved.is_(False))
        .group_by(DriftItem.severity).all()
    )
    return {"total": sum(by_cat.values()), "by_category": by_cat, "by_severity": by_sev}


@router.post("/scan")
def trigger_scan(
    subnet_id: int | None = Query(None),
    _: User = Depends(require_operator),
    db: Session = Depends(get_db),
):
    detect_drift(db, subnet_id)
    return {"status": "ok"}


def _resolve_one(db: Session, d: DriftItem, body: ResolveRequest) -> dict:
    """Apply the category-specific remediation. Returns the audit action dict.
    Raises HTTPException on provider failure (rolled back)."""
    cat = d.category
    ip = d.ip_address

    if cat == "active_but_available" and body.new_status:
        try:
            new_status = AddressStatus(body.new_status)
        except ValueError:
            raise HTTPException(422, f"Invalid status: {body.new_status}")
        addr = db.query(IPAddress).filter_by(address=ip).first()
        if addr is None:
            raise HTTPException(422, "No IPAM record found for this IP")
        addr.status = new_status
        return {"new_status": body.new_status}

    if cat == "hostname_mismatch" and body.canonical_hostname:
        return _resolve_hostname_mismatch(db, ip, body.canonical_hostname)

    if cat == "multi_dhcp_scope" and body.sources_to_remove:
        return _resolve_multi_dhcp(db, ip, body.sources_to_remove)

    if cat == "orphan_dns" and body.action:
        return _resolve_orphan_dns(db, ip, body.action)

    if cat == "orphan_dhcp" and body.action:
        return _resolve_orphan_dhcp(db, ip, body.action)

    if cat == "mac_mismatch" and body.action == "update_ipam":
        lease = db.query(CachedDHCPLease).filter_by(ip_address=ip).first()
        addr = db.query(IPAddress).filter_by(address=ip).first()
        if lease and addr and lease.mac_address:
            addr.mac_address = lease.mac_address
        return {"action": "update_ipam"}

    return {}  # plain dismiss


def _resolve_hostname_mismatch(db: Session, ip: str, canonical: str) -> dict:
    lease = db.query(CachedDHCPLease).filter_by(ip_address=ip).first()
    dns_row = db.query(CachedDNSRecord).filter(
        CachedDNSRecord.value == ip,
        CachedDNSRecord.record_type.in_(["A", "AAAA"]),
    ).first()
    original_hostname = lease.name if lease else None

    dhcp_provider = None
    if lease:
        providers = get_dhcp_providers()
        dhcp_provider = next((p for p in providers if p.source == lease.source),
                             providers[0] if providers else None)
        if dhcp_provider:
            try:
                dhcp_provider.update_reservation_name(lease.scope_id, ip, canonical)
            except Exception as exc:
                logger.error("DHCP update_reservation_name failed: %s", exc)
                raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dhcp"})

    if dns_row:
        providers = get_dns_providers()
        dns_provider = next((p for p in providers if p.source == dns_row.source),
                            providers[0] if providers else None)
        if dns_provider:
            old_rec = DNSRecord(name=dns_row.name, record_type=dns_row.record_type,
                                value=dns_row.value, zone=dns_row.zone, ttl=dns_row.ttl, source=dns_row.source)
            new_rec = DNSRecord(name=canonical, record_type=dns_row.record_type,
                                value=dns_row.value, zone=dns_row.zone, ttl=dns_row.ttl, source=dns_row.source)
            try:
                dns_provider.update_record(old_rec, new_rec)
            except Exception as exc:
                logger.error("DNS update_record failed: %s", exc)
                if dhcp_provider and lease and original_hostname is not None:
                    try:
                        dhcp_provider.update_reservation_name(lease.scope_id, ip, original_hostname)
                    except Exception as rb_exc:
                        logger.error("DHCP rollback failed: %s", rb_exc)
                raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dns"})

    addr = db.query(IPAddress).filter_by(address=ip).first()
    if addr:
        addr.hostname = canonical
    return {"canonical_hostname": canonical}


def _resolve_multi_dhcp(db: Session, ip: str, sources_to_remove: list[str]) -> dict:
    providers = get_dhcp_providers()
    leases_by_source = {}
    for source in sources_to_remove:
        row = db.query(CachedDHCPLease).filter_by(ip_address=ip, source=source).first()
        if row:
            leases_by_source[source] = row
    deleted: list[tuple] = []
    for source in sources_to_remove:
        provider = next((p for p in providers if p.source == source), None)
        lease_row = leases_by_source.get(source)
        if not provider or not lease_row:
            continue
        try:
            provider.delete_reservation(lease_row.scope_id, ip)
            deleted.append((provider, lease_row))
        except Exception as exc:
            logger.error("DHCP delete_reservation failed for %s: %s", source, exc)
            for (prov, dl) in deleted:
                try:
                    prov.add_reservation(DHCPReservation(
                        scope_id=dl.scope_id, ip_address=dl.ip_address,
                        mac_address=dl.mac_address or "", client_duid=dl.client_duid or "",
                        iaid=dl.iaid or 0, name=dl.name or "", description=dl.description or "",
                    ))
                except Exception as rb_exc:
                    logger.error("DHCP rollback add_reservation failed: %s", rb_exc)
            raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dhcp"})
    return {"sources_to_remove": sources_to_remove}


def _subnet_for(db: Session, ip: str) -> int | None:
    for s in db.query(Subnet).all():
        if ip_in_cidr(ip, s.cidr):
            return s.id
    return None


def _import_address(db: Session, ip: str, hostname: str | None, mac: str | None) -> None:
    if db.query(IPAddress).filter_by(address=ip).first():
        return
    sid = _subnet_for(db, ip)
    if sid is None:
        raise HTTPException(422, "No subnet contains this IP; cannot import")
    db.add(IPAddress(address=ip, subnet_id=sid, status=AddressStatus.discovered,
                     hostname=hostname or None, mac_address=mac or None))


def _resolve_orphan_dns(db: Session, ip: str, action: str) -> dict:
    rec = db.query(CachedDNSRecord).filter(
        CachedDNSRecord.value == ip, CachedDNSRecord.record_type.in_(["A", "AAAA"])
    ).first()
    if action == "import":
        _import_address(db, ip, rec.name if rec else None, None)
        return {"action": "import"}
    if action == "delete":
        if rec:
            providers = get_dns_providers()
            provider = next((p for p in providers if p.source == rec.source),
                            providers[0] if providers else None)
            if provider:
                try:
                    provider.delete_record(DNSRecord(
                        name=rec.name, record_type=rec.record_type, value=rec.value,
                        zone=rec.zone, ttl=rec.ttl, source=rec.source))
                except Exception as exc:
                    raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dns"})
        return {"action": "delete"}
    raise HTTPException(422, f"Invalid action for orphan_dns: {action}")


def _resolve_orphan_dhcp(db: Session, ip: str, action: str) -> dict:
    lease = db.query(CachedDHCPLease).filter_by(ip_address=ip).first()
    if action == "import":
        _import_address(db, ip, lease.name if lease else None, lease.mac_address if lease else None)
        return {"action": "import"}
    if action == "delete":
        if lease:
            providers = get_dhcp_providers()
            provider = next((p for p in providers if p.source == lease.source),
                            providers[0] if providers else None)
            if provider:
                try:
                    provider.delete_reservation(lease.scope_id, ip)
                except Exception as exc:
                    raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dhcp"})
        return {"action": "delete"}
    raise HTTPException(422, f"Invalid action for orphan_dhcp: {action}")


@router.post("/{drift_id}/resolve", response_model=ResolveResponse)
def resolve_drift(
    drift_id: int,
    body: ResolveRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    d = db.get(DriftItem, drift_id)
    if not d:
        raise HTTPException(404, "Drift item not found")
    action = _resolve_one(db, d, body or ResolveRequest())
    d.resolved = True
    d.resolved_at = utcnow()
    db.flush()
    write_audit(db, current_user.username, "resolve", "drift", str(d.id),
                f"{d.category} {d.ip_address}", after=action or None)
    db.commit()
    return ResolveResponse(id=d.id, resolved=True)


@router.post("/resolve-bulk")
def resolve_bulk(
    body: BulkResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    resolved: list[int] = []
    failed: list[dict] = []
    for did in body.ids:
        d = db.get(DriftItem, did)
        if not d or d.resolved:
            failed.append({"id": did, "error": "not found or already resolved"})
            continue
        try:
            req = ResolveRequest(action=body.action) if body.action in ("delete", "import") else ResolveRequest()
            action = _resolve_one(db, d, req)
            d.resolved = True
            d.resolved_at = utcnow()
            db.flush()
            write_audit(db, current_user.username, "resolve", "drift", str(d.id),
                        f"{d.category} {d.ip_address}", after=action or None)
            resolved.append(did)
        except HTTPException as exc:
            db.rollback()
            failed.append({"id": did, "error": str(exc.detail)})
    db.commit()
    return {"resolved": resolved, "failed": failed}
