from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.cache import CachedDNSZone, CachedDNSRecord, CachedDHCPScope, CachedDHCPLease

router = APIRouter()


@router.get("")
def get_stats(db: Session = Depends(get_db)):
    dns_zones   = db.query(func.count(CachedDNSZone.zone)).scalar() or 0
    dns_records = db.query(func.count(CachedDNSRecord.id)).scalar() or 0
    dhcp_scopes = db.query(func.count(CachedDHCPScope.id)).scalar() or 0
    dhcp_leases = db.query(func.count(CachedDHCPLease.id)).scalar() or 0
    return {
        "dns_zones":   dns_zones,
        "dns_records": dns_records,
        "dhcp_scopes": dhcp_scopes,
        "dhcp_leases": dhcp_leases,
    }
