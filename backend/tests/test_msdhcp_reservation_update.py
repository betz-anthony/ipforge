"""DNS-DHCP-EDIT-001 P3 — MSDHCPProvider.update_reservation."""
from app.providers.dhcp.msdhcp import MSDHCPProvider
from app.providers.dhcp.base import DHCPReservation


def _provider():
    p = MSDHCPProvider({"dhcp_server": "dc01", "winrm_host": "dc01"}, "msdhcp01")
    p.calls = []
    p._run = lambda ps: (p.calls.append(ps), "")[1]
    return p


def test_update_reservation_same_mac_uses_set_command():
    p = _provider()
    old = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="aa-bb-cc-dd-ee-ff", name="old", description="d1")
    new = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="aa-bb-cc-dd-ee-ff", name="new", description="d2")
    p.update_reservation(old, new)
    assert len(p.calls) == 1
    assert "Set-DhcpServerv4Reservation" in p.calls[0]
    assert "-Name 'new'" in p.calls[0]
    assert "-Description 'd2'" in p.calls[0]


def test_update_reservation_mac_change_falls_back_to_delete_add():
    p = _provider()
    old = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="aa-bb-cc-dd-ee-ff", name="host")
    new = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="11-22-33-44-55-66", name="host")
    p.update_reservation(old, new)
    assert len(p.calls) == 2
    assert "Remove-DhcpServerv4Reservation" in p.calls[0]
    assert "Add-DhcpServerv4Reservation" in p.calls[1]
    assert "-ClientId '11-22-33-44-55-66'" in p.calls[1]


def test_update_reservation_v6_duid_change_falls_back_to_delete_add():
    p = _provider()
    old = DHCPReservation(scope_id="2001:db8::/64", ip_address="2001:db8::5",
                          client_duid="00:01", iaid=1, name="host6")
    new = DHCPReservation(scope_id="2001:db8::/64", ip_address="2001:db8::5",
                          client_duid="00:02", iaid=1, name="host6")
    p.update_reservation(old, new)
    assert len(p.calls) == 2
    assert "Remove-DhcpServerv6Reservation" in p.calls[0]
    assert "Add-DhcpServerv6Reservation" in p.calls[1]
    assert "-ClientDuid '00:02'" in p.calls[1]
