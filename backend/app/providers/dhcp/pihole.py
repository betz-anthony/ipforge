import requests
from app.config import settings
from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation

# Pi-hole v6 DHCP provider.
# Static reservations are managed via PATCH /api/config (dhcp.hosts array).


class PiholeDHCPProvider(DHCPProvider):
    source = "pihole"
    SCOPE_ID = "pihole"

    def __init__(self):
        self._sid: str | None = None

    @property
    def _base(self) -> str:
        return settings.pihole_url.rstrip("/")

    def _authenticate(self) -> str:
        r = requests.post(
            f"{self._base}/api/auth",
            json={"password": settings.pihole_password},
            verify=False,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["session"]["sid"]

    def _headers(self) -> dict:
        if not self._sid:
            self._sid = self._authenticate()
        return {"X-FTL-SID": self._sid}

    def _req(self, method: str, path: str, **kwargs):
        url = f"{self._base}/api{path}"
        r = requests.request(method, url, headers=self._headers(), verify=False, timeout=10, **kwargs)
        if r.status_code == 401:
            self._sid = None
            r = requests.request(method, url, headers=self._headers(), verify=False, timeout=10, **kwargs)
        r.raise_for_status()
        return r

    def _dhcp_config(self) -> dict:
        return self._req("GET", "/config/dhcp").json().get("config", {}).get("dhcp", {})

    def _static_hosts(self) -> list[dict]:
        return self._dhcp_config().get("hosts", {}).get("v", [])

    def get_scopes(self) -> list[DHCPScope]:
        cfg = self._dhcp_config()
        return [DHCPScope(
            scope_id=self.SCOPE_ID,
            name="Pi-hole DHCP",
            subnet_mask="",
            start_range=cfg.get("start", {}).get("v", ""),
            end_range=cfg.get("end", {}).get("v", ""),
            description=f"Router: {cfg.get('router', {}).get('v', '')}",
            active=bool(cfg.get("active", {}).get("v", False)),
        )]

    def get_leases(self, scope_id: str) -> list[DHCPReservation]:
        leases = self._req("GET", "/dhcp/leases").json().get("leases", [])
        return [
            DHCPReservation(
                scope_id=scope_id,
                ip_address=l.get("ip", ""),
                mac_address=l.get("mac", ""),
                name=l.get("name", "") or l.get("hostname", ""),
            )
            for l in leases
        ]

    def add_reservation(self, reservation: DHCPReservation) -> None:
        hosts = self._static_hosts()
        hosts.append({
            "ip": reservation.ip_address,
            "mac": reservation.mac_address,
            "name": reservation.name,
        })
        self._req("PATCH", "/config", json={"dhcp": {"hosts": hosts}})

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        hosts = [h for h in self._static_hosts() if h.get("ip") != ip_address]
        self._req("PATCH", "/config", json={"dhcp": {"hosts": hosts}})
