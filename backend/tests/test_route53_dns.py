from unittest.mock import MagicMock

from app.providers.dns.route53 import Route53DNSProvider
from app.providers.dns.base import DNSRecord


def _provider(client):
    p = Route53DNSProvider({"aws_access_key_id": "k", "aws_secret_access_key": "s"}, "r53")
    p._client = lambda: client
    return p


def _client_with_zones():
    c = MagicMock()
    c.list_hosted_zones.return_value = {"HostedZones": [
        {"Id": "/hostedzone/Z1", "Name": "example.com."},
        {"Id": "/hostedzone/Z2", "Name": "corp.local."},
    ]}
    return c


def test_get_zones_strips_dot():
    p = _provider(_client_with_zones())
    assert set(p.get_zones()) == {"example.com", "corp.local"}


def test_get_records_flattens_rrset():
    c = _client_with_zones()
    c.list_resource_record_sets.return_value = {
        "ResourceRecordSets": [
            {"Name": "web.example.com.", "Type": "A", "TTL": 300,
             "ResourceRecords": [{"Value": "10.0.0.5"}, {"Value": "10.0.0.6"}]},
        ],
        "IsTruncated": False,
    }
    p = _provider(c)
    recs = p.get_records("example.com")
    vals = {r.value for r in recs}
    assert vals == {"10.0.0.5", "10.0.0.6"}
    assert all(r.name == "web.example.com" and r.record_type == "A" and r.ttl == 300 for r in recs)


def test_add_record_upserts():
    c = _client_with_zones()
    p = _provider(c)
    p.add_record(DNSRecord(name="new.example.com", record_type="A", value="10.0.0.9", zone="example.com", ttl=120))
    args = c.change_resource_record_sets.call_args.kwargs
    assert args["HostedZoneId"] == "/hostedzone/Z1"
    change = args["ChangeBatch"]["Changes"][0]
    assert change["Action"] == "UPSERT"
    rrs = change["ResourceRecordSet"]
    assert rrs["Name"] == "new.example.com" and rrs["Type"] == "A" and rrs["TTL"] == 120
    assert rrs["ResourceRecords"] == [{"Value": "10.0.0.9"}]


def test_delete_record_deletes():
    c = _client_with_zones()
    p = _provider(c)
    p.delete_record(DNSRecord(name="web.example.com", record_type="A", value="10.0.0.5", zone="example.com", ttl=300))
    change = c.change_resource_record_sets.call_args.kwargs["ChangeBatch"]["Changes"][0]
    assert change["Action"] == "DELETE"
    assert change["ResourceRecordSet"]["Name"] == "web.example.com"
