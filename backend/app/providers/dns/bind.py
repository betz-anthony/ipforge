import socket
import dns.query
import dns.zone
import dns.update
import dns.tsigkeyring
import dns.rdatatype
import dns.rcode
import dns.name
from app.providers.dns.base import DNSProvider, DNSRecord

# BIND provider via dnspython.
# Reading:  AXFR zone transfer (allow-transfer must permit this host or TSIG key).
# Writing:  RFC 2136 dynamic update over TCP (allow-update must permit TSIG key).
# Zones:    No self-listing API — configure zones as comma-separated list.


class BINDDNSProvider(DNSProvider):
    def __init__(self, cfg: dict, name: str):
        self.source = name
        self._host = cfg.get("host", "")
        self._port = int(cfg.get("port", 53))
        self._tsig_key_name = cfg.get("tsig_key_name", "")
        self._tsig_key_secret = cfg.get("tsig_key_secret", "")
        self._tsig_algorithm = cfg.get("tsig_algorithm", "hmac-sha256")
        self._zones = cfg.get("zones", "")

    def _addr(self) -> str:
        # dnspython's query.tcp/xfr require an IP literal — they do NOT resolve
        # hostnames. Resolve here so a hostname in the provider config works
        # (an IP passes through getaddrinfo unchanged).
        try:
            return socket.getaddrinfo(self._host, self._port, proto=socket.IPPROTO_TCP)[0][4][0]
        except socket.gaierror as e:
            raise RuntimeError(f"BIND host '{self._host}' did not resolve: {e}")

    def _keyring(self):
        if not self._tsig_key_name:
            return None, None
        keyring = dns.tsigkeyring.from_text({self._tsig_key_name: self._tsig_key_secret})
        return keyring, self._tsig_algorithm

    def get_zones(self) -> list[str]:
        if not self._zones:
            return []
        return [z.strip() for z in self._zones.split(",") if z.strip()]

    def get_records(self, zone: str) -> list[DNSRecord]:
        keyring, algo = self._keyring()
        xfr_kwargs: dict = {}
        if keyring:
            xfr_kwargs = {"keyring": keyring, "keyalgorithm": algo}

        xfr = dns.query.xfr(self._addr(), zone, port=self._port, **xfr_kwargs)
        zone_obj = dns.zone.from_xfr(xfr)

        records: list[DNSRecord] = []
        for name, node in zone_obj.nodes.items():
            str_name = str(name)
            for rdataset in node.rdatasets:
                rtype = dns.rdatatype.to_text(rdataset.rdtype)
                for rdata in rdataset:
                    records.append(DNSRecord(
                        name=str_name,
                        record_type=rtype,
                        value=rdata.to_text(),
                        zone=zone,
                        ttl=rdataset.ttl,
                    ))
        return records

    def _update(self, zone: str):
        keyring, algo = self._keyring()
        kwargs: dict = {}
        if keyring:
            kwargs = {"keyring": keyring, "keyalgorithm": algo}
        return dns.update.Update(zone, **kwargs)

    def _send_update(self, update) -> None:
        resp = dns.query.tcp(update, self._addr(), port=self._port)
        rc = resp.rcode()
        if rc != dns.rcode.NOERROR:
            raise RuntimeError(f"BIND RFC 2136 update rejected: {dns.rcode.to_text(rc)}")

    def add_record(self, record: DNSRecord) -> None:
        update = self._update(record.zone)
        update.add(record.name, record.ttl, record.record_type, record.value)
        self._send_update(update)

    def delete_record(self, record: DNSRecord) -> None:
        update = self._update(record.zone)
        update.delete(record.name, record.record_type, record.value)
        self._send_update(update)

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
