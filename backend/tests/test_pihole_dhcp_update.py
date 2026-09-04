"""DNS-DHCP-EDIT-001 P3 — PiholeDHCPProvider.update_reservation."""
from urllib.parse import quote

from app.providers.dhcp.pihole import PiholeDHCPProvider
from app.providers.dhcp.base import DHCPReservation


def _provider():
    p = PiholeDHCPProvider({"url": "http://pihole/", "password": "x"}, "pihole01")
    p.calls = []
    p._static_hosts_raw = lambda: ["aa:bb:cc:dd:ee:ff,10.0.0.5,old"]

    def fake_req(method, path, **kwargs):
        p.calls.append((method, path))
        return None

    p._req = fake_req
    return p


def test_update_reservation_deletes_old_entry_then_adds_new():
    p = _provider()
    old = DHCPReservation(scope_id="pihole", ip_address="10.0.0.5",
                          mac_address="aa:bb:cc:dd:ee:ff", name="old")
    new = DHCPReservation(scope_id="pihole", ip_address="10.0.0.5",
                          mac_address="aa:bb:cc:dd:ee:ff", name="new")
    p.update_reservation(old, new)
    methods_paths = p.calls
    assert methods_paths[0][0] == "DELETE"
    assert quote("aa:bb:cc:dd:ee:ff,10.0.0.5,old", safe="") in methods_paths[0][1]
    assert methods_paths[1][0] == "PUT"
    assert quote("aa:bb:cc:dd:ee:ff,10.0.0.5,new", safe="") in methods_paths[1][1]


def test_update_reservation_can_change_mac():
    p = _provider()
    old = DHCPReservation(scope_id="pihole", ip_address="10.0.0.5",
                          mac_address="aa:bb:cc:dd:ee:ff", name="host")
    new = DHCPReservation(scope_id="pihole", ip_address="10.0.0.5",
                          mac_address="11:22:33:44:55:66", name="host")
    p.update_reservation(old, new)
    put_call = next(c for c in p.calls if c[0] == "PUT")
    assert quote("11:22:33:44:55:66,10.0.0.5,host", safe="") in put_call[1]
