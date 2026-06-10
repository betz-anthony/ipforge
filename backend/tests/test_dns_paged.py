# backend/tests/test_dns_paged.py
from app.models.cache import CachedDNSRecord, CachedDNSZone
from app.core.time import utcnow


def _zone(db, zone="example.com", source="bind"):
    db.add(CachedDNSZone(zone=zone, source=source, synced_at=utcnow()))
    db.commit()


def _record(db, zone="example.com", name="host", rtype="A", value="10.0.0.1", source="bind"):
    db.add(CachedDNSRecord(
        zone=zone, name=name, record_type=rtype, value=value,
        source=source, synced_at=utcnow(),
    ))
    db.commit()


def test_list_records_returns_envelope(client, db):
    _zone(db)
    _record(db)
    r = client.get("/api/v1/dns/zones/example.com/records")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body


def test_list_records_q_matches_name(client, db):
    _zone(db)
    _record(db, name="web-01")
    _record(db, name="db-01")
    r = client.get("/api/v1/dns/zones/example.com/records?q=web")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "web-01"


def test_list_records_q_matches_value(client, db):
    _zone(db)
    _record(db, name="a", value="10.0.0.50")
    _record(db, name="b", value="10.0.0.51")
    r = client.get("/api/v1/dns/zones/example.com/records?q=10.0.0.50")
    assert r.json()["total"] == 1


def test_list_records_sort_name_asc(client, db):
    _zone(db)
    _record(db, name="zebra")
    _record(db, name="alpha")
    r = client.get("/api/v1/dns/zones/example.com/records?sort=name&dir=asc")
    names = [i["name"] for i in r.json()["items"]]
    assert names == sorted(names)


def test_list_records_unknown_sort_ignored(client, db):
    _zone(db)
    _record(db)
    r = client.get("/api/v1/dns/zones/example.com/records?sort=drop_table&dir=asc")
    assert r.status_code == 200
    assert "items" in r.json()
