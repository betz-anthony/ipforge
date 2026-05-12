import requests
from urllib.parse import quote
from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation

# Pi-hole v6 DHCP provider.
# Static reservations: PUT/DELETE /api/config/dhcp/hosts/{mac,ip[,name]}
# Active leases:       GET /api/dhcp/leases  (field: hwaddr, not mac)


class PiholeDHCPProvider(DHCPProvider):
    SCOPE_ID = "pihole"

    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._base_url = cfg.get("url", "").rstrip("/")
        self._password = cfg.get("password", "")
        self._sid: str | None = None

    def _authenticate(self) -> str:
        r = requests.post(
            f"{self._base_url}/api/auth",
            json={"password": self._password},
            verify=False, timeout=10,
        )
        r.raise_for_status()
        return r.json()["session"]["sid"]

    def _headers(self) -> dict:
        if not self._sid:
            self._sid = self._authenticate()
        return {"X-FTL-SID": self._sid}

    def _req(self, method: str, path: str, **kwargs):
        url = f"{self._base_url}/api{path}"
        r = requests.request(method, url, headers=self._headers(), verify=False, timeout=10, **kwargs)
        if r.status_code == 401:
            self._sid = None
            r = requests.request(method, url, headers=self._headers(), verify=False, timeout=10, **kwargs)
        r.raise_for_status()
        return r

    def _dhcp_cfg(self) -> dict:
        data = self._req("GET", "/config/dhcp").json()
        return data.get("config", {}).get("dhcp", {})

    def _static_hosts_raw(self) -> list[str]:
        return self._dhcp_cfg().get("hosts", [])

    def get_scopes(self) -> list[DHCPScope]:
        cfg = self._dhcp_cfg()
        return [DHCPScope(
            scope_id=self.SCOPE_ID,
            name="Pi-hole DHCP",
            subnet_mask="",
            start_range=cfg.get("start", ""),
            end_range=cfg.get("end", ""),
            description=f"Router: {cfg.get('router', '')}",
            active=bool(cfg.get("active", False)),
        )]

    def get_leases(self, scope_id: str) -> list[DHCPReservation]:
        leases = self._req("GET", "/dhcp/leases").json().get("leases", [])
        return [
            DHCPReservation(
                scope_id=scope_id,
                ip_address=l.get("ip", ""),
                mac_address=l.get("hwaddr", ""),
                name=l.get("name", "") or l.get("hostname", ""),
            )
            for l in leases
        ]

    def add_reservation(self, reservation: DHCPReservation) -> None:
        entry = f"{reservation.mac_address},{reservation.ip_address}"
        if reservation.name:
            entry += f",{reservation.name}"
        self._req("PUT", f"/config/dhcp/hosts/{quote(entry, safe='')}")

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        for entry in self._static_hosts_raw():
            parts = entry.split(",")
            if len(parts) >= 2 and parts[1] == ip_address:
                self._req("DELETE", f"/config/dhcp/hosts/{quote(entry, safe='')}")
                return
        raise RuntimeError(f"No static reservation found for {ip_address}")
