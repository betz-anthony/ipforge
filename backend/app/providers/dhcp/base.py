from abc import ABC, abstractmethod
from pydantic import BaseModel


class DHCPScope(BaseModel):
    scope_id: str
    name: str
    subnet_mask: str
    start_range: str
    end_range: str
    description: str = ""
    active: bool = True


class DHCPReservation(BaseModel):
    scope_id: str
    ip_address: str
    mac_address: str
    name: str
    description: str = ""


class DHCPProvider(ABC):
    @abstractmethod
    def get_scopes(self) -> list[DHCPScope]: ...

    @abstractmethod
    def get_leases(self, scope_id: str) -> list[DHCPReservation]: ...

    @abstractmethod
    def add_reservation(self, reservation: DHCPReservation) -> None: ...

    @abstractmethod
    def delete_reservation(self, scope_id: str, ip_address: str) -> None: ...
