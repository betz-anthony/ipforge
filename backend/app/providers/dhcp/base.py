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
