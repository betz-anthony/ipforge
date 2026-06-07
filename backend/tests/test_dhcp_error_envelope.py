from unittest.mock import MagicMock, patch


def test_dhcp_add_provider_error_returns_envelope(client, db):
    prov = MagicMock()
    prov.source = "msdhcp"
    prov.add_reservation = MagicMock(side_effect=Exception("Connection timed out to dc01"))
    with patch("app.api.dhcp.get_dhcp_providers", return_value=[prov]):
        r = client.post("/api/dhcp/scopes/10.0.0.0/reservations", json={
            "scope_id": "10.0.0.0", "ip_address": "10.0.0.5",
            "mac_address": "aa:bb:cc:dd:ee:ff", "name": "host1"})
    assert r.status_code == 502
    d = r.json()["detail"]
    assert d["code"] == "provider_unreachable"
    assert d["step"] == "dhcp" and d["hint"]
