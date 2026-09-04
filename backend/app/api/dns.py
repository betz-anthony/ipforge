import logging
import re
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
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
from app.core.errors import raise_provider_error, provider_unconfigured
from app.core.pagination import paginate

logger = logging.getLogger(__name__)
router = APIRouter()


_DNS_NAME_RE = re.compile(r"^[A-Za-z0-9_.*@-]{1,255}$")
_VALID_RECORD_TYPES = {"A", "AAAA", "CNAME", "PTR", "MX", "TXT", "NS"}

DNS_SORT_MAP = {
    "name":        CRow.name,
    "record_type": CRow.record_type,
    "value":       CRow.value,
}


def _validate_name(v: str) -> str:
    v = v.strip()
    if not _DNS_NAME_RE.match(v):
        raise ValueError("name must be 1-255 chars: letters, digits, . _ - * @")
    return v


def _validate_record_type(v: str) -> str:
    if v not in _VALID_RECORD_TYPES:
        raise ValueError(f"record_type must be one of {sorted(_VALID_RECORD_TYPES)}")
    return v


def _validate_value(v: str) -> str:
    v = v.strip()
    if not v or len(v) > 512:
        raise ValueError("value must be 1-512 characters")
    if any(ord(c) < 32 for c in v):
        raise ValueError("value must not contain control characters")
    return v


class CreateRecordRequest(DNSRecord):
    register_ptr: bool = False

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("record_type")
    @classmethod
    def _check_record_type(cls, v: str) -> str:
        return _validate_record_type(v)

    @field_validator("value")
    @classmethod
    def _check_value(cls, v: str) -> str:
        return _validate_value(v)


class DeleteRecordRequest(DNSRecord):
    delete_ptr: bool = False


class UpdateRecordRequest(BaseModel):
    old: DNSRecord
    new: DNSRecord
    update_ptr: bool = False

    @field_validator("new")
    @classmethod
    def _check_new(cls, v: DNSRecord) -> DNSRecord:
        return v.model_copy(update={
            "name": _validate_name(v.name),
            "record_type": _validate_record_type(v.record_type),
            "value": _validate_value(v.value),
        })


class UpdateRecordResponse(DNSRecord):
    ptr_stale: bool = False


def _cached_zone_names(db: Session, source: str) -> list[str]:
    return [z for (z,) in db.query(CachedDNSZone.zone).filter_by(source=source)]


def _zone_names(db: Session, target) -> list[str]:
    """Reverse-zone candidates — cached zones, falling back to a live provider query."""
    cached = _cached_zone_names(db, target.source)
    return cached if cached else target.get_zones()


def _undo_provider(target, record: DNSRecord, op: str, reverse_to: DNSRecord | None = None) -> None:
    """Best-effort reversal of a provider mutation after a failed DB transaction."""
    try:
        if op == "delete":
            target.delete_record(record)
        elif op == "update":
            target.update_record(record, reverse_to)
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
def list_records(
    zone: str,
    q: str | None = None,
    sort: str = "",
    dir: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(CRow).filter(CRow.zone == zone)
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(
            CRow.name.ilike(pattern),
            CRow.value.ilike(pattern),
        ))
    result = paginate(query, limit=limit, offset=offset,
                      sort_map=DNS_SORT_MAP, sort=sort, dir=dir,
                      tiebreaker=CRow.id.asc())
    items = [
        {
            "name": r.name, "record_type": r.record_type, "value": r.value,
            "zone": r.zone, "ttl": r.ttl, "source": r.source,
            "synced_at": r.synced_at.isoformat() + "Z" if r.synced_at else None,
        }
        for r in result["items"]
    ]
    return {"items": items, "total": result["total"],
            "limit": result["limit"], "offset": result["offset"]}


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
        provider_unconfigured("dns")

    try:
        target.add_record(record)
        record.source = target.source
    except Exception as e:
        raise_provider_error(e, step="dns", user=current_user)

    now = utcnow()
    ptr_record = None
    ptr_added = False
    # PTR registration is auxiliary: only when the provider supports PTR and a
    # reverse zone exists. A PTR failure is logged but never blocks the A record.
    if record.register_ptr and record.record_type in ("A", "AAAA") and target.supports_ptr:
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


@router.put("/zones/{zone}/records", response_model=UpdateRecordResponse)
def update_record(
    zone: str,
    body: UpdateRecordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if body.update_ptr:
        raise HTTPException(400, "update_ptr is not yet supported (P2)")

    old, new = body.old, body.new
    if new.zone != old.zone:
        raise HTTPException(422, "zone cannot change on an edit — delete and recreate instead")
    if new.source != old.source:
        raise HTTPException(422, "source cannot change on an edit — delete and recreate instead")

    old.zone = zone
    new.zone = zone

    providers = get_dns_providers()
    target = next((p for p in providers if p.source == old.source), None) or (providers[0] if providers else None)
    if not target:
        provider_unconfigured("dns")

    row = db.query(CRow).filter_by(
        name=old.name, record_type=old.record_type, value=old.value,
        zone=zone, source=old.source,
    ).first()
    if row is None:
        raise HTTPException(404, "record not found")

    try:
        target.update_record(old, new)
    except Exception as e:
        raise_provider_error(e, step="dns", user=current_user)

    # P1 does not follow PTR through an edit; surface staleness so the UI/drift
    # can flag it instead of silently leaving a mismatched reverse record.
    ptr_stale = (
        new.record_type in ("A", "AAAA")
        and target.supports_ptr
        and find_reverse_zone(old.value, _zone_names(db, target)) is not None
    )

    now = utcnow()
    try:
        row.name = new.name
        row.record_type = new.record_type
        row.value = new.value
        row.ttl = new.ttl
        row.synced_at = now
        write_audit(db, current_user.username, "update", "dns_record",
                    f"{new.name}/{new.record_type}",
                    f"{old.name} {old.record_type} {old.value} -> {new.name} {new.record_type} {new.value}",
                    before=old.model_dump(), after=new.model_dump())
        db.commit()
    except Exception as e:
        db.rollback()
        _undo_provider(target, new, "update", reverse_to=old)
        logger.error("DNS update_record cache update failed: %s", e, exc_info=True)
        raise HTTPException(502, f"DNS record update failed: {e}")

    return UpdateRecordResponse(**new.model_dump(), ptr_stale=ptr_stale)


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
        provider_unconfigured("dns")

    ptr_record = None
    if record.delete_ptr and record.record_type in ("A", "AAAA") and target.supports_ptr:
        reverse_zone = find_reverse_zone(record.value, _zone_names(db, target))
        if reverse_zone is not None:
            ptr_record = build_ptr_record(record.value, record.name, reverse_zone, provider=record.source)

    try:
        target.delete_record(record)
    except Exception as e:
        raise_provider_error(e, step="dns", user=current_user)

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
