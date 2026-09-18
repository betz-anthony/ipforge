from unittest.mock import patch, MagicMock
from app.providers.dhcp.isc import KeaDHCPProvider


def _provider():
    return KeaDHCPProvider({"url": "http://kea:8000"}, "kea01")


def _subnet(pools, option_data=None):
    return {
        "id": 1, "subnet": "10.10.0.0/24",
        "pools": [{"pool": p} for p in pools],
        "option-data": option_data or [],
    }


def test_get_scope_gateway_from_routers_option():
    s = _subnet(["10.10.0.10-10.10.0.200"], option_data=[
        {"name": "routers", "code": 3, "data": "10.10.0.1"},
    ])
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[s]):
        assert p.get_scope_gateway("10.10.0.0/24") == "10.10.0.1"


def test_get_scope_gateway_none_when_no_routers_option():
    s = _subnet(["10.10.0.10-10.10.0.200"])
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[s]):
        assert p.get_scope_gateway("10.10.0.0/24") is None


def test_get_scope_exclusions_gap_before_and_after_pool():
    # Pool 10.10.0.10-.200 inside /24 (hosts .1-.254): excludes .1-.9 and .201-.254.
    s = _subnet(["10.10.0.10-10.10.0.200"])
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[s]):
        gaps = p.get_scope_exclusions("10.10.0.0/24")
    assert gaps == [("10.10.0.1", "10.10.0.9"), ("10.10.0.201", "10.10.0.254")]


def test_get_scope_exclusions_gap_between_two_pools():
    s = _subnet(["10.10.0.10-10.10.0.50", "10.10.0.52-10.10.0.200"])
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[s]):
        gaps = p.get_scope_exclusions("10.10.0.0/24")
    assert ("10.10.0.51", "10.10.0.51") in gaps


def test_get_scope_exclusions_empty_when_no_pools():
    s = _subnet([])
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[s]):
        assert p.get_scope_exclusions("10.10.0.0/24") == []


def test_get_scope_exclusions_empty_for_oversized_subnet_even_with_pools():
    # A /16 with a small pool would otherwise derive exclusion ranges spanning
    # tens of thousands of addresses — those get individually materialized by
    # SubnetRange consumers (reserved_ip_set, allocation candidate search),
    # which don't expect a range that large. Guard bails before that happens,
    # and skips the get_scope_pools() HTTP round-trip entirely since the
    # decision doesn't depend on what it would return.
    p = _provider()
    mock_get_subnets = MagicMock(return_value=[_subnet(["10.10.0.10-10.10.0.200"])])
    with patch.object(p, "_get_subnets", mock_get_subnets):
        gaps = p.get_scope_exclusions("10.10.0.0/16")
    assert gaps == []
    mock_get_subnets.assert_not_called()


def test_get_scope_exclusions_small_subnet_still_derives_gaps():
    # Regression check: the size guard must not affect the already-covered
    # small-subnet case.
    s = _subnet(["10.10.0.10-10.10.0.200"])
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[s]):
        gaps = p.get_scope_exclusions("10.10.0.0/24")
    assert gaps == [("10.10.0.1", "10.10.0.9"), ("10.10.0.201", "10.10.0.254")]
