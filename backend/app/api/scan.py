import logging
import threading
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.deps import get_current_user
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord
from app.models.cache import SyncStatus
from app.models.scan import Collision, ScanResult
from app.models.subnet import Subnet
from app.models.user import User
from app.providers.dhcp.base import DHCPReservation
from app.providers.dns.base import DNSRecord
from app.providers.registry import get_dhcp_providers, get_dns_providers
from app.utils import ip_in_cidr

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _age(synced_at) -> int | None:
    if synced_at is None:
        return None
    return max(0, int((_utcnow() - synced_at).total_seconds()))


# ── Request / response schemas ───────────────────────────────────────────────

class ScanTriggerBody(BaseModel):
    start_ip: str | None = None
    end_ip:   str | None = None


class TriggerResponse(BaseModel):
    status: str


class ScanHostResult(BaseModel):
    ip: str
    reachable: bool
    latency_ms: float | None


class ScanStatusResponse(BaseModel):
    status: str
    scanned_at: str | None
    age_seconds: int | None
    error: str | None
    results: list[ScanHostResult]


class CollisionResponse(BaseModel):
    id: int
    ip_address: str
    collision_type: Literal["active_but_available", "multi_dhcp_scope", "hostname_mismatch"]
    details: str | None
    detected_at: str | None
    resolved: bool
    resolved_at: str | None


class CollisionResolveRequest(BaseModel):
    new_status:         str | None       = None  # active_but_available
    canonical_hostname: str | None       = None  # hostname_mismatch
    sources_to_remove:  list[str] | None = None  # multi_dhcp_scope


class ResolveResponse(BaseModel):
    id: int
    resolved: bool


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/subnets/{subnet_id}", response_model=TriggerResponse)
def trigger_scan(
    subnet_id: int,
    body: ScanTriggerBody | None = None,
    db: Session = Depends(get_db),
):
    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")

    key = f"scan:{subnet_id}"
    status_row = db.get(SyncStatus, key)
    if status_row and status_row.status == "running":
        raise HTTPException(409, "Scan already running for this subnet")

    if body is None:
        body = ScanTriggerBody()

    from app.scan import scan_subnet
    threading.Thread(
        target=scan_subnet,
        args=(subnet_id,),
        kwargs={"start_ip": body.start_ip, "end_ip": body.end_ip},
        daemon=True,
    ).start()
    return TriggerResponse(status="triggered")


@router.get("/subnets/{subnet_id}", response_model=ScanStatusResponse)
def get_scan_status(subnet_id: int, db: Session = Depends(get_db)):
    key = f"scan:{subnet_id}"
    status_row = db.get(SyncStatus, key)

    all_results = (
        db.query(ScanResult)
        .filter_by(subnet_id=subnet_id)
        .order_by(ScanResult.scanned_at.desc())
        .all()
    )
    latest_results: list[ScanHostResult] = []
    if all_results:
        latest_time = all_results[0].scanned_at
        latest_results = [
            ScanHostResult(ip=r.ip_address, reachable=r.reachable, latency_ms=r.latency_ms)
            for r in all_results
            if r.scanned_at == latest_time
        ]

    return ScanStatusResponse(
        status=status_row.status if status_row else "never",
        scanned_at=status_row.synced_at.isoformat() + "Z" if (status_row and status_row.synced_at) else None,
        age_seconds=_age(status_row.synced_at) if status_row else None,
        error=status_row.error if status_row else None,
        results=latest_results,
    )


@router.get("/collisions", response_model=list[CollisionResponse])
def list_collisions(
    resolved:  bool       = Query(False),
    subnet_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    collisions = (
        db.query(Collision)
        .filter(Collision.resolved == resolved)
        .order_by(Collision.detected_at.desc())
        .all()
    )
    if subnet_id is not None:
        subnet = db.get(Subnet, subnet_id)
        if subnet:
            collisions = [c for c in collisions if ip_in_cidr(c.ip_address, subnet.cidr)]

    return [
        CollisionResponse(
            id=c.id,
            ip_address=c.ip_address,
            collision_type=c.collision_type,
            details=c.details,
            detected_at=c.detected_at.isoformat() + "Z" if c.detected_at else None,
            resolved=c.resolved,
            resolved_at=c.resolved_at.isoformat() + "Z" if c.resolved_at else None,
        )
        for c in collisions
    ]


@router.put("/collisions/{collision_id}/resolve", response_model=ResolveResponse)
def resolve_collision(
    collision_id: int,
    body: CollisionResolveRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.get(Collision, collision_id)
    if not c:
        raise HTTPException(404, "Collision not found")

    action_taken: dict = {}

    if body:
        if c.collision_type == "active_but_available" and body.new_status:
            try:
                new_status = AddressStatus(body.new_status)
            except ValueError:
                raise HTTPException(422, f"Invalid status: {body.new_status}")
            addr = db.query(IPAddress).filter_by(address=c.ip_address).first()
            if addr is None:
                raise HTTPException(422, "No IPAM record found for this IP")
            addr.status = new_status
            action_taken = {"new_status": body.new_status}

        elif c.collision_type == "hostname_mismatch" and body.canonical_hostname:
            canonical = body.canonical_hostname

            lease = db.query(CachedDHCPLease).filter_by(ip_address=c.ip_address).first()
            dns_row = db.query(CachedDNSRecord).filter(
                CachedDNSRecord.value == c.ip_address,
                CachedDNSRecord.record_type.in_(["A", "AAAA"]),
            ).first()
            original_hostname = lease.name if lease else None

            # Step 1: DHCP
            dhcp_provider = None
            if lease:
                dhcp_providers = get_dhcp_providers()
                dhcp_provider = next(
                    (p for p in dhcp_providers if p.source == lease.source),
                    dhcp_providers[0] if dhcp_providers else None,
                )
                if dhcp_provider:
                    try:
                        dhcp_provider.update_reservation_name(lease.scope_id, c.ip_address, canonical)
                    except Exception as exc:
                        logger.error("DHCP update_reservation_name failed: %s", exc)
                        raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dhcp"})

            # Step 2: DNS (with DHCP rollback on failure)
            if dns_row:
                dns_providers = get_dns_providers()
                dns_provider = next(
                    (p for p in dns_providers if p.source == dns_row.source),
                    dns_providers[0] if dns_providers else None,
                )
                if dns_provider:
                    old_rec = DNSRecord(
                        name=dns_row.name, record_type=dns_row.record_type,
                        value=dns_row.value, zone=dns_row.zone,
                        ttl=dns_row.ttl, source=dns_row.source,
                    )
                    new_rec = DNSRecord(
                        name=canonical, record_type=dns_row.record_type,
                        value=dns_row.value, zone=dns_row.zone,
                        ttl=dns_row.ttl, source=dns_row.source,
                    )
                    try:
                        dns_provider.update_record(old_rec, new_rec)
                    except Exception as exc:
                        logger.error("DNS update_record failed: %s", exc)
                        if dhcp_provider and lease and original_hostname is not None:
                            try:
                                dhcp_provider.update_reservation_name(lease.scope_id, c.ip_address, original_hostname)
                            except Exception as rb_exc:
                                logger.error("DHCP rollback failed: %s", rb_exc)
                        raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dns"})

            # Step 3: IPAM
            addr = db.query(IPAddress).filter_by(address=c.ip_address).first()
            if addr:
                addr.hostname = canonical
            action_taken = {"canonical_hostname": canonical}

        elif c.collision_type == "multi_dhcp_scope" and body.sources_to_remove:
            sources_to_remove = body.sources_to_remove
            dhcp_providers = get_dhcp_providers()

            # Pre-fetch lease data for each source (needed for rollback re-add)
            leases_by_source: dict = {}
            for source in sources_to_remove:
                row = db.query(CachedDHCPLease).filter_by(
                    ip_address=c.ip_address, source=source
                ).first()
                if row:
                    leases_by_source[source] = row

            deleted: list[tuple] = []  # (provider, lease_row) pairs already deleted

            for source in sources_to_remove:
                provider = next((p for p in dhcp_providers if p.source == source), None)
                lease_row = leases_by_source.get(source)
                if not provider or not lease_row:
                    continue
                try:
                    provider.delete_reservation(lease_row.scope_id, c.ip_address)
                    deleted.append((provider, lease_row))
                except Exception as exc:
                    logger.error("DHCP delete_reservation failed for %s: %s", source, exc)
                    for (prov, deleted_lease) in deleted:
                        try:
                            prov.add_reservation(DHCPReservation(
                                scope_id=deleted_lease.scope_id,
                                ip_address=deleted_lease.ip_address,
                                mac_address=deleted_lease.mac_address or "",
                                client_duid=deleted_lease.client_duid or "",
                                iaid=deleted_lease.iaid or 0,
                                name=deleted_lease.name or "",
                                description=deleted_lease.description or "",
                            ))
                        except Exception as rb_exc:
                            logger.error("DHCP rollback add_reservation failed: %s", rb_exc)
                    raise HTTPException(502, detail={"error": "connection_error", "detail": str(exc), "step": "dhcp"})

            action_taken = {"sources_to_remove": sources_to_remove}

    c.resolved    = True
    c.resolved_at = _utcnow()
    db.flush()
    write_audit(
        db, current_user.username, "resolve", "collision", str(c.id),
        f"{c.collision_type} {c.ip_address}",
        after=action_taken if action_taken else None,
    )
    db.commit()
    return ResolveResponse(id=c.id, resolved=True)
