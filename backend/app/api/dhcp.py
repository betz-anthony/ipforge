from fastapi import APIRouter, Depends, HTTPException
from app.providers.registry import get_dhcp_provider
from app.providers.dhcp.base import DHCPProvider, DHCPReservation, DHCPScope

router = APIRouter()


@router.get("/scopes", response_model=list[DHCPScope])
def list_scopes(provider: DHCPProvider = Depends(get_dhcp_provider)):
    try:
        return provider.get_scopes()
    except Exception as e:
        raise HTTPException(502, str(e))


@router.get("/scopes/{scope_id}/leases", response_model=list[DHCPReservation])
def list_leases(scope_id: str, provider: DHCPProvider = Depends(get_dhcp_provider)):
    try:
        return provider.get_leases(scope_id)
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/scopes/{scope_id}/reservations", response_model=DHCPReservation, status_code=201)
def add_reservation(scope_id: str, reservation: DHCPReservation, provider: DHCPProvider = Depends(get_dhcp_provider)):
    reservation.scope_id = scope_id
    try:
        provider.add_reservation(reservation)
        return reservation
    except Exception as e:
        raise HTTPException(502, str(e))


@router.delete("/scopes/{scope_id}/reservations/{ip_address}", status_code=204)
def delete_reservation(scope_id: str, ip_address: str, provider: DHCPProvider = Depends(get_dhcp_provider)):
    try:
        provider.delete_reservation(scope_id, ip_address)
    except Exception as e:
        raise HTTPException(502, str(e))
