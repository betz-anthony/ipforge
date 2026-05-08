from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.address import IPAddress
from app.models.cache import CachedDHCPLease, CachedDNSRecord
from app.models.subnet import Subnet

router = APIRouter()

RESULT_LIMIT = 50


class SubnetResult(BaseModel):
    id: int
    name: str
    cidr: str
    ip_version: int
    description: str | None


class AddressResult(BaseModel):
    id: int
    address: str
    hostname: str | None
    status: str
    mac_address: str | None
    subnet_id: int


class LeaseResult(BaseModel):
    ip_address: str
    name: str | None
    mac_address: str | None
    scope_id: str
    source: str


class RecordResult(BaseModel):
    name: str
    record_type: str
    value: str
    zone: str
    source: str


class SearchResults(BaseModel):
    subnets:   list[SubnetResult]
    addresses: list[AddressResult]
    leases:    list[LeaseResult]
    records:   list[RecordResult]


@router.get("", response_model=SearchResults)
def search(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
):
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pat = f"%{escaped}%"

    subnets = (
        db.query(Subnet)
        .filter(
            Subnet.cidr.ilike(pat, escape="\\") |
            Subnet.name.ilike(pat, escape="\\") |
            Subnet.description.ilike(pat, escape="\\")
        )
        .limit(RESULT_LIMIT).all()
    )

    addresses = (
        db.query(IPAddress)
        .filter(
            IPAddress.address.ilike(pat, escape="\\") |
            IPAddress.hostname.ilike(pat, escape="\\") |
            IPAddress.mac_address.ilike(pat, escape="\\")
        )
        .limit(RESULT_LIMIT).all()
    )

    leases = (
        db.query(CachedDHCPLease)
        .filter(
            CachedDHCPLease.ip_address.ilike(pat, escape="\\") |
            CachedDHCPLease.name.ilike(pat, escape="\\") |
            CachedDHCPLease.mac_address.ilike(pat, escape="\\")
        )
        .limit(RESULT_LIMIT).all()
    )

    records = (
        db.query(CachedDNSRecord)
        .filter(
            CachedDNSRecord.name.ilike(pat, escape="\\") |
            CachedDNSRecord.value.ilike(pat, escape="\\")
        )
        .limit(RESULT_LIMIT).all()
    )

    return SearchResults(
        subnets=[
            SubnetResult(id=s.id, name=s.name, cidr=s.cidr,
                         ip_version=s.ip_version, description=s.description)
            for s in subnets
        ],
        addresses=[
            AddressResult(id=a.id, address=a.address, hostname=a.hostname,
                          status=a.status.value, mac_address=a.mac_address,
                          subnet_id=a.subnet_id)
            for a in addresses
        ],
        leases=[
            LeaseResult(ip_address=lease.ip_address, name=lease.name,
                        mac_address=lease.mac_address, scope_id=lease.scope_id,
                        source=lease.source)
            for lease in leases
        ],
        records=[
            RecordResult(name=r.name, record_type=r.record_type,
                         value=r.value, zone=r.zone, source=r.source)
            for r in records
        ],
    )
