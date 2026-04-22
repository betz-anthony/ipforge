import json
import winrm
from app.config import settings
from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation


class MSDHCPProvider(DHCPProvider):
    def __init__(self):
        self._session = None

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
        result = self.session.run_ps(ps)
        if result.status_code != 0:
            raise RuntimeError(result.std_err.decode())
        return result.std_out.decode()

    def get_scopes(self) -> list[DHCPScope]:
        out = self._run(
            f"Get-DhcpServerv4Scope -ComputerName '{settings.ms_dhcp_server}' "
            "| ConvertTo-Json -Depth 3"
        )
        scopes = json.loads(out)
        if isinstance(scopes, dict):
            scopes = [scopes]
        return [
            DHCPScope(
                scope_id=s["ScopeId"]["IPAddressToString"],
                name=s["Name"],
                subnet_mask=s["SubnetMask"]["IPAddressToString"],
                start_range=s["StartRange"]["IPAddressToString"],
                end_range=s["EndRange"]["IPAddressToString"],
                description=s.get("Description") or "",
                active=s.get("State") == "Active",
            )
            for s in scopes
        ]

    def get_leases(self, scope_id: str) -> list[DHCPReservation]:
        out = self._run(
            f"Get-DhcpServerv4Lease -ScopeId '{scope_id}' "
            f"-ComputerName '{settings.ms_dhcp_server}' "
            "| ConvertTo-Json -Depth 3"
        )
        leases = json.loads(out)
        if isinstance(leases, dict):
            leases = [leases]
        return [
            DHCPReservation(
                scope_id=scope_id,
                ip_address=l["IPAddress"]["IPAddressToString"],
                mac_address=l.get("ClientId") or "",
                name=l.get("HostName") or "",
            )
            for l in leases
        ]

    def add_reservation(self, reservation: DHCPReservation) -> None:
        self._run(
            f"Add-DhcpServerv4Reservation -ScopeId '{reservation.scope_id}' "
            f"-IPAddress '{reservation.ip_address}' "
            f"-ClientId '{reservation.mac_address}' "
            f"-Name '{reservation.name}' "
            f"-Description '{reservation.description}' "
            f"-ComputerName '{settings.ms_dhcp_server}'"
        )

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        self._run(
            f"Remove-DhcpServerv4Reservation -ScopeId '{scope_id}' "
            f"-IPAddress '{ip_address}' -Force "
            f"-ComputerName '{settings.ms_dhcp_server}'"
        )
