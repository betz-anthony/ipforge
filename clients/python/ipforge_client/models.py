from typing import Any, Optional


class Model:
    """Forward-compatible wrapper over a response dict. Known fields are exposed
    as typed properties; everything is reachable via .raw / item access, so a
    new API field never breaks the client."""

    def __init__(self, raw: dict):
        self.raw = dict(raw)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def __eq__(self, other) -> bool:
        return isinstance(other, Model) and self.raw == other.raw

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.raw!r})"


class Subnet(Model):
    @property
    def id(self) -> Optional[int]: return self.raw.get("id")
    @property
    def cidr(self) -> Optional[str]: return self.raw.get("cidr")
    @property
    def name(self) -> Optional[str]: return self.raw.get("name")
    @property
    def vlan_id(self) -> Optional[int]: return self.raw.get("vlan_id")
    @property
    def description(self) -> Optional[str]: return self.raw.get("description")


class Address(Model):
    @property
    def id(self) -> Optional[int]: return self.raw.get("id")
    @property
    def address(self) -> Optional[str]: return self.raw.get("address")
    @property
    def hostname(self) -> Optional[str]: return self.raw.get("hostname")
    @property
    def status(self) -> Optional[str]: return self.raw.get("status")
    @property
    def mac_address(self) -> Optional[str]: return self.raw.get("mac_address")
    @property
    def subnet_id(self) -> Optional[int]: return self.raw.get("subnet_id")


class Vlan(Model):
    @property
    def id(self) -> Optional[int]: return self.raw.get("id")
    @property
    def vlan_id(self) -> Optional[int]: return self.raw.get("vlan_id")
    @property
    def name(self) -> Optional[str]: return self.raw.get("name")


class DNSRecord(Model):
    @property
    def name(self) -> Optional[str]: return self.raw.get("name")
    @property
    def record_type(self) -> Optional[str]: return self.raw.get("record_type")
    @property
    def value(self) -> Optional[str]: return self.raw.get("value")
    @property
    def zone(self) -> Optional[str]: return self.raw.get("zone")
    @property
    def ttl(self) -> Optional[int]: return self.raw.get("ttl")


class DHCPLease(Model):
    @property
    def ip_address(self) -> Optional[str]: return self.raw.get("ip_address")
    @property
    def mac_address(self) -> Optional[str]: return self.raw.get("mac_address")
    @property
    def name(self) -> Optional[str]: return self.raw.get("name")
    @property
    def scope_id(self) -> Optional[str]: return self.raw.get("scope_id")


class DriftItem(Model):
    @property
    def id(self) -> Optional[int]: return self.raw.get("id")
    @property
    def category(self) -> Optional[str]: return self.raw.get("category")
    @property
    def severity(self) -> Optional[str]: return self.raw.get("severity")


class DiscoveryEndpoint(Model):
    @property
    def ip(self) -> Optional[str]: return self.raw.get("ip")
    @property
    def mac(self) -> Optional[str]: return self.raw.get("mac")
    @property
    def port_name(self) -> Optional[str]: return self.raw.get("port_name")


class AuditEntry(Model):
    @property
    def id(self) -> Optional[int]: return self.raw.get("id")
    @property
    def action(self) -> Optional[str]: return self.raw.get("action")
    @property
    def resource_type(self) -> Optional[str]: return self.raw.get("resource_type")
    @property
    def username(self) -> Optional[str]: return self.raw.get("username")
