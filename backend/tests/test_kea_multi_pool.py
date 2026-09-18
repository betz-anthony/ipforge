from unittest.mock import patch
from app.providers.dhcp.isc import KeaDHCPProvider


def _provider():
    return KeaDHCPProvider({"url": "http://kea:8000"}, "kea01")


_TWO_POOL_SUBNET = {
    "id": 1,
    "subnet": "10.10.0.0/24",
    "pools": [
        {"pool": "10.10.0.10-10.10.0.50"},
        {"pool": "10.10.0.52-10.10.0.200"},
    ],
}


def test_get_scopes_start_end_span_all_pools():
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[_TWO_POOL_SUBNET]):
        scopes = p._scopes_for_service("dhcp4")
    assert len(scopes) == 1
    assert scopes[0].start_range == "10.10.0.10"
    assert scopes[0].end_range == "10.10.0.200"


def test_get_scope_pools_returns_every_pool():
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[_TWO_POOL_SUBNET]):
        pools = p.get_scope_pools("10.10.0.0/24")
    assert pools == [("10.10.0.10", "10.10.0.50"), ("10.10.0.52", "10.10.0.200")]


def test_get_scope_pools_single_pool_unchanged():
    single = {"id": 2, "subnet": "10.20.0.0/24", "pools": [{"pool": "10.20.0.10-10.20.0.100"}]}
    p = _provider()
    with patch.object(p, "_get_subnets", return_value=[single]):
        pools = p.get_scope_pools("10.20.0.0/24")
    assert pools == [("10.20.0.10", "10.20.0.100")]
