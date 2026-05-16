import ipaddress
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import require_operator
from app.core.audit import write_audit
from app.database import get_db
from app.models.address import IPAddress, AddressStatus
from app.models.subnet import Subnet
from app.models.user import User
from app.providers.registry import get_dns_providers, get_dhcp_providers
from app.providers.dns.base import DNSRecord
from app.providers.dhcp.base import DHCPReservation

router = APIRouter()

_INELIGIBLE = {
    AddressStatus.reserved,
    AddressStatus.assigned,
    AddressStatus.deprecated,
    AddressStatus.discovered,
}


class AllocateRequest(BaseModel):
    hostname: str
    description: str | None = None
    mac_address: str | None = None
    notes: str | None = None
    register_dns: bool = False
    register_dhcp: bool = False
    dns_zone: str | None = None
    dns_provider: str | None = None
    dhcp_provider: str | None = None


def _find_candidate(db: Session, subnet_id: int, cidr: str) -> str | None:
    taken = {
        row.address
        for row in db.query(IPAddress.address).filter(
            IPAddress.subnet_id == subnet_id,
            IPAddress.status.in_(_INELIGIBLE),
        )
    }
    for ip in ipaddress.ip_network(cidr, strict=False).hosts():
        s = str(ip)
        if s.endswith(".0") or s.endswith(".1") or s.endswith(".255"):  # skip gateway, broadcast, and network-like addresses
            continue
        if s in taken:
            continue
        return s
    return None


def _resolve_provider(request_name: str | None, subnet_default: str | None, providers: list):
    target = request_name or subnet_default
    if target:
        return next((p for p in providers if p.source == target), None)
    return providers[0] if providers else None


def _find_dhcp_scope(provider, ip_address: str) -> str | None:
    target = ipaddress.ip_address(ip_address)  # ValueError if bad IP
    for scope in provider.get_scopes():
        try:
            start = ipaddress.ip_address(scope.start_range)
            end   = ipaddress.ip_address(scope.end_range)
            if start <= target <= end:
                return scope.scope_id
        except ValueError:
            continue
    return None


@router.post("/{subnet_id}/allocate")
def allocate_ip(
    subnet_id: int,
    body: AllocateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    hostname = (body.hostname or "").strip().lower()
    if not hostname:
        raise HTTPException(422, "hostname is required")

    subnet = db.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(404, "Subnet not found")

    dns_prov = dhcp_prov = None

    if body.register_dns:
        if not (body.dns_zone or "").strip():
            raise HTTPException(422, "dns_zone is required when register_dns is true")
        dns_prov = _resolve_provider(body.dns_provider, subnet.dns_provider_name, get_dns_providers())
        if dns_prov is None:
            raise HTTPException(400, "No DNS provider available")

    if body.register_dhcp:
        dhcp_prov = _resolve_provider(body.dhcp_provider, subnet.dhcp_provider_name, get_dhcp_providers())
        if dhcp_prov is None:
            raise HTTPException(400, "No DHCP provider available")

    existing = (
        db.query(IPAddress)
        .filter(
            IPAddress.subnet_id == subnet_id,
            func.lower(IPAddress.hostname) == hostname,
            IPAddress.status != AddressStatus.deprecated,
        )
        .first()
    )
    is_new = existing is None

    if existing:
        if body.mac_address and not existing.mac_address:
            existing.mac_address = body.mac_address
            db.flush()
        addr = existing
    else:
        if body.register_dhcp and not body.mac_address:
            raise HTTPException(422, "mac_address is required when register_dhcp is true")
        candidate = _find_candidate(db, subnet_id, subnet.cidr)
        if candidate is None:
            raise HTTPException(409, "subnet exhausted")
        addr = db.query(IPAddress).filter_by(address=candidate).first()
        if addr:
            addr.hostname    = hostname
            addr.status      = AddressStatus.reserved
            addr.mac_address = body.mac_address
            addr.description = body.description
            addr.notes       = body.notes
        else:
            addr = IPAddress(
                address=candidate, subnet_id=subnet_id,
                hostname=hostname, status=AddressStatus.reserved,
                mac_address=body.mac_address,
                description=body.description, notes=body.notes,
            )
            db.add(addr)
        db.flush()

    dns_registered = dhcp_registered = False

    if body.register_dns and dns_prov:
        record = DNSRecord(
            name=hostname, record_type="A",
            value=addr.address, zone=body.dns_zone or "",
        )
        try:
            dns_prov.add_record(record)
            dns_registered = True
        except Exception as exc:
            if is_new:
                db.rollback()
            raise HTTPException(502, f"DNS registration failed: {exc}")

    if body.register_dhcp and dhcp_prov:
        try:
            scope_id = _find_dhcp_scope(dhcp_prov, addr.address)
        except Exception as exc:
            if is_new:
                if dns_registered and dns_prov:
                    try:
                        dns_prov.delete_record(DNSRecord(
                            name=hostname, record_type="A",
                            value=addr.address, zone=body.dns_zone or "",
                        ))
                    except Exception:
                        pass
                db.rollback()
            raise HTTPException(502, f"DHCP provider error fetching scopes: {exc}")
        if scope_id is None:
            if is_new:
                if dns_registered and dns_prov:
                    try:
                        dns_prov.delete_record(DNSRecord(
                            name=hostname, record_type="A",
                            value=addr.address, zone=body.dns_zone or "",
                        ))
                    except Exception:
                        pass
                db.rollback()
            raise HTTPException(400, f"No DHCP scope found containing {addr.address}")
        reservation = DHCPReservation(
            scope_id=scope_id,
            ip_address=addr.address,
            mac_address=body.mac_address or (addr.mac_address or ""),
            name=hostname,
        )
        try:
            dhcp_prov.add_reservation(reservation)
            dhcp_registered = True
        except Exception as exc:
            if is_new:
                if dns_registered and dns_prov:
                    try:
                        dns_prov.delete_record(DNSRecord(
                            name=hostname, record_type="A",
                            value=addr.address, zone=body.dns_zone or "",
                        ))
                    except Exception:
                        pass
                db.rollback()
            raise HTTPException(502, f"DHCP registration failed: {exc}")

    if is_new:
        write_audit(db, current_user.username, "create", "address", str(addr.id),
                    f"{addr.address} (allocation)",
                    after={"address": addr.address, "hostname": hostname})
    db.commit()

    return JSONResponse(
        status_code=201 if is_new else 200,
        content={
            "id":              addr.id,
            "address":         addr.address,
            "subnet_id":       subnet_id,
            "subnet_cidr":     subnet.cidr,
            "hostname":        addr.hostname,
            "status":          addr.status.value,
            "mac_address":     addr.mac_address,
            "dns_registered":  dns_registered,
            "dhcp_registered": dhcp_registered,
            "is_new":          is_new,
        },
    )
