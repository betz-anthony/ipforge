from typing import List, Optional

from ..models import DiscoveryEndpoint


class Discovery:
    def __init__(self, transport):
        self._t = transport

    def list_endpoints(self, ip: Optional[str] = None,
                       mac: Optional[str] = None) -> List[DiscoveryEndpoint]:
        params = {k: v for k, v in {"ip": ip, "mac": mac}.items() if v is not None}
        return [DiscoveryEndpoint(x)
                for x in self._t.request("GET", "/discovery/endpoints", params=params or None)]
