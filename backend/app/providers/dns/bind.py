import dns.query
import dns.zone
import dns.update
import dns.tsigkeyring
import dns.rdatatype
import dns.name
from app.config import settings
from app.providers.dns.base import DNSProvider, DNSRecord

# BIND provider via dnspython.
# Reading:  AXFR zone transfer (allow-transfer must permit this host or TSIG key).
# Writing:  RFC 2136 dynamic update over TCP (allow-update must permit TSIG key).
# Zones:    No self-listing API — configure bind_zones as comma-separated list.


class BINDDNSProvider(DNSProvider):
    source = "bind"

    def _keyring(self):
        if not settings.bind_tsig_key_name:
            return None, None
        keyring = dns.tsigkeyring.from_text({
            settings.bind_tsig_key_name: settings.bind_tsig_key_secret,
        })
        return keyring, settings.bind_tsig_algorithm

    def get_zones(self) -> list[str]:
        if not settings.bind_zones:
            return []
        return [z.strip() for z in settings.bind_zones.split(",") if z.strip()]

    def get_records(self, zone: str) -> list[DNSRecord]:
        keyring, algo = self._keyring()
        xfr_kwargs: dict = {}
        if keyring:
            xfr_kwargs = {"keyring": keyring, "keyalgorithm": algo}

        xfr = dns.query.xfr(
            settings.bind_host, zone,
            port=settings.bind_port,
            **xfr_kwargs,
        )
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

    def _update(self, zone: str) -> tuple:
        keyring, algo = self._keyring()
        kwargs: dict = {}
        if keyring:
            kwargs = {"keyring": keyring, "keyalgorithm": algo}
        return dns.update.Update(zone, **kwargs), kwargs

    def add_record(self, record: DNSRecord) -> None:
        update, _ = self._update(record.zone)
        update.add(record.name, record.ttl, record.record_type, record.value)
        dns.query.tcp(update, settings.bind_host, port=settings.bind_port)

    def delete_record(self, record: DNSRecord) -> None:
        update, _ = self._update(record.zone)
        update.delete(record.name, record.record_type, record.value)
        dns.query.tcp(update, settings.bind_host, port=settings.bind_port)

    def update_record(self, old: DNSRecord, new: DNSRecord) -> None:
        self.delete_record(old)
        self.add_record(new)
