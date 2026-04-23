import logging
from fastapi import APIRouter, HTTPException, Query
from app.providers.registry import get_dhcp_providers
from app.providers.dhcp.base import DHCPReservation, DHCPScope

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/scopes", response_model=list[DHCPScope])
def list_scopes():
    scopes: list[DHCPScope] = []
    errors: list[str] = []
    for p in get_dhcp_providers():
        try:
            s = p.get_scopes()
            for scope in s:
                scope.source = p.source
            scopes.extend(s)
        except Exception as e:
            logger.error("DHCP %s get_scopes: %s", p.source, e, exc_info=True)
            errors.append(f"{p.source}: {e}")
    if errors and not scopes:
        raise HTTPException(502, "; ".join(errors))
    return scopes


@router.get("/scopes/{scope_id}/leases", response_model=list[DHCPReservation])
def list_leases(scope_id: str, source: str = Query("")):
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DHCP provider configured")
    try:
        return target.get_leases(scope_id)
    except Exception as e:
        logger.error("DHCP %s get_leases(%s): %s", target.source, scope_id, e, exc_info=True)
        raise HTTPException(502, str(e))


@router.post("/scopes/{scope_id}/reservations", response_model=DHCPReservation, status_code=201)
def add_reservation(scope_id: str, reservation: DHCPReservation, source: str = Query("")):
    reservation.scope_id = scope_id
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DHCP provider configured")
    try:
        target.add_reservation(reservation)
        return reservation
    except Exception as e:
        logger.error("DHCP %s add_reservation: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))


@router.delete("/scopes/{scope_id}/reservations/{ip_address}", status_code=204)
def delete_reservation(scope_id: str, ip_address: str, source: str = Query("")):
    providers = get_dhcp_providers()
    target = next((p for p in providers if p.source == source), None) or (providers[0] if providers else None)
    if not target:
        raise HTTPException(502, "No DHCP provider configured")
    try:
        target.delete_reservation(scope_id, ip_address)
    except Exception as e:
        logger.error("DHCP %s delete_reservation: %s", target.source, e, exc_info=True)
        raise HTTPException(502, str(e))
