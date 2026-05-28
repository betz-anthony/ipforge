from app.providers.dns.cloudflare import CloudflareDNSProvider
from app.providers.dns.base import DNSRecord


def _provider(responses, calls):
    p = CloudflareDNSProvider({"api_token": "tok"}, "cf")

    def fake_req(method, path, **kw):
        calls.append((method, path, kw.get("json")))
        return responses.get((method, path), {})

    p._req = fake_req
    return p


ZONES = {("GET", "/zones"): {"result": [
    {"id": "z1", "name": "example.com"},
    {"id": "z2", "name": "corp.local"},
]}}


def test_get_zones():
    p = _provider(ZONES, [])
    assert set(p.get_zones()) == {"example.com", "corp.local"}


def test_get_records_flattens():
    resp = dict(ZONES)
    resp[("GET", "/zones/z1/dns_records")] = {"result": [
        {"id": "r1", "type": "A", "name": "web.example.com", "content": "10.0.0.5", "ttl": 300},
        {"id": "r2", "type": "CNAME", "name": "alias.example.com", "content": "web.example.com", "ttl": 1},
    ]}
    p = _provider(resp, [])
    recs = p.get_records("example.com")
    a = next(r for r in recs if r.record_type == "A")
    assert a.name == "web.example.com" and a.value == "10.0.0.5" and a.ttl == 300 and a.zone == "example.com"
    assert any(r.record_type == "CNAME" and r.value == "web.example.com" for r in recs)


def test_add_record_posts():
    calls = []
    p = _provider(ZONES, calls)
    p.add_record(DNSRecord(name="new.example.com", record_type="A", value="10.0.0.9", zone="example.com", ttl=120))
    post = next(c for c in calls if c[0] == "POST")
    assert post[1] == "/zones/z1/dns_records"
    assert post[2] == {"type": "A", "name": "new.example.com", "content": "10.0.0.9", "ttl": 120}


def test_delete_record_resolves_id_then_deletes():
    resp = dict(ZONES)
    resp[("GET", "/zones/z1/dns_records")] = {"result": [
        {"id": "rX", "type": "A", "name": "web.example.com", "content": "10.0.0.5", "ttl": 300},
    ]}
    calls = []
    p = _provider(resp, calls)
    p.delete_record(DNSRecord(name="web.example.com", record_type="A", value="10.0.0.5", zone="example.com"))
    assert ("DELETE", "/zones/z1/dns_records/rX", None) in calls


def test_update_record_puts():
    resp = dict(ZONES)
    resp[("GET", "/zones/z1/dns_records")] = {"result": [
        {"id": "rX", "type": "A", "name": "web.example.com", "content": "10.0.0.5", "ttl": 300},
    ]}
    calls = []
    p = _provider(resp, calls)
    old = DNSRecord(name="web.example.com", record_type="A", value="10.0.0.5", zone="example.com")
    new = DNSRecord(name="web.example.com", record_type="A", value="10.0.0.6", zone="example.com", ttl=60)
    p.update_record(old, new)
    put = next(c for c in calls if c[0] == "PUT")
    assert put[1] == "/zones/z1/dns_records/rX"
    assert put[2]["content"] == "10.0.0.6" and put[2]["ttl"] == 60
