"""Regression: the DNS records type filter (and its chip counts) only ever
reflected whatever 50 records happened to be on the current page, not the
whole zone — at real scale (thousands of records) that made both the chips
and the filter itself wrong. record_type is now a real server-side filter,
and record-type-counts is a zone-wide aggregate independent of pagination."""
from app.core.time import utcnow
from app.models.cache import CachedDNSRecord


def _seed(db, n_a=3, n_cname=2, n_txt=1, zone="example.com"):
    now = utcnow()
    for i in range(n_a):
        db.add(CachedDNSRecord(name=f"a{i}", record_type="A", value=f"10.0.0.{i}",
                                zone=zone, ttl=3600, source="bind01", synced_at=now))
    for i in range(n_cname):
        db.add(CachedDNSRecord(name=f"c{i}", record_type="CNAME", value=f"target{i}.{zone}",
                                zone=zone, ttl=3600, source="bind01", synced_at=now))
    for i in range(n_txt):
        db.add(CachedDNSRecord(name=f"t{i}", record_type="TXT", value="v=spf1 ~all",
                                zone=zone, ttl=3600, source="bind01", synced_at=now))
    db.commit()


def test_list_records_filters_by_record_type(client, db):
    _seed(db)
    r = client.get("/api/v1/dns/zones/example.com/records", params={"record_type": "CNAME"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert all(item["record_type"] == "CNAME" for item in body["items"])


def test_list_records_type_filter_survives_pagination(client, db):
    # 10 A records + 1 CNAME. Page size 5, sorted by name: CNAME (name "c0")
    # sorts before "a*" alphabetically only if... use a name that sorts LAST
    # so a page-1-only client-side filter would have missed it entirely.
    _seed(db, n_a=10, n_cname=0, n_txt=0)
    db.add(CachedDNSRecord(name="zzz-last", record_type="CNAME", value="target.example.com",
                            zone="example.com", ttl=3600, source="bind01", synced_at=utcnow()))
    db.commit()
    r = client.get("/api/v1/dns/zones/example.com/records",
                    params={"record_type": "CNAME", "sort": "name", "limit": 5, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "zzz-last"


def test_record_type_counts_is_zone_wide_not_page_scoped(client, db):
    _seed(db, n_a=60, n_cname=2, n_txt=1)  # more than one page at the default limit
    r = client.get("/api/v1/dns/zones/example.com/record-type-counts")
    assert r.status_code == 200
    counts = {row["record_type"]: row["count"] for row in r.json()}
    assert counts == {"A": 60, "CNAME": 2, "TXT": 1}


def test_record_type_counts_scoped_to_zone(client, db):
    _seed(db, n_a=1, n_cname=1, n_txt=0, zone="example.com")
    _seed(db, n_a=5, n_cname=0, n_txt=0, zone="other.com")
    r = client.get("/api/v1/dns/zones/example.com/record-type-counts")
    counts = {row["record_type"]: row["count"] for row in r.json()}
    assert counts == {"A": 1, "CNAME": 1}
