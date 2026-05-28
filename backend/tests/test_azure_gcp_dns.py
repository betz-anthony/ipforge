from types import SimpleNamespace
from unittest.mock import MagicMock

from app.providers.dns.azuredns import AzureDNSProvider
from app.providers.dns.gcpdns import GCPDNSProvider
from app.providers.dns.base import DNSRecord


# ── Azure ─────────────────────────────────────────────────────────────────────

def _azure(client):
    p = AzureDNSProvider({
        "tenant_id": "t", "client_id": "c", "client_secret": "s",
        "subscription_id": "sub", "resource_group": "rg",
    }, "az")
    p._client = lambda: client
    return p


def test_azure_get_zones():
    c = MagicMock()
    c.zones.list_by_resource_group.return_value = [SimpleNamespace(name="example.com"), SimpleNamespace(name="corp.local")]
    assert set(_azure(c).get_zones()) == {"example.com", "corp.local"}


def test_azure_get_records_a():
    c = MagicMock()
    rs = SimpleNamespace(name="web", type="Microsoft.Network/dnszones/A", ttl=300,
                         a_records=[SimpleNamespace(ipv4_address="10.0.0.5")])
    c.record_sets.list_by_dns_zone.return_value = [rs]
    recs = _azure(c).get_records("example.com")
    assert recs[0].name == "web.example.com" and recs[0].value == "10.0.0.5" and recs[0].ttl == 300


def test_azure_add_record():
    c = MagicMock()
    _azure(c).add_record(DNSRecord(name="web.example.com", record_type="A", value="10.0.0.9", zone="example.com", ttl=120))
    args, kwargs = c.record_sets.create_or_update.call_args
    # (rg, zone, relative_name, record_type, parameters)
    assert args[0] == "rg" and args[1] == "example.com" and args[2] == "web" and args[3] == "A"


def test_azure_delete_record():
    c = MagicMock()
    _azure(c).delete_record(DNSRecord(name="web.example.com", record_type="A", value="10.0.0.5", zone="example.com"))
    args, _ = c.record_sets.delete.call_args
    assert args[:4] == ("rg", "example.com", "web", "A")


# ── GCP ───────────────────────────────────────────────────────────────────────

def _gcp(client):
    p = GCPDNSProvider({"project_id": "proj", "service_account_json": "{}"}, "gcp")
    p._client = lambda: client
    return p


def test_gcp_get_zones():
    c = MagicMock()
    c.list_zones.return_value = [SimpleNamespace(name="z1", dns_name="example.com.")]
    assert _gcp(c).get_zones() == ["example.com"]


def test_gcp_get_records_flatten():
    c = MagicMock()
    zone = MagicMock()
    zone.list_resource_record_sets.return_value = [
        SimpleNamespace(name="web.example.com.", record_type="A", ttl=300, rrdatas=["10.0.0.5", "10.0.0.6"]),
    ]
    c.list_zones.return_value = [SimpleNamespace(name="z1", dns_name="example.com.")]
    c.zone.return_value = zone
    recs = _gcp(c).get_records("example.com")
    assert {r.value for r in recs} == {"10.0.0.5", "10.0.0.6"}
    assert all(r.name == "web.example.com" and r.ttl == 300 for r in recs)


def test_gcp_add_record_change():
    c = MagicMock()
    zone = MagicMock()
    c.list_zones.return_value = [SimpleNamespace(name="z1", dns_name="example.com.")]
    c.zone.return_value = zone
    _gcp(c).add_record(DNSRecord(name="web.example.com", record_type="A", value="10.0.0.9", zone="example.com", ttl=120))
    assert zone.changes.called
