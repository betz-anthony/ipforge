from unittest.mock import patch, MagicMock
from app.providers.dhcp.pihole import PiholeDHCPProvider


def _provider():
    return PiholeDHCPProvider({"url": "https://pihole.example.com", "password": "x"}, "pihole01")


def test_get_scope_gateway_returns_router_value():
    p = _provider()
    with patch.object(p, "_dhcp_cfg", return_value={"router": "10.10.0.1"}):
        assert p.get_scope_gateway("pihole") == "10.10.0.1"


def test_get_scope_gateway_none_when_unset():
    p = _provider()
    with patch.object(p, "_dhcp_cfg", return_value={"router": ""}):
        assert p.get_scope_gateway("pihole") is None


def test_get_scope_exclusions_not_overridden():
    # Confirms Pi-hole deliberately has no exclusion concept — inherits the
    # ABC default rather than raising or fabricating one.
    p = _provider()
    assert p.get_scope_exclusions("pihole") == []
