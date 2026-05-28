from abc import ABC, abstractmethod

from pydantic import BaseModel


class Endpoint(BaseModel):
    ip: str | None = None
    mac: str
    ifindex: int | None = None
    port_name: str | None = None
    vlan: int | None = None


class DiscoverySource(ABC):
    source: str = ""

    @abstractmethod
    def poll(self) -> list[Endpoint]: ...
