import pytest

from app.providers.dhcp.isc import KeaDHCPProvider
from app.providers.dhcp.base import DHCPReservation


def _provider_with_stub(responses):
    """Build a Kea provider whose _cmd is stubbed.

    `responses` maps (command, service) -> arguments dict. Calls are recorded
    on provider.calls as (command, service, arguments).
    """
    p = KeaDHCPProvider({"url": "http://kea:8000/", "secret": ""}, "kea")
    p.calls = []

    def fake_cmd(command, service="dhcp4", arguments=None):
        p.calls.append((command, service, arguments))
        return responses.get((command, service), {})

    p._cmd = fake_cmd
    return p


def test_get_scopes_includes_v4_and_v6():
    p = _provider_with_stub({
        ("subnet4-list", "dhcp4"): {"subnets": [
            {"subnet": "10.0.0.0/24", "id": 1, "pools": [{"pool": "10.0.0.10 - 10.0.0.20"}]},
        ]},
        ("subnet6-list", "dhcp6"): {"subnets": [
            {"subnet": "2001:db8::/64", "id": 2, "pools": [{"pool": "2001:db8::10 - 2001:db8::20"}]},
        ]},
    })
    scopes = p.get_scopes()
    by_cidr = {s.scope_id: s for s in scopes}
    assert by_cidr["10.0.0.0/24"].ip_version == 4
    assert by_cidr["2001:db8::/64"].ip_version == 6
    assert by_cidr["2001:db8::/64"].start_range == "2001:db8::10"
    assert by_cidr["2001:db8::/64"].end_range == "2001:db8::20"


def test_get_leases_v6_routes_to_dhcp6():
    p = _provider_with_stub({
        ("subnet6-list", "dhcp6"): {"subnets": [{"subnet": "2001:db8::/64", "id": 2, "pools": []}]},
        ("reservation-get-all", "dhcp6"): {"hosts": [
            {"ip-addresses": ["2001:db8::5"], "duid": "00:01:02:03", "hostname": "res6"},
        ]},
        ("lease6-get-all", "dhcp6"): {"leases": [
            {"ip-address": "2001:db8::99", "duid": "0a:0b", "hostname": "lease6"},
        ]},
    })
    leases = p.get_leases("2001:db8::/64")
    ips = {l.ip_address for l in leases}
    assert ips == {"2001:db8::5", "2001:db8::99"}
    # all Kea calls for a v6 scope must target the dhcp6 service
    assert all(service == "dhcp6" for _, service, _ in p.calls)
    commands = {c for c, _, _ in p.calls}
    assert "lease6-get-all" in commands
    assert "reservation-get-all" in commands


def test_add_reservation_v6_uses_duid():
    p = _provider_with_stub({
        ("subnet6-list", "dhcp6"): {"subnets": [{"subnet": "2001:db8::/64", "id": 2, "pools": []}]},
        ("reservation-add", "dhcp6"): {},
    })
    p.add_reservation(DHCPReservation(
        scope_id="2001:db8::/64", ip_address="2001:db8::5",
        client_duid="00:01:02:03:04", name="host6",
    ))
    add_call = next(c for c in p.calls if c[0] == "reservation-add")
    _, service, args = add_call
    assert service == "dhcp6"
    host = args["reservation"]
    assert host["duid"] == "00:01:02:03:04"
    assert host["ip-addresses"] == ["2001:db8::5"]
    assert host["subnet-id"] == 2
    assert "hw-address" not in host


def test_add_reservation_v6_requires_duid():
    p = _provider_with_stub({
        ("subnet6-list", "dhcp6"): {"subnets": [{"subnet": "2001:db8::/64", "id": 2, "pools": []}]},
    })
    with pytest.raises(RuntimeError):
        p.add_reservation(DHCPReservation(
            scope_id="2001:db8::/64", ip_address="2001:db8::5", name="host6",
        ))


def test_add_reservation_v4_still_uses_hw_address():
    p = _provider_with_stub({
        ("subnet4-list", "dhcp4"): {"subnets": [{"subnet": "10.0.0.0/24", "id": 1, "pools": []}]},
        ("reservation-add", "dhcp4"): {},
    })
    p.add_reservation(DHCPReservation(
        scope_id="10.0.0.0/24", ip_address="10.0.0.5",
        mac_address="AA-BB-CC-DD-EE-FF", name="host4",
    ))
    _, service, args = next(c for c in p.calls if c[0] == "reservation-add")
    assert service == "dhcp4"
    host = args["reservation"]
    assert host["hw-address"] == "aa:bb:cc:dd:ee:ff"
    assert "duid" not in host


def test_update_reservation_name_v6_preserves_duid():
    p = _provider_with_stub({
        ("subnet6-list", "dhcp6"): {"subnets": [{"subnet": "2001:db8::/64", "id": 2, "pools": []}]},
        ("reservation-get-all", "dhcp6"): {"hosts": [
            {"ip-addresses": ["2001:db8::5"], "duid": "00:01:02:03", "hostname": "old"},
        ]},
        ("lease6-get-all", "dhcp6"): {"leases": []},
        ("reservation-del", "dhcp6"): {},
        ("reservation-add", "dhcp6"): {},
    })
    p.update_reservation_name("2001:db8::/64", "2001:db8::5", "newname")
    cmds = [c for c, _, _ in p.calls]
    assert cmds.index("reservation-del") < cmds.index("reservation-add")
    _, _, add_args = next(c for c in p.calls if c[0] == "reservation-add")
    host = add_args["reservation"]
    assert host["duid"] == "00:01:02:03"
    assert host["hostname"] == "newname"
    assert host["ip-addresses"] == ["2001:db8::5"]


def test_delete_reservation_v6_routes_to_dhcp6():
    p = _provider_with_stub({
        ("subnet6-list", "dhcp6"): {"subnets": [{"subnet": "2001:db8::/64", "id": 2, "pools": []}]},
        ("reservation-del", "dhcp6"): {},
    })
    p.delete_reservation("2001:db8::/64", "2001:db8::5")
    _, service, args = next(c for c in p.calls if c[0] == "reservation-del")
    assert service == "dhcp6"
    assert args["ip-address"] == "2001:db8::5"
    assert args["subnet-id"] == 2
