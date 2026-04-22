from fastapi import APIRouter, Depends, HTTPException
from app.providers.registry import get_dns_provider
from app.providers.dns.base import DNSProvider, DNSRecord

router = APIRouter()


@router.get("/zones")
def list_zones(provider: DNSProvider = Depends(get_dns_provider)):
    try:
        return provider.get_zones()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/zones/{zone}/records", response_model=list[DNSRecord])
def list_records(zone: str, provider: DNSProvider = Depends(get_dns_provider)):
    try:
        return provider.get_records(zone)
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/zones/{zone}/records", response_model=DNSRecord, status_code=201)
def create_record(zone: str, record: DNSRecord, provider: DNSProvider = Depends(get_dns_provider)):
    record.zone = zone
    try:
        provider.add_record(record)
        return record
    except Exception as e:
        raise HTTPException(502, str(e))


@router.delete("/zones/{zone}/records", status_code=204)
def delete_record(zone: str, record: DNSRecord, provider: DNSProvider = Depends(get_dns_provider)):
    record.zone = zone
    try:
        provider.delete_record(record)
    except Exception as e:
        raise HTTPException(502, str(e))
