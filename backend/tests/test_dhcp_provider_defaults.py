from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation


class _MinimalProvider(DHCPProvider):
    """Implements only the abstract methods — proves the two new methods
    have usable defaults and don't force every provider to implement them."""
    source = "minimal"

    def get_scopes(self) -> list[DHCPScope]:
        return []

    def get_leases(self, scope_id: str) -> list[DHCPReservation]:
        return []

    def add_reservation(self, reservation: DHCPReservation) -> None:
        pass

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        pass

    def update_reservation_name(self, scope_id: str, ip_address: str, name: str) -> None:
        pass

    def update_reservation(self, old: DHCPReservation, new: DHCPReservation) -> None:
        pass


def test_get_scope_gateway_defaults_to_none():
    assert _MinimalProvider().get_scope_gateway("10.0.0.0/24") is None


def test_get_scope_exclusions_defaults_to_empty_list():
    assert _MinimalProvider().get_scope_exclusions("10.0.0.0/24") == []
