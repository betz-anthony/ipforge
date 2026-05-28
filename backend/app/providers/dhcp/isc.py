import requests
from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation

# ISC Kea DHCP provider via Kea Control Agent REST API.
# Requires: Kea Control Agent running (default port 8000).
# Docs: https://kea.readthedocs.io/en/latest/arm/ctrl-channel.html
#
# IPv4 subnets are served by the dhcp4 service, IPv6 by dhcp6. A scope_id is the
# subnet CIDR, so the service is inferred from whether it contains a colon.


def _is_v6(scope_id: str) -> bool:
    return ":" in scope_id


class KeaDHCPProvider(DHCPProvider):
    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._url = cfg.get("url", "")
        self._secret = cfg.get("secret", "")

    def _cmd(self, command: str, service: str = "dhcp4", arguments: dict | None = None) -> dict:
        body: dict = {"command": command, "service": [service]}
        if arguments:
            body["arguments"] = arguments

        auth = ("kea", self._secret) if self._secret else None
        r = requests.post(self._url, json=body, auth=auth, timeout=10)
        r.raise_for_status()

        result = r.json()
        if isinstance(result, list):
            result = result[0]
        if result.get("result") not in (0, 3):  # 3 = empty/not found, still ok for listing
            raise RuntimeError(result.get("text", "Kea command failed"))
        return result.get("arguments", {})

    def _service_for(self, scope_id: str) -> str:
        return "dhcp6" if _is_v6(scope_id) else "dhcp4"

    def _get_subnets(self, service: str = "dhcp4") -> list[dict]:
        v6 = service == "dhcp6"
        list_cmd = "subnet6-list" if v6 else "subnet4-list"
        cfg_key = "Dhcp6" if v6 else "Dhcp4"
        subnet_key = "subnet6" if v6 else "subnet4"
        # subnet{4,6}-list requires the subnet_cmds hook; fall back to config-get.
        try:
            return self._cmd(list_cmd, service=service).get("subnets", [])
        except RuntimeError as e:
            if "not supported" in str(e).lower():
                cfg = self._cmd("config-get", service=service)
                return cfg.get(cfg_key, {}).get(subnet_key, [])
            raise

    def _subnet_id(self, scope_id: str) -> int:
        service = self._service_for(scope_id)
        for s in self._get_subnets(service):
            if s["subnet"] == scope_id:
                return int(s["id"])
        raise RuntimeError(f"Subnet {scope_id!r} not found in Kea")

    def _scopes_for_service(self, service: str) -> list[DHCPScope]:
        v6 = service == "dhcp6"
        scopes: list[DHCPScope] = []
        for s in self._get_subnets(service):
            pools = s.get("pools", [])
            pool_str = pools[0].get("pool", "") if pools else ""
            start = end = ""
            if " - " in pool_str:
                start, end = [p.strip() for p in pool_str.split(" - ", 1)]
            cidr = s["subnet"]
            mask = ""
            if v6 and "/" in cidr:
                mask = "/" + cidr.split("/", 1)[1]
            scopes.append(DHCPScope(
                scope_id=cidr,
                name=s.get("shared-network-name") or cidr,
                subnet_mask=mask,
                start_range=start,
                end_range=end,
                description=f"ID: {s.get('id', '')}",
                active=True,
                ip_version=6 if v6 else 4,
            ))
        return scopes

    def get_scopes(self) -> list[DHCPScope]:
        return self._scopes_for_service("dhcp4") + self._scopes_for_service("dhcp6")

    def get_leases(self, scope_id: str) -> list[DHCPReservation]:
        service = self._service_for(scope_id)
        v6 = service == "dhcp6"
        results: dict[str, DHCPReservation] = {}
        subnet_id = self._subnet_id(scope_id)

        # Static reservations — requires host_cmds hook or built-in (Kea 3+)
        try:
            data = self._cmd("reservation-get-all", service=service, arguments={"subnet-id": subnet_id})
            for h in data.get("hosts", []):
                if v6:
                    addrs = h.get("ip-addresses") or ([h["ip-address"]] if h.get("ip-address") else [])
                    ip = addrs[0] if addrs else ""
                else:
                    ip = h.get("ip-address", "")
                if ip:
                    results[ip] = DHCPReservation(
                        scope_id=scope_id,
                        ip_address=ip,
                        mac_address="" if v6 else h.get("hw-address", ""),
                        client_duid=h.get("duid", "") if v6 else "",
                        name=h.get("hostname", ""),
                    )
        except RuntimeError as e:
            if "not supported" not in str(e).lower():
                raise

        # Dynamic leases — requires lease_cmds hook; filtered to this subnet
        lease_cmd = "lease6-get-all" if v6 else "lease4-get-all"
        try:
            data = self._cmd(lease_cmd, service=service, arguments={"subnets": [subnet_id]})
            for l in data.get("leases", []):
                ip = l.get("ip-address", "")
                if ip and ip not in results:
                    results[ip] = DHCPReservation(
                        scope_id=scope_id,
                        ip_address=ip,
                        mac_address="" if v6 else l.get("hw-address", ""),
                        client_duid=l.get("duid", "") if v6 else "",
                        name=l.get("hostname", ""),
                    )
        except RuntimeError as e:
            if "not supported" not in str(e).lower():
                raise

        return list(results.values())

    def _build_host(self, reservation: DHCPReservation) -> dict:
        service = self._service_for(reservation.scope_id)
        host: dict = {"subnet-id": self._subnet_id(reservation.scope_id)}
        if service == "dhcp6":
            if not reservation.client_duid:
                raise RuntimeError(
                    "Kea IPv6 requires a host identifier — enter a client DUID to create a reservation"
                )
            host["ip-addresses"] = [reservation.ip_address]
            host["duid"] = reservation.client_duid
        else:
            if not reservation.mac_address:
                raise RuntimeError(
                    "Kea requires a host identifier — enter a MAC address to create a reservation"
                )
            host["ip-address"] = reservation.ip_address
            host["hw-address"] = reservation.mac_address.replace("-", ":").lower()
        if reservation.name:
            host["hostname"] = reservation.name
        return host

    def add_reservation(self, reservation: DHCPReservation) -> None:
        service = self._service_for(reservation.scope_id)
        host = self._build_host(reservation)
        self._cmd("reservation-add", service=service, arguments={"reservation": host})

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        service = self._service_for(scope_id)
        self._cmd("reservation-del", service=service, arguments={
            "ip-address": ip_address,
            "subnet-id": self._subnet_id(scope_id),
        })

    def update_reservation_name(self, scope_id: str, ip_address: str, name: str) -> None:
        # Kea has no in-place reservation rename; delete and re-add preserving the
        # existing client identifier.
        existing = next(
            (r for r in self.get_leases(scope_id) if r.ip_address == ip_address),
            None,
        )
        if existing is None:
            raise RuntimeError(f"No reservation found for {ip_address} in {scope_id}")
        self.delete_reservation(scope_id, ip_address)
        existing.scope_id = scope_id
        existing.name = name
        self.add_reservation(existing)
