from app.mcp_client import IPForgeClient


def _client(responses, calls):
    c = IPForgeClient("http://ipf", "ipfg_tok")

    def fake_req(method, path, params=None, json=None):
        calls.append((method, path, params, json))
        return responses.get((method, path), {})

    c._req = fake_req
    return c


def test_list_subnets():
    calls = []
    c = _client({("GET", "/subnets"): [{"id": 1, "cidr": "10.0.0.0/24"}]}, calls)
    assert c.list_subnets()[0]["cidr"] == "10.0.0.0/24"
    assert calls[0][:2] == ("GET", "/subnets")


def test_list_addresses_filters():
    calls = []
    c = _client({("GET", "/addresses"): {"items": [], "total": 0, "limit": 200, "offset": 0}}, calls)
    result = c.list_addresses(subnet_id=3, tag="prod")
    assert result == []
    assert calls[0][0] == "GET" and calls[0][1] == "/addresses"
    assert calls[0][2]["subnet_id"] == 3
    assert calls[0][2]["tag"] == "prod"
    assert calls[0][2]["limit"] == 200


def test_find_free_ip_returns_first_free():
    calls = []
    resp = {("GET", "/subnets/1/map"): {"too_large": False, "cells": [
        {"ip": "10.0.0.1", "status": "assigned"},
        {"ip": "10.0.0.2", "status": "free"},
        {"ip": "10.0.0.3", "status": "free"},
    ]}}
    c = _client(resp, calls)
    assert c.find_free_ip(1) == "10.0.0.2"


def test_find_free_ip_too_large():
    c = _client({("GET", "/subnets/1/map"): {"too_large": True, "host_count": 99999}}, [])
    assert c.find_free_ip(1) is None


def test_allocate_ip_posts_body():
    calls = []
    c = _client({("POST", "/subnets/1/allocate"): {"address": "10.0.0.2", "is_new": True}}, calls)
    c.allocate_ip(1, "web-01", mac="aa:bb:cc:dd:ee:ff", register_dns=True, dns_zone="example.com")
    m, p, params, body = calls[0]
    assert (m, p) == ("POST", "/subnets/1/allocate")
    assert body["hostname"] == "web-01" and body["mac_address"] == "aa:bb:cc:dd:ee:ff"
    assert body["register_dns"] is True and body["dns_zone"] == "example.com"


def test_tag_address_unions_existing():
    calls = []
    resp = {
        ("GET", "/addresses/by-ip/10.0.0.5"): {"id": 7, "tags": ["keep"]},
        ("PUT", "/addresses/7"): {},
    }
    c = _client(resp, calls)
    c.tag_address("10.0.0.5", ["new"])
    put = next(x for x in calls if x[0] == "PUT")
    assert put[1] == "/addresses/7"
    assert set(put[3]["tags"]) == {"keep", "new"}


def test_resolve_drift_posts():
    calls = []
    c = _client({("POST", "/drift/9/resolve"): {"resolved": True}}, calls)
    c.resolve_drift(9, action="import")
    assert calls[0][:2] == ("POST", "/drift/9/resolve")
    assert calls[0][3] == {"action": "import"}


def test_ip_history():
    calls = []
    c = _client({("GET", "/addresses/by-ip/10.0.0.5/history"): {"ip": "10.0.0.5", "timeline": []}}, calls)
    assert c.ip_history("10.0.0.5")["ip"] == "10.0.0.5"


def test_allocate_ip_without_pool_omits_field():
    calls = []
    c = _client({("POST", "/subnets/1/allocate"): {"address": "10.0.0.2", "pool": None}}, calls)
    c.allocate_ip(1, "web-01")
    assert "pool" not in calls[0][3]


def test_allocate_ip_with_pool_sends_field():
    calls = []
    c = _client({("POST", "/subnets/1/allocate"): {"address": "10.10.3.2", "pool": "linux"}}, calls)
    out = c.allocate_ip(1, "lx-01", pool="linux")
    assert calls[0][3]["pool"] == "linux"
    assert out["address"] == "10.10.3.2"


def test_allocate_ip_pool_ignored_by_old_server_raises():
    import pytest
    from app.mcp_client import PoolNotSupportedError
    calls = []
    c = _client({("POST", "/subnets/1/allocate"): {"address": "10.10.0.2"}}, calls)
    with pytest.raises(PoolNotSupportedError) as exc:
        c.allocate_ip(1, "lx-01", pool="linux")
    assert "10.10.0.2" in str(exc.value)


def test_list_pools():
    calls = []
    c = _client({("GET", "/subnets/2/pools"): [{"name": "linux"}]}, calls)
    assert c.list_pools(2)[0]["name"] == "linux"
    assert calls[0][:2] == ("GET", "/subnets/2/pools")
