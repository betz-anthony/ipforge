from ipforge_client.models import DNSRecord
from ipforge_client.resources.dns import DNS


def test_list_records_paginated(fake):
    fake.set("GET", "/dns/zones/ex.com/records",
             {"items": [{"name": "a", "record_type": "A", "value": "10.0.0.1"}],
              "total": 1, "limit": 200, "offset": 0})
    out = list(DNS(fake).list_records("ex.com", q="a"))
    assert out[0].record_type == "A"
    assert fake.calls[0][2]["q"] == "a"


def test_create_record_register_ptr(fake):
    fake.set("POST", "/dns/zones/ex.com/records", {"name": "web"})
    DNS(fake).create_record("ex.com", register_ptr=True, name="web", record_type="A", value="10.0.0.5")
    body = fake.calls[0][3]
    assert body["register_ptr"] is True and body["name"] == "web"


def test_delete_record_sends_record_body(fake):
    rec = DNSRecord({"name": "web", "record_type": "A", "value": "10.0.0.5", "zone": "ex.com"})
    DNS(fake).delete_record("ex.com", rec, delete_ptr=True)
    m, p, params, body = fake.calls[0]
    assert (m, p) == ("DELETE", "/dns/zones/ex.com/records")
    assert body["name"] == "web" and body["delete_ptr"] is True
