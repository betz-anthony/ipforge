"""MCP-001 — thin HTTP client used by the MCP server.

Wraps the IPForge REST API with an `ipfg_` token. Only `_req` touches the
network, so the method logic is unit-testable with mocks. The token's role is the
authorization boundary (the API enforces read-only / operator / admin).
"""
import requests


class IPForgeClient:
    def __init__(self, base_url: str, token: str):
        self._base = base_url.rstrip("/")
        self._token = token

    def _req(self, method: str, path: str, params: dict | None = None, json: dict | None = None):
        r = requests.request(
            method, f"{self._base}/api/v1{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params=params, json=json, timeout=30,
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    # ── read ─────────────────────────────────────────────────────────────────
    def list_subnets(self) -> list:
        return self._req("GET", "/subnets")

    def get_subnet(self, subnet_id: int) -> dict:
        return self._req("GET", f"/subnets/{subnet_id}")

    def list_addresses(self, subnet_id: int | None = None, tag: str | None = None) -> list:
        params: dict = {"limit": 200}
        if subnet_id is not None:
            params["subnet_id"] = subnet_id
        if tag is not None:
            params["tag"] = tag
        return self._req("GET", "/addresses", params=params)["items"]

    def find_free_ip(self, subnet_id: int) -> str | None:
        m = self._req("GET", f"/subnets/{subnet_id}/map")
        if m.get("too_large"):
            return None
        for cell in m.get("cells", []):
            if cell.get("status") == "free":
                return cell["ip"]
        return None

    def search(self, q: str) -> dict:
        return self._req("GET", "/search", params={"q": q})

    def list_drift(self, category: str | None = None, severity: str | None = None,
                   needs_review: bool | None = None) -> list:
        params = {}
        if category is not None:
            params["category"] = category
        if severity is not None:
            params["severity"] = severity
        if needs_review is not None:
            params["needs_review"] = needs_review
        return self._req("GET", "/drift", params=params or None)

    def list_discovery(self, ip: str | None = None, mac: str | None = None) -> list:
        params = {}
        if ip is not None:
            params["ip"] = ip
        if mac is not None:
            params["mac"] = mac
        return self._req("GET", "/discovery/endpoints", params=params or None)

    def ip_history(self, ip: str) -> dict:
        return self._req("GET", f"/addresses/by-ip/{ip}/history")

    # ── safe writes ────────────────────────────────────────────────────────────
    def allocate_ip(self, subnet_id: int, hostname: str, mac: str | None = None,
                    register_dns: bool = False, register_dhcp: bool = False,
                    dns_zone: str | None = None) -> dict:
        body = {"hostname": hostname, "register_dns": register_dns, "register_dhcp": register_dhcp}
        if mac:
            body["mac_address"] = mac
        if dns_zone:
            body["dns_zone"] = dns_zone
        return self._req("POST", f"/subnets/{subnet_id}/allocate", json=body)

    def tag_address(self, ip: str, tags: list[str]) -> dict:
        addr = self._req("GET", f"/addresses/by-ip/{ip}")
        merged = sorted(set(addr.get("tags") or []) | set(tags))
        return self._req("PUT", f"/addresses/{addr['id']}", json={"tags": merged})

    def resolve_drift(self, drift_id: int, action: str | None = None) -> dict:
        return self._req("POST", f"/drift/{drift_id}/resolve", json={"action": action} if action else {})
