import logging
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import field_validator
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.providers.registry import get_dns_providers
from app.providers.dns.base import DNSRecord
from app.models.cache import CachedDNSZone, CachedDNSRecord as CRow
from app.core.deps import require_operator
from app.core.audit import write_audit
from app.core.time import utcnow
from app.core.ptr import find_reverse_zone, build_ptr_record

logger = logging.getLogger(__name__)
router = APIRouter()


_DNS_NAME_RE = re.compile(r"^[A-Za-z0-9_.*@-]{1,255}$")
_VALID_RECORD_TYPES = {"A", "AAAA", "CNAME", "PTR", "MX", "TXT", "NS"}


class CreateRecordRequest(DNSRecord):
    register_ptr: bool = False

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = v.strip()
        if not _DNS_NAME_RE.match(v):
            raise ValueError("name must be 1-255 chars: letters, digits, . _ - * @")
        return v

    @field_validator("record_type")
    @classmethod
    def _validate_record_type(cls, v: str) -> str:
        if v not in _VALID_RECORD_TYPES:
            raise ValueError(f"record_type must be one of {sorted(_VALID_RECORD_TYPES)}")
        return v

    @field_validator("value")
    @classmethod
    def _validate_value(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 512:
            raise ValueError("value must be 1-512 characters")
        if any(ord(c) < 32 for c in v):
            raise ValueError("value must not contain control characters")
        return v


class DeleteRecordRequest(DNSRecord):
    delete_ptr: bool = False


def _cached_zone_names(db: Session, source: str) -> list[str]:
    return [z for (z,) in db.query(CachedDNSZone.zone).filter_by(source=source)]


def _zone_names(db: Session, target) -> list[str]:
    """Reverse-zone candidates — cached zones, falling back to a live provider query."""
    cached = _cached_zone_names(db, target.source)
    return cached if cached else target.get_zones()


def _undo_provider(target, record: DNSRecord, op: str) -> None:
    """Best-effort reversal of a provider mutation after a failed DB transaction."""
    try:
        if op == "delete":
            target.delete_record(record)
        else:
            target.add_record(record)
    except Exception as exc:
        logger.warning("provider %s undo failed for %s/%s: %s",
                       op, record.name, record.record_type, exc)


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

    try:
        target.add_record(record)
        record.source = target.source
    except Exception as e:
        logger.error("DNS %s add_record: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    now = utcnow()
    ptr_record = None
    ptr_added = False
    # PTR registration is auxiliary: only when the provider supports PTR and a
    # reverse zone exists. A PTR failure is logged but never blocks the A record.
    if record.register_ptr and record.record_type == "A" and target.supports_ptr:
        reverse_zone = find_reverse_zone(record.value, _zone_names(db, target))
        if reverse_zone is not None:
            candidate = build_ptr_record(record.value, record.name, reverse_zone, provider=record.source)
            try:
                target.add_record(candidate)
                ptr_record = candidate
                ptr_added = True
            except Exception as e:
                logger.warning("PTR registration (best-effort) failed for %s: %s", candidate.name, e)

    try:
        if ptr_added and ptr_record is not None:
            db.add(CRow(name=ptr_record.name, record_type="PTR", value=ptr_record.value,
                        zone=ptr_record.zone, ttl=ptr_record.ttl, source=record.source, synced_at=now))
            if db.get(CachedDNSZone, (ptr_record.zone, record.source)) is None:
                db.add(CachedDNSZone(zone=ptr_record.zone, source=record.source, synced_at=now))

        db.add(CRow(name=record.name, record_type=record.record_type, value=record.value,
                    zone=zone, ttl=record.ttl, source=record.source, synced_at=now))
        if db.get(CachedDNSZone, (zone, record.source)) is None:
            db.add(CachedDNSZone(zone=zone, source=record.source, synced_at=now))
        write_audit(db, current_user.username, "create", "dns_record",
                    f"{record.name}/{record.record_type}",
                    f"{record.name} {record.record_type} {record.value}",
                    after=record.model_dump(exclude={"register_ptr"}))
        db.commit()
    except Exception as e:
        db.rollback()
        if ptr_added and ptr_record is not None:
            _undo_provider(target, ptr_record, "delete")
        _undo_provider(target, record, "delete")
        logger.error("DNS create_record failed: %s", e, exc_info=True)
        raise HTTPException(502, f"DNS record creation failed: {e}")
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
    if record.delete_ptr and record.record_type == "A" and target.supports_ptr:
        reverse_zone = find_reverse_zone(record.value, _zone_names(db, target))
        if reverse_zone is not None:
            ptr_record = build_ptr_record(record.value, record.name, reverse_zone, provider=record.source)

    try:
        target.delete_record(record)
    except Exception as e:
        logger.error("DNS %s delete_record: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))

    # PTR cleanup is best-effort: an absent or failed PTR delete (e.g. the record
    # was created outside its reverse zone) must never revert the A deletion.
    if ptr_record is not None:
        try:
            target.delete_record(ptr_record)
        except Exception as e:
            logger.warning("PTR delete (best-effort) failed for %s: %s", ptr_record.name, e)
        db.query(CRow).filter_by(
            name=ptr_record.name, record_type="PTR",
            zone=ptr_record.zone, source=record.source,
        ).delete()

    try:
        db.query(CRow).filter_by(
            name=record.name, record_type=record.record_type,
            value=record.value, zone=zone, source=record.source,
        ).delete()
        write_audit(db, current_user.username, "delete", "dns_record",
                    f"{record.name}/{record.record_type}",
                    f"{record.name} {record.record_type} {record.value}",
                    before=record.model_dump(exclude={"delete_ptr"}))
        db.commit()
    except Exception as e:
        db.rollback()
        # Cache write failed after the provider delete succeeded — re-add the A
        # record so provider and IPAM stay consistent.
        _undo_provider(target, record, "add")
        logger.error("DNS delete cache update failed: %s", e, exc_info=True)
        raise HTTPException(502, f"DNS record deletion failed: {e}")
