from abc import ABC, abstractmethod
from pydantic import BaseModel


class DNSRecord(BaseModel):
    name: str
    record_type: str
    value: str
    zone: str = ""
    ttl: int = 3600
    source: str = ""


class DNSProvider(ABC):
    source: str = ""
    @abstractmethod
    def get_zones(self) -> list[str]: ...

    @abstractmethod
    def get_records(self, zone: str) -> list[DNSRecord]: ...

    @abstractmethod
    def add_record(self, record: DNSRecord) -> None: ...

    @abstractmethod
    def delete_record(self, record: DNSRecord) -> None: ...

    @abstractmethod
    def update_record(self, old: DNSRecord, new: DNSRecord) -> None: ...
