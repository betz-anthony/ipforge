"""DNS-DHCP-EDIT-001 P4 — BIND update_record as one RFC2136 transaction."""
from app.providers.dns.bind import BINDDNSProvider
from app.providers.dns.base import DNSRecord


class FakeUpdate:
    def __init__(self):
        self.calls = []

    def delete(self, name, record_type, value):
        self.calls.append(("delete", name, record_type, value))

    def add(self, name, ttl, record_type, value):
        self.calls.append(("add", name, ttl, record_type, value))


def _provider():
    p = BINDDNSProvider({"host": "10.0.0.1"}, "bind01")
    p.updates_created = []
    p.sent = []

    def fake_update(zone):
        u = FakeUpdate()
        u.zone = zone
        p.updates_created.append(u)
        return u

    p._update = fake_update
    p._send_update = lambda u: p.sent.append(u)
    return p


def test_update_record_single_transaction():
    p = _provider()
    old = DNSRecord(name="web01", record_type="A", value="10.0.1.5", zone="example.com", ttl=3600)
    new = DNSRecord(name="web01", record_type="A", value="10.0.1.9", zone="example.com", ttl=3600)
    p.update_record(old, new)

    assert len(p.updates_created) == 1, "delete+add must share one Update object"
    assert len(p.sent) == 1, "must be a single wire transaction"
    assert p.sent[0] is p.updates_created[0]

    u = p.updates_created[0]
    assert u.zone == "example.com"
    assert u.calls == [
        ("delete", "web01", "A", "10.0.1.5"),
        ("add", "web01", 3600, "A", "10.0.1.9"),
    ]
