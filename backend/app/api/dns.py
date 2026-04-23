import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.providers.registry import get_dns_providers
from app.providers.dns.base import DNSRecord
from app.models.cache import CachedDNSZone, CachedDNSRecord as CRow

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/zones")
def list_zones(db: Session = Depends(get_db)):
    rows = db.query(CachedDNSZone).all()
    seen: set[str] = set()
    zones: list[str] = []
    for r in rows:
        if r.zone not in seen:
            seen.add(r.zone)
            zones.append(r.zone)
    return zones


@router.get("/zones/{zone}/records", response_model=list[DNSRecord])
def list_records(zone: str, db: Session = Depends(get_db)):
    rows = db.query(CRow).filter_by(zone=zone).all()
    return [
        DNSRecord(name=r.name, record_type=r.record_type, value=r.value,
                  zone=r.zone, ttl=r.ttl, source=r.source)
        for r in rows
    ]


@router.post("/zones/{zone}/records", response_model=DNSRecord, status_code=201)
def create_record(zone: str, record: DNSRecord, db: Session = Depends(get_db)):
    record.zone = zone
    providers = get_dns_providers()
    target = next((p for p in providers if p.source == record.source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DNS provider configured")
    try:
        target.add_record(record)
        record.source = target.source
    except Exception as e:
        logger.error("DNS %s add_record: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    now = _utcnow()
    db.add(CRow(name=record.name, record_type=record.record_type, value=record.value,
                zone=zone, ttl=record.ttl, source=record.source, synced_at=now))
    if db.get(CachedDNSZone, (zone, record.source)) is None:
        db.add(CachedDNSZone(zone=zone, source=record.source, synced_at=now))
    db.commit()
    return record


@router.delete("/zones/{zone}/records", status_code=204)
def delete_record(zone: str, record: DNSRecord, db: Session = Depends(get_db)):
    record.zone = zone
    providers = get_dns_providers()
    target = next((p for p in providers if p.source == record.source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DNS provider configured")
    try:
        target.delete_record(record)
    except Exception as e:
        logger.error("DNS %s delete_record: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    db.query(CRow).filter_by(
        name=record.name, record_type=record.record_type,
        value=record.value, zone=zone, source=record.source,
    ).delete()
    db.commit()
