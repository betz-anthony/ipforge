import logging
import threading
from winrm.exceptions import WinRMTransportError
from app.core.mac import normalize_mac
from app.providers.dhcp.base import DHCPProvider, DHCPScope, DHCPReservation
from app.providers._ps import ps_quote
from app.providers._winrm import build_session, check_result, parse_ps_json

logger = logging.getLogger(__name__)

try:
    from spnego.exceptions import BadMICError as _BadMICError
    _WINRM_RETRY = (WinRMTransportError, _BadMICError)
except ImportError:
    _WINRM_RETRY = (WinRMTransportError,)


def _is_v6(scope_id: str) -> bool:
    return ":" in scope_id


def _dash_mac(mac: str) -> str:
    """Add/Set-DhcpServerv4Reservation's -ClientId requires dash-delimited
    hex (aa-bb-cc-dd-ee-ff) — IPForge's own canonical MAC form is colon-
    delimited (core.mac.normalize_mac), which Windows rejects outright with
    a CimException rather than accepting or reformatting it."""
    return normalize_mac(mac).replace(":", "-")


def _v4_client_mac(client_id: str) -> str:
    """Get-DhcpServerv4Lease's ClientId is the raw DHCP option-61 value — for a
    normal client that's the 6-byte hardware MAC, but a client can (and newer
    Windows guest OSes commonly do) send a DUID-based client identifier for
    IPv4 instead, which is a different shape entirely. Only accept it as a MAC
    if it actually is one; otherwise leave it blank rather than mislabel it."""
    if not client_id:
        return ""
    try:
        normalize_mac(client_id)
    except ValueError:
        logger.warning("msdhcp: ClientId %r is not a MAC (likely a DUID-based client-id) — leaving blank", client_id)
        return ""
    return client_id


class MSDHCPProvider(DHCPProvider):
    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._winrm_host = cfg.get("winrm_host", "")
        self._winrm_user = cfg.get("winrm_user", "")
        self._winrm_password = cfg.get("winrm_password", "")
        self._winrm_transport = cfg.get("winrm_transport", "ntlm")
        self._dhcp_server = cfg.get("dhcp_server", "")
        self._session = None
        self._lock = threading.Lock()

    @property
    def session(self):
        if self._session is None:
            self._session = build_session(
                self._winrm_host,
                self._winrm_user,
                self._winrm_password,
                self._winrm_transport,
            )
        return self._session

    def _run(self, ps: str) -> str:
        with self._lock:
            try:
                result = self.session.run_ps(ps)
            except _WINRM_RETRY:
                self._session = None
                result = self.session.run_ps(ps)
            return check_result(result)

    def _parse_json(self, out: str) -> list:
        return parse_ps_json(out)

    def get_scopes(self) -> list[DHCPScope]:
        return self._get_v4_scopes() + self._get_v6_scopes()

    def _get_v4_scopes(self) -> list[DHCPScope]:
        out = self._run(
            f"Get-DhcpServerv4Scope -ComputerName {ps_quote(self._dhcp_server)} "
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
                f"Get-DhcpServerv6Scope -ComputerName {ps_quote(self._dhcp_server)} "
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
            f"Get-DhcpServerv4Lease -ScopeId {ps_quote(scope_id)} "
            f"-ComputerName {ps_quote(self._dhcp_server)} "
            "| ConvertTo-Json -Depth 3"
        )
        return [
            DHCPReservation(
                scope_id=scope_id,
                ip_address=l["IPAddress"]["IPAddressToString"],
                mac_address=_v4_client_mac(l.get("ClientId") or ""),
                name=l.get("HostName") or "",
            )
            for l in self._parse_json(out)
        ]

    def _get_v6_leases(self, scope_id: str) -> list[DHCPReservation]:
        out = self._run(
            f"Get-DhcpServerv6Lease -Prefix {ps_quote(scope_id)} "
            f"-ComputerName {ps_quote(self._dhcp_server)} "
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
                f"Add-DhcpServerv6Reservation -Prefix {ps_quote(reservation.scope_id)} "
                f"-IPAddress {ps_quote(reservation.ip_address)} "
                f"-ClientDuid {ps_quote(reservation.client_duid)} "
                f"-Iaid {int(reservation.iaid)} "
                f"-Name {ps_quote(reservation.name)} "
                f"-Description {ps_quote(reservation.description)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )
        else:
            self._run(
                f"Add-DhcpServerv4Reservation -ScopeId {ps_quote(reservation.scope_id)} "
                f"-IPAddress {ps_quote(reservation.ip_address)} "
                f"-ClientId {ps_quote(_dash_mac(reservation.mac_address))} "
                f"-Name {ps_quote(reservation.name)} "
                f"-Description {ps_quote(reservation.description)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )

    def delete_reservation(self, scope_id: str, ip_address: str) -> None:
        if _is_v6(scope_id):
            self._run(
                f"Remove-DhcpServerv6Reservation -Prefix {ps_quote(scope_id)} "
                f"-IPAddress {ps_quote(ip_address)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )
        else:
            self._run(
                f"Remove-DhcpServerv4Reservation -IPAddress {ps_quote(ip_address)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )

    def update_reservation_name(self, scope_id: str, ip_address: str, name: str) -> None:
        if _is_v6(scope_id):
            self._run(
                f"Set-DhcpServerv6Reservation -IPAddress {ps_quote(ip_address)} "
                f"-Name {ps_quote(name)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )
        else:
            self._run(
                f"Set-DhcpServerv4Reservation -IPAddress {ps_quote(ip_address)} "
                f"-Name {ps_quote(name)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )

    def update_reservation(self, old: DHCPReservation, new: DHCPReservation) -> None:
        is_v6 = _is_v6(old.scope_id)
        # The client identifier (MAC / DUID+IAID) is the reservation's key on
        # MS DHCP — Set-* cannot change it, so fall back to delete + add.
        identifier_changed = (
            (old.client_duid != new.client_duid or old.iaid != new.iaid) if is_v6
            else old.mac_address != new.mac_address
        )
        if identifier_changed:
            self.delete_reservation(old.scope_id, old.ip_address)
            new.scope_id = old.scope_id
            try:
                self.add_reservation(new)
            except Exception:
                # The delete already committed on the live server — try to
                # restore the original reservation so a failed add doesn't
                # leave it permanently gone. Re-raise either way so the
                # caller still sees the real failure and never writes the
                # (never-applied) change into IPAM's own cache.
                try:
                    self.add_reservation(old)
                except Exception as undo_exc:
                    logger.error(
                        "msdhcp: add_reservation failed AND restoring the deleted "
                        "reservation for %s/%s also failed — it is gone from the "
                        "DHCP server: %s", old.scope_id, old.ip_address, undo_exc,
                    )
                raise
            return
        if is_v6:
            self._run(
                f"Set-DhcpServerv6Reservation -IPAddress {ps_quote(old.ip_address)} "
                f"-Name {ps_quote(new.name)} "
                f"-Description {ps_quote(new.description)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )
        else:
            self._run(
                f"Set-DhcpServerv4Reservation -IPAddress {ps_quote(old.ip_address)} "
                f"-Name {ps_quote(new.name)} "
                f"-Description {ps_quote(new.description)} "
                f"-ComputerName {ps_quote(self._dhcp_server)}"
            )
