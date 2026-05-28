"""SNMP discovery collector (DISCOVERY-SNMP-001 P1).

Walks standard MIBs and merges them into IP↔MAC↔switchport↔VLAN endpoints.
Only `_walk` touches the network, so merge logic is unit-testable with mocks.
"""
import logging

from app.discovery.base import DiscoverySource, Endpoint

logger = logging.getLogger(__name__)

# MIB OIDs (numeric).
OID_ARP      = "1.3.6.1.2.1.4.22.1.2"        # ipNetToMediaPhysAddress: <ifindex>.<ipv4> -> mac
OID_FDB      = "1.3.6.1.2.1.17.7.1.2.2.1.2"  # dot1qTpFdbPort: <vlan>.<mac6> -> bridgeport
OID_BASEPORT = "1.3.6.1.2.1.17.1.4.1.2"      # dot1dBasePortIfIndex: <bridgeport> -> ifindex
OID_IFNAME   = "1.3.6.1.2.1.31.1.1.1.1"      # ifName: <ifindex> -> name


def _mac_from_octets(octets: list[int]) -> str:
    return ":".join(f"{o:02x}" for o in octets)


class SnmpDiscovery(DiscoverySource):
    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._host = cfg.get("host", "")
        self._version = cfg.get("snmp_version", "2c")
        self._cfg = cfg

    # ── network layer (mocked in tests) ──────────────────────────────────────
    def _auth_data(self):
        # pysnmp 6.x async hlapi (lextudio). Classic sync pysnmp.hlapi was removed.
        from pysnmp.hlapi.asyncio import (
            CommunityData, UsmUserData,
            usmHMACSHAAuthProtocol, usmHMACMD5AuthProtocol,
            usmAesCfb128Protocol, usmDESPrivProtocol, usmNoAuthProtocol, usmNoPrivProtocol,
        )
        if self._version == "3":
            auth = {"SHA": usmHMACSHAAuthProtocol, "MD5": usmHMACMD5AuthProtocol}.get(
                self._cfg.get("auth_protocol"), usmNoAuthProtocol)
            priv = {"AES": usmAesCfb128Protocol, "DES": usmDESPrivProtocol}.get(
                self._cfg.get("priv_protocol"), usmNoPrivProtocol)
            return UsmUserData(
                self._cfg.get("v3_user", ""),
                authKey=self._cfg.get("auth_key") or None,
                privKey=self._cfg.get("priv_key") or None,
                authProtocol=auth, privProtocol=priv,
            )
        return CommunityData(self._cfg.get("community", "public"))  # mpModel=1 (v2c) by default

    def _decode(self, oid: str, name, val) -> tuple[str, object]:
        suffix = str(name)[len(oid) + 1:]
        if oid == OID_ARP:
            return suffix, val.asOctets().hex(":")
        if oid == OID_IFNAME:
            return suffix, str(val)
        return suffix, int(val)

    def _walk(self, oid: str) -> list[tuple[str, object]]:
        """Return [(index_suffix, decoded_value)] for an OID subtree.

        ARP values decode to 'aa:bb:..' mac strings; fdb/baseport to int;
        ifName to str. Uses the pysnmp 6.x asyncio hlapi, driven synchronously.
        """
        import asyncio
        return asyncio.run(self._awalk(oid))

    async def _awalk(self, oid: str) -> list[tuple[str, object]]:
        from pysnmp.hlapi.asyncio import (
            SnmpEngine, UdpTransportTarget, ContextData,
            ObjectType, ObjectIdentity, walkCmd,
        )
        # Transport construction became an async classmethod in pysnmp 6.1+.
        try:
            transport = await UdpTransportTarget.create((self._host, 161), timeout=2, retries=1)
        except AttributeError:
            transport = UdpTransportTarget((self._host, 161), timeout=2, retries=1)

        out: list[tuple[str, object]] = []
        async for (err, status, _idx, binds) in walkCmd(
            SnmpEngine(), self._auth_data(), transport, ContextData(),
            ObjectType(ObjectIdentity(oid)), lexicographicMode=False,
        ):
            if err or status:
                logger.warning("SNMP walk %s on %s: %s", oid, self._host, err or status)
                break
            for name, val in binds:
                out.append(self._decode(oid, name, val))
        return out

    # ── merge logic (pure; unit-tested) ──────────────────────────────────────
    def poll(self) -> list[Endpoint]:
        baseport_to_ifindex: dict[int, int] = {}
        for suffix, ifindex in self._walk(OID_BASEPORT):
            try:
                baseport_to_ifindex[int(suffix)] = int(ifindex)
            except (ValueError, TypeError):
                continue

        ifindex_to_name: dict[int, str] = {}
        for suffix, name in self._walk(OID_IFNAME):
            try:
                ifindex_to_name[int(suffix)] = str(name)
            except (ValueError, TypeError):
                continue

        # fdb: mac -> (vlan, ifindex, port_name)
        fdb: dict[str, dict] = {}
        for suffix, bridgeport in self._walk(OID_FDB):
            parts = suffix.split(".")
            if len(parts) < 7:
                continue
            try:
                vlan = int(parts[0])
                mac = _mac_from_octets([int(x) for x in parts[1:7]])
            except ValueError:
                continue
            ifindex = baseport_to_ifindex.get(int(bridgeport)) if bridgeport is not None else None
            fdb[mac] = {
                "vlan": vlan,
                "ifindex": ifindex,
                "port_name": ifindex_to_name.get(ifindex) if ifindex is not None else None,
            }

        # arp: mac -> ip
        arp: dict[str, str] = {}
        for suffix, mac in self._walk(OID_ARP):
            parts = suffix.split(".")
            if len(parts) < 5:
                continue
            ip = ".".join(parts[-4:])
            arp[str(mac).lower()] = ip

        endpoints: list[Endpoint] = []
        for mac in set(fdb) | set(arp):
            f = fdb.get(mac, {})
            endpoints.append(Endpoint(
                ip=arp.get(mac),
                mac=mac,
                ifindex=f.get("ifindex"),
                port_name=f.get("port_name"),
                vlan=f.get("vlan"),
            ))
        return endpoints
