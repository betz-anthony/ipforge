"""DNS-DHCP-EDIT-001 P3 — MSDHCPProvider.update_reservation."""
from app.providers.dhcp.msdhcp import MSDHCPProvider
from app.providers.dhcp.base import DHCPReservation


def _provider():
    p = MSDHCPProvider({"dhcp_server": "dc01", "winrm_host": "dc01"}, "msdhcp01")
    p.calls = []
    p._run = lambda ps: (p.calls.append(ps), "")[1]
    return p


def test_update_reservation_mac_change_restores_old_on_add_failure():
    # The delete already committed on the live server before add_reservation
    # ever runs. If add fails (bad ClientId, WinRM blip, whatever), the old
    # reservation must be recreated instead of being left permanently gone.
    p = _provider()

    def _run(ps):
        p.calls.append(ps)
        if "11-22-33-44-55-66" in ps:
            raise RuntimeError("Add-DhcpServerv4Reservation failed")
        return ""
    p._run = _run

    old = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="aa-bb-cc-dd-ee-ff", name="host")
    new = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="11-22-33-44-55-66", name="host")

    try:
        p.update_reservation(old, new)
        assert False, "expected the original add failure to propagate"
    except RuntimeError:
        pass

    assert len(p.calls) == 3
    assert "Remove-DhcpServerv4Reservation" in p.calls[0]
    assert "Add-DhcpServerv4Reservation" in p.calls[1] and "11-22-33-44-55-66" in p.calls[1]
    assert "Add-DhcpServerv4Reservation" in p.calls[2] and "aa-bb-cc-dd-ee-ff" in p.calls[2]


def test_update_reservation_mac_change_logs_when_restore_also_fails(caplog):
    p = _provider()

    def _run(ps):
        p.calls.append(ps)
        if "Add-DhcpServerv4Reservation" in ps:
            raise RuntimeError("boom")
        return ""
    p._run = _run

    old = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="aa-bb-cc-dd-ee-ff", name="host")
    new = DHCPReservation(scope_id="10.0.0.0/24", ip_address="10.0.0.5",
                          mac_address="11-22-33-44-55-66", name="host")

    try:
        p.update_reservation(old, new)
        assert False, "expected the original add failure to propagate"
    except RuntimeError:
        pass

    assert len(p.calls) == 3  # delete, failed add(new), failed restore add(old)
    assert any("gone from the DHCP server" in r.message for r in caplog.records)


def test_add_reservation_v4_sends_dash_delimited_client_id():
    # Add-DhcpServerv4Reservation's -ClientId only accepts dash-delimited
    # hex — IPForge's own canonical MAC form (core.mac.normalize_mac) is
    # colon-delimited, and passing that straight through throws a
    # CimException ("not in valid format"), not a friendly error.
    p = _provider()
    reservation = DHCPReservation(scope_id="10.10.0.0/24", ip_address="10.10.0.152",
                                   mac_address="02:ec:02:3d:00:66", name="newvm")
    p.add_reservation(reservation)
    assert "-ClientId '02-ec-02-3d-00-66'" in p.calls[0]


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
    # Remove-DhcpServerv4Reservation has no -Force parameter — passing one
    # throws ParameterBindingException and aborts the whole mac-change edit.
    assert "-Force" not in p.calls[0]
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
