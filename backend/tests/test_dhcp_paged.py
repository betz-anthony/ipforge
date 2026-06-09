from app.models.cache import CachedDHCPLease
from app.core.time import utcnow


def _lease(db, scope_id="scope1", ip="10.0.0.1", mac="aa:bb:cc:dd:ee:01",
           name="host1", source="keadhcp"):
    db.add(CachedDHCPLease(scope_id=scope_id, ip_address=ip, mac_address=mac,
                            name=name, source=source, synced_at=utcnow()))
    db.commit()


def test_list_leases_returns_envelope(client, db):
    _lease(db)
    r = client.get("/api/dhcp/scopes/scope1/leases")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body


def test_list_leases_q_matches_ip(client, db):
    _lease(db, ip="10.0.0.10", name="web")
    _lease(db, ip="10.0.0.20", name="db")
    r = client.get("/api/dhcp/scopes/scope1/leases?q=10.0.0.10")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["ip_address"] == "10.0.0.10"


def test_list_leases_q_matches_name(client, db):
    _lease(db, ip="10.0.0.1", name="webapp")
    _lease(db, ip="10.0.0.2", name="database")
    r = client.get("/api/dhcp/scopes/scope1/leases?q=webapp")
    assert r.json()["total"] == 1


def test_list_leases_sort_ip_asc(client, db):
    _lease(db, ip="10.0.0.5", name="z")
    _lease(db, ip="10.0.0.1", name="a")
    r = client.get("/api/dhcp/scopes/scope1/leases?sort=ip_address&dir=asc")
    ips = [i["ip_address"] for i in r.json()["items"]]
    assert ips == sorted(ips)


def test_list_leases_unknown_sort_ignored(client, db):
    _lease(db)
    r = client.get("/api/dhcp/scopes/scope1/leases?sort=drop_table")
    assert r.status_code == 200
    assert "items" in r.json()
