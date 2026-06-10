from ipforge_client.resources.dhcp import DHCP


def test_list_leases_paginated(fake):
    fake.set("GET", "/dhcp/scopes/scope1/leases",
             {"items": [{"ip_address": "10.0.0.10", "name": "web"}],
              "total": 1, "limit": 200, "offset": 0})
    out = list(DHCP(fake).list_leases("scope1", q="web"))
    assert out[0].ip_address == "10.0.0.10"
    assert fake.calls[0][2]["q"] == "web"


def test_add_reservation_with_source(fake):
    fake.set("POST", "/dhcp/scopes/scope1/reservations", {"ip_address": "10.0.0.5"})
    DHCP(fake).add_reservation("scope1", source="keadhcp",
                               ip_address="10.0.0.5", mac_address="aa:bb:cc:dd:ee:ff", name="x")
    m, p, params, body = fake.calls[0]
    assert (m, p) == ("POST", "/dhcp/scopes/scope1/reservations")
    assert params == {"source": "keadhcp"}
    assert body["ip_address"] == "10.0.0.5"


def test_delete_reservation(fake):
    DHCP(fake).delete_reservation("scope1", "10.0.0.5")
    assert fake.calls[0][:2] == ("DELETE", "/dhcp/scopes/scope1/reservations/10.0.0.5")
