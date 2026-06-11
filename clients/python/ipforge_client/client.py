import os
from typing import Optional

from ._transport import _Transport
from .exceptions import ConfigError
from .resources.subnets import Subnets
from .resources.addresses import Addresses
from .resources.vlans import Vlans
from .resources.dns import DNS
from .resources.dhcp import DHCP
from .resources.drift import Drift
from .resources.discovery import Discovery
from .resources.audit import Audit


class IPForge:
    """IPForge API client.

        client = IPForge("https://ipforge.example.com", token="ipfg_...")
        for addr in client.addresses.list(subnet_id=3):
            print(addr.address, addr.hostname)
    """

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None,
                 timeout: float = 30, retries: int = 2):
        base_url = base_url or os.environ.get("IPFORGE_URL")
        token = token or os.environ.get("IPFORGE_TOKEN")
        if not base_url or not token:
            raise ConfigError(
                "base_url and token are required "
                "(pass explicitly or set IPFORGE_URL / IPFORGE_TOKEN)"
            )
        self._t = _Transport(base_url, token, timeout=timeout, retries=retries)
        self.subnets = Subnets(self._t)
        self.addresses = Addresses(self._t)
        self.vlans = Vlans(self._t)
        self.dns = DNS(self._t)
        self.dhcp = DHCP(self._t)
        self.drift = Drift(self._t)
        self.discovery = Discovery(self._t)
        self.audit = Audit(self._t)

    def search(self, q: str) -> dict:
        return self._t.request("GET", "/search", params={"q": q})
