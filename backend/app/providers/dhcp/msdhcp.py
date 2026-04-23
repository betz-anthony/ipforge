import json
import threading
import winrm
from winrm.exceptions import WinRMTransportError
from app.config import settings
from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation

try:
    from spnego.exceptions import BadMICError as _BadMICError
    _WINRM_RETRY = (WinRMTransportError, _BadMICError)
except ImportError:
    _WINRM_RETRY = (WinRMTransportError,)


def _is_v6(scope_id: str) -> bool:
    return ":" in scope_id


class MSDHCPProvider(DHCPProvider):
    source = "msdhcp"

    def __init__(self):
        self._session = None
        self._lock = threading.Lock()

    @property
    def session(self):
        if self._session is None:
            self._session = winrm.Session(
                settings.ms_winrm_host,
                auth=(settings.ms_winrm_user, settings.ms_winrm_password),
                transport=settings.ms_winrm_transport,
            )
        return self._session

    def _run(self, ps: str) -> str:
        with self._lock:
            try:
                result = self.session.run_ps(ps)
            except _WINRM_RETRY:
                self._session = None
                result = self.session.run_ps(ps)
            if result.status_code != 0:
                raise RuntimeError(result.std_err.decode())
            return result.std_out.decode()

    def _parse_json(self, out: str) -> list:
        if not out.strip():
            return []
        data = json.loads(out)
        return data if isinstance(data, list) else [data]

    def get_scopes(self) -> list[DHCPScope]:
        v4 = self._get_v4_scopes()
        v6 = self._get_v6_scopes()
        return v4 + v6

    def _get_v4_scopes(self) -> list[DHCPScope]:
        out = self._run(
            f"Get-DhcpServerv4Scope -ComputerName '{settings.ms_dhcp_server}' "
            "| ConvertTo-Json -Depth 3"
        )
        return [
            DHCPScope(
                scope_id=s["ScopeId"]["IPAddressToString"],
                name=s["Name"],
                subnet_mask=s["SubnetMask"]["IPAddressToString"],
                start_range=s["StartRange"]["IPAddressToString"],
                end_range=s["EndRange"]["IPAddressToString"],
                description=s.get("Description") or "",
                active=s.get("State") == "Active",
                ip_version=4,
            )
            for s in self._parse_json(out)
        ]

    def _get_v6_scopes(self) -> list[DHCPScope]:
        try:
            out = self._run(
                f"Get-DhcpServerv6Scope -ComputerName '{settings.ms_dhcp_server}' "
                "| ConvertTo-Json -Depth 3"
            )
        except RuntimeError:
            return []
        return [
            DHCPScope(
                scope_id=s["Prefix"]["IPAddressToString"],
                name=s.get("Name") or s["Prefix"]["IPAddressToString"],
                subnet_mask=f"/{s.get('SubnetLength', 64)}",
                start_range="",
                end_range="",
                description=s.get("Description") or "",
                active=s.get("State") == "Active",
                ip_version=6,
            )
            for s in self._parse_json(out)
        ]

    def get_leases(self, scope_id: str) -> list[DHCPReservation]:
        if _is_v6(scope_id):
            return self._get_v6_leases(scope_id)
        return self._get_v4_leases(scope_id)

    def _get_v4_leases(self, scope_id: str) -> list[DHCPReservation]:
        out = self._run(
            f"Get-DhcpServerv4Lease -ScopeId '{scope_id}' "
            f"-ComputerName '{settings.ms_dhcp_server}' "
            "| ConvertTo-Json -Depth 3"
        )
        return [
            DHCPReservation(
                scope_id=scope_id,
                ip_address=l["IPAddress"]["IPAddressToString"],
                mac_address=l.get("ClientId") or "",
                name=l.get("HostName") or "",
            )
            for l in self._parse_json(out)
        ]

    def _get_v6_leases(self, scope_id: str) -> list[DHCPReservation]:
        out = self._run(
            f"Get-DhcpServerv6Lease -Prefix '{scope_id}' "
            f"-ComputerName '{settings.ms_dhcp_server}' "
            "| ConvertTo-Json -Depth 3"
        )
        return [
            DHCPReservation(
                scope_id=scope_id,
                ip_address=l["IPAddress"]["IPAddressToString"],
                client_duid=l.get("ClientDuid") or "",
                iaid=l.get("Iaid") or 0,
                name=l.get("HostName") or "",
            )
            for l in self._parse_json(out)
        ]

    def add_reservation(self, reservation: DHCPReservation) -> None:
        if _is_v6(reservation.scope_id):
            self._run(
                f"Add-DhcpServerv6Reservation -Prefix '{reservation.scope_id}' "
                f"-IPAddress '{reservation.ip_address}' "
                f"-ClientDuid '{reservation.client_duid}' "
                f"-Iaid {reservation.iaid} "
                f"-Name '{reservation.name}' "
                f"-Description '{reservation.description}' "
                f"-ComputerName '{settings.ms_dhcp_server}'"
            )
        else:
            self._run(
                f"Add-DhcpServerv4Reservation -ScopeId '{reservation.scope_id}' "
                f"-IPAddress '{reservation.ip_address}' "
                f"-ClientId '{reservation.mac_address}' "
                f"-Name '{reservation.name}' "
                f"-Description '{reservation.description}' "
                f"-ComputerName '{settings.ms_dhcp_server}'"
            )

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        if _is_v6(scope_id):
            self._run(
                f"Remove-DhcpServerv6Reservation -Prefix '{scope_id}' "
                f"-IPAddress '{ip_address}' "
                f"-ComputerName '{settings.ms_dhcp_server}'"
            )
        else:
            self._run(
                f"Remove-DhcpServerv4Reservation -IPAddress '{ip_address}' -Force "
                f"-ComputerName '{settings.ms_dhcp_server}'"
            )
