from typing import List

from ..models import Vlan


class Vlans:
    def __init__(self, transport):
        self._t = transport

    def list(self) -> List[Vlan]:
        return [Vlan(x) for x in self._t.request("GET", "/vlans")]

    def get(self, vlan_pk: int) -> Vlan:
        return Vlan(self._t.request("GET", f"/vlans/{vlan_pk}"))

    def create(self, **fields) -> Vlan:
        return Vlan(self._t.request("POST", "/vlans", json=fields))

    def update(self, vlan_pk: int, **fields) -> Vlan:
        return Vlan(self._t.request("PUT", f"/vlans/{vlan_pk}", json=fields))

    def delete(self, vlan_pk: int) -> None:
        self._t.request("DELETE", f"/vlans/{vlan_pk}")
