"""Regression: MSDHCPProvider._get_v4_leases() stored Get-DhcpServerv4Lease's
raw ClientId as mac_address unconditionally. ClientId is the DHCP option-61
client identifier — usually the 6-byte hardware MAC, but a client can send a
DUID-based client-id instead (newer Windows guest OSes commonly do for IPv4),
which is a different shape entirely (18+ bytes, not 6). Storing that verbatim
in a field labeled mac_address is actively wrong, not just cosmetic."""
import json

from app.providers.dhcp.msdhcp import MSDHCPProvider


def _provider():
    p = MSDHCPProvider({"dhcp_server": "dc01", "winrm_host": "dc01"}, "msdhcp01")
    return p


def test_get_v4_leases_accepts_a_real_mac():
    p = _provider()
    p._run = lambda ps: json.dumps({
        "IPAddress": {"IPAddressToString": "10.0.0.5"},
        "ClientId": "02-3d-00-66-00-01",
        "HostName": "host1",
    })
    leases = p.get_leases("10.0.0.0/24")
    assert leases[0].mac_address == "02-3d-00-66-00-01"


def test_get_v4_leases_blanks_a_duid_shaped_client_id():
    p = _provider()
    p._run = lambda ps: json.dumps({
        "IPAddress": {"IPAddressToString": "10.0.0.9"},
        # DUID-based client-id: not a 6-byte MAC.
        "ClientId": "02-3d-00-66-00-01-00-01-32-29-b3-92-00-15-5d-01-3f-3e",
        "HostName": "newvm",
    })
    leases = p.get_leases("10.0.0.0/24")
    assert leases[0].mac_address == ""
