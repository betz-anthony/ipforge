import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.providers.registry import get_dns_providers
from app.providers.dns.base import DNSRecord
from app.models.cache import CachedDNSZone, CachedDNSRecord as CRow
from app.core.deps import require_operator
from app.core.audit import write_audit
from app.core.ptr import find_reverse_zone, build_ptr_record

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateRecordRequest(DNSRecord):
    register_ptr: bool = False


class DeleteRecordRequest(DNSRecord):
    delete_ptr: bool = False


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/zones")
def list_zones(db: Session = Depends(get_db)):
    seen: set[tuple] = set()
    result: list[dict] = []
    for r in db.query(CachedDNSZone).order_by(CachedDNSZone.zone).all():
        key = (r.zone, r.source)
        if key not in seen:
            seen.add(key)
            result.append({"zone": r.zone, "source": r.source})
    return result


@router.get("/zones/{zone}/records")
def list_records(zone: str, db: Session = Depends(get_db)):
    rows = db.query(CRow).filter_by(zone=zone).all()
    return [
        {
            "name": r.name, "record_type": r.record_type, "value": r.value,
            "zone": r.zone, "ttl": r.ttl, "source": r.source,
            "synced_at": r.synced_at.isoformat() + "Z" if r.synced_at else None,
        }
        for r in rows
    ]


@router.get("/by-ip/{address}")
def get_records_by_ip(address: str, db: Session = Depends(get_db)):
    rows = db.query(CRow).filter(CRow.value == address).all()
    return [
        {
            "name": r.name, "record_type": r.record_type, "value": r.value,
            "zone": r.zone, "ttl": r.ttl, "source": r.source,
            "synced_at": r.synced_at.isoformat() + "Z" if r.synced_at else None,
        }
        for r in rows
    ]


@router.post("/zones/{zone}/records", response_model=DNSRecord, status_code=201)
def create_record(
    zone: str,
    record: CreateRecordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    record.zone = zone
    providers = get_dns_providers()
    target = next((p for p in providers if p.source == record.source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DNS provider configured")

    if record.register_ptr and record.record_type == "A":
        from app.providers.dns.pihole import PiholeDNSProvider
        if isinstance(target, PiholeDNSProvider):
            raise HTTPException(422, "Provider does not support PTR records")

    try:
        target.add_record(record)
        record.source = target.source
    except Exception as e:
        logger.error("DNS %s add_record: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    if record.register_ptr and record.record_type == "A":
        zones = [row.zone for row in db.query(CachedDNSZone).filter_by(source=record.source).all()]
        reverse_zone = find_reverse_zone(record.value, zones)
        if reverse_zone is None:
            try:
                target.delete_record(record)
            except Exception as ce:
                logger.warning("A record rollback failed: %s", ce)
            raise HTTPException(422, "No reverse zone found for this IP address")

        ptr_record = build_ptr_record(record.value, record.name, reverse_zone, provider=record.source)
        try:
            target.add_record(ptr_record)
        except Exception as e:
            try:
                target.delete_record(record)
            except Exception as ce:
                logger.warning("A record rollback failed: %s", ce)
            raise HTTPException(502, f"PTR registration failed: {e}")

        now = _utcnow()
        db.add(CRow(name=ptr_record.name, record_type="PTR", value=ptr_record.value,
                    zone=reverse_zone, ttl=ptr_record.ttl, source=record.source, synced_at=now))

    now = _utcnow()
    db.add(CRow(name=record.name, record_type=record.record_type, value=record.value,
                zone=zone, ttl=record.ttl, source=record.source, synced_at=now))
    if db.get(CachedDNSZone, (zone, record.source)) is None:
        db.add(CachedDNSZone(zone=zone, source=record.source, synced_at=now))
    write_audit(db, current_user.username, "create", "dns_record",
                f"{record.name}/{record.record_type}",
                f"{record.name} {record.record_type} {record.value}",
                after={k: v for k, v in record.model_dump().items() if k != "register_ptr"})
    db.commit()
    return record


@router.delete("/zones/{zone}/records", status_code=204)
def delete_record(
    zone: str,
    record: DeleteRecordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    record.zone = zone
    providers = get_dns_providers()
    target = next((p for p in providers if p.source == record.source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DNS provider configured")

    ptr_record = None
    if record.delete_ptr and record.record_type == "A":
        from app.providers.dns.pihole import PiholeDNSProvider
        if isinstance(target, PiholeDNSProvider):
            raise HTTPException(422, "Provider does not support PTR records")
        zones = [row.zone for row in db.query(CachedDNSZone).filter_by(source=record.source).all()]
        reverse_zone = find_reverse_zone(record.value, zones)
        if reverse_zone is None:
            raise HTTPException(422, "No reverse zone found for this IP address")
        ptr_record = build_ptr_record(record.value, record.name, reverse_zone, provider=record.source)

    try:
        target.delete_record(record)
    except Exception as e:
        logger.error("DNS %s delete_record: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    if ptr_record is not None:
        try:
            target.delete_record(ptr_record)
        except Exception as e:
            try:
                target.add_record(record)
            except Exception as ce:
                logger.warning("A record rollback failed: %s", ce)
            raise HTTPException(502, f"PTR delete failed: {e}")
        db.query(CRow).filter_by(
            name=ptr_record.name, record_type="PTR",
            zone=ptr_record.zone, source=record.source,
        ).delete()

    db.query(CRow).filter_by(
        name=record.name, record_type=record.record_type,
        value=record.value, zone=zone, source=record.source,
    ).delete()
    write_audit(db, current_user.username, "delete", "dns_record",
                f"{record.name}/{record.record_type}",
                f"{record.name} {record.record_type} {record.value}",
                before={k: v for k, v in record.model_dump().items() if k != "delete_ptr"})
    db.commit()
