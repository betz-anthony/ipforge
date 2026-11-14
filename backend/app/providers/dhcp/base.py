from abc import ABC, abstractmethod
from pydantic import BaseModel


class DHCPScope(BaseModel):
    scope_id: str
    name: str
    subnet_mask: str       # prefix length string (e.g. "/64") for IPv6 scopes
    start_range: str
    end_range: str
    description: str = ""
    active: bool = True
    ip_version: int = 4
    source: str = ""
    # Admin-set opt-out (never populated by a provider itself — set by the
    # API layer from DHCPScopeReservedSyncExclusion). False means this
    # scope's gateway/exclusions are withheld from Reserved Ranges sync.
    sync_reserved_ranges: bool = True
    # Admin-set opt-out for subnet auto-creation (API layer, like the above).
    auto_create_subnet: bool = True
    # Scope-wide pool utilization, computed by the API layer from the lease
    # cache (never a provider field). None when it can't be computed (IPv6 or
    # no pool range).
    pool_size: int | None = None
    pool_used: int | None = None
    # Every cached reservation/lease in the scope, unfiltered (any IP version).
    lease_count: int = 0


class DHCPReservation(BaseModel):
    scope_id: str = ""     # overwritten by path param in add_reservation route
    ip_address: str
    mac_address: str = ""  # IPv4
    client_duid: str = ""  # IPv6
    iaid: int = 0          # IPv6
    name: str
    description: str = ""


class DHCPProvider(ABC):
    source: str = ""

    @abstractmethod
    def get_scopes(self) -> list[DHCPScope]: ...

    @abstractmethod
    def get_leases(self, scope_id: str) -> list[DHCPReservation]: ...

    @abstractmethod
    def add_reservation(self, reservation: DHCPReservation) -> None: ...

    @abstractmethod
    def delete_reservation(self, scope_id: str, ip_address: str) -> None: ...

    @abstractmethod
    def update_reservation_name(self, scope_id: str, ip_address: str, name: str) -> None: ...

    @abstractmethod
    def update_reservation(self, old: DHCPReservation, new: DHCPReservation) -> None: ...

    def get_scope_gateway(self, scope_id: str) -> str | None:
        """The scope's configured gateway/router IP, if the provider exposes
        one. Default: not supported by this provider."""
        return None

    def get_scope_exclusions(self, scope_id: str) -> list[tuple[str, str]]:
        """(start_ip, end_ip) ranges excluded from dynamic assignment within
        this scope, if the provider has that concept. Default: not
        supported by this provider."""
        return []
