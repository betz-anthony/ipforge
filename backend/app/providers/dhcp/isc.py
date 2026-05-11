import requests
from app.config import settings
from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation

# ISC Kea DHCP provider via Kea Control Agent REST API.
# Requires: Kea Control Agent running (default port 8000).
# Docs: https://kea.readthedocs.io/en/latest/arm/ctrl-channel.html


class KeaDHCPProvider(DHCPProvider):
    source = "keadhcp"

    def _cmd(self, command: str, service: str = "dhcp4", arguments: dict | None = None) -> dict:
        body: dict = {"command": command, "service": [service]}
        if arguments:
            body["arguments"] = arguments

        auth = ("kea", settings.kea_secret) if settings.kea_secret else None
        r = requests.post(settings.kea_url, json=body, auth=auth, timeout=10)
        r.raise_for_status()

        result = r.json()
        if isinstance(result, list):
            result = result[0]
        if result.get("result") not in (0, 3):  # 3 = empty/not found, still ok for listing
            raise RuntimeError(result.get("text", "Kea command failed"))
        return result.get("arguments", {})

    def _get_subnets(self) -> list[dict]:
        # subnet4-list requires subnet_cmds hook; fall back to config-get if unavailable
        try:
            return self._cmd("subnet4-list").get("subnets", [])
        except RuntimeError as e:
            if "not supported" in str(e).lower():
                cfg = self._cmd("config-get")
                return cfg.get("Dhcp4", {}).get("subnet4", [])
            raise

    def _subnet_id(self, scope_id: str) -> int:
        for s in self._get_subnets():
            if s["subnet"] == scope_id:
                return int(s["id"])
        raise RuntimeError(f"Subnet {scope_id!r} not found in Kea")

    def get_scopes(self) -> list[DHCPScope]:
        subnets = self._get_subnets()
        scopes: list[DHCPScope] = []
        for s in subnets:
            pools = s.get("pools", [])
            pool_str = pools[0].get("pool", "") if pools else ""
            start = end = ""
            if " - " in pool_str:
                start, end = [p.strip() for p in pool_str.split(" - ", 1)]
            scopes.append(DHCPScope(
                scope_id=s["subnet"],
                name=s.get("shared-network-name") or s["subnet"],
                subnet_mask="",
                start_range=start,
                end_range=end,
                description=f"ID: {s.get('id', '')}",
                active=True,
            ))
        return scopes

    def get_leases(self, scope_id: str) -> list[DHCPReservation]:
        data = self._cmd("lease4-get-all")
        leases = data.get("leases", [])
        return [
            DHCPReservation(
                scope_id=scope_id,
                ip_address=l.get("ip-address", ""),
                mac_address=l.get("hw-address", ""),
                name=l.get("hostname", ""),
            )
            for l in leases
        ]

    def add_reservation(self, reservation: DHCPReservation) -> None:
        self._cmd("reservation-add", arguments={
            "reservation": {
                "ip-address": reservation.ip_address,
                "hw-address": reservation.mac_address,
                "hostname": reservation.name,
                "subnet-id": self._subnet_id(reservation.scope_id),
            }
        })

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        self._cmd("reservation-del", arguments={
            "ip-address": ip_address,
            "subnet-id": self._subnet_id(scope_id),
        })
