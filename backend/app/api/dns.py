import logging
from fastapi import APIRouter, HTTPException
from app.providers.registry import get_dns_providers
from app.providers.dns.base import DNSRecord

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/zones")
def list_zones():
    zones: list[str] = []
    for p in get_dns_providers():
        try:
            zones.extend(p.get_zones())
        except Exception as e:
            logger.error("DNS %s get_zones: %s", p.source, e, exc_info=True)
    return list(dict.fromkeys(zones))


@router.get("/zones/{zone}/records", response_model=list[DNSRecord])
def list_records(zone: str):
    records: list[DNSRecord] = []
    errors: list[str] = []
    for p in get_dns_providers():
        try:
            recs = p.get_records(zone)
            for r in recs:
                r.source = p.source
            records.extend(recs)
        except Exception as e:
            logger.error("DNS %s get_records(%s): %s", p.source, zone, e, exc_info=True)
            errors.append(f"{p.source}: {e}")
    if errors and not records:
        raise HTTPException(502, "; ".join(errors))
    return records


@router.post("/zones/{zone}/records", response_model=DNSRecord, status_code=201)
def create_record(zone: str, record: DNSRecord):
    record.zone = zone
    providers = get_dns_providers()
    target = next((p for p in providers if p.source == record.source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DNS provider configured")
    try:
        target.add_record(record)
        record.source = target.source
        return record
    except Exception as e:
        logger.error("DNS %s add_record: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))


@router.delete("/zones/{zone}/records", status_code=204)
def delete_record(zone: str, record: DNSRecord):
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
