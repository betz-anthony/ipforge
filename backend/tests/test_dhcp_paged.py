from app.models.cache import CachedDHCPLease
from app.core.time import utcnow


def _lease(db, scope_id="scope1", ip="10.0.0.1", mac="aa:bb:cc:dd:ee:01",
           name="host1", source="keadhcp"):
    db.add(CachedDHCPLease(scope_id=scope_id, ip_address=ip, mac_address=mac,
                            name=name, source=source, synced_at=utcnow()))
    db.commit()


def test_list_leases_returns_envelope(client, db):
    _lease(db)
    r = client.get("/api/v1/dhcp/scopes/scope1/leases")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body


def test_list_leases_q_matches_ip(client, db):
    _lease(db, ip="10.0.0.10", name="web")
    _lease(db, ip="10.0.0.20", name="db")
    r = client.get("/api/v1/dhcp/scopes/scope1/leases?q=10.0.0.10")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["ip_address"] == "10.0.0.10"


def test_list_leases_q_matches_name(client, db):
    _lease(db, ip="10.0.0.1", name="webapp")
    _lease(db, ip="10.0.0.2", name="database")
    r = client.get("/api/v1/dhcp/scopes/scope1/leases?q=webapp")
    assert r.json()["total"] == 1


def test_list_leases_sort_ip_asc(client, db):
    _lease(db, ip="10.0.0.5", name="z")
    _lease(db, ip="10.0.0.1", name="a")
    r = client.get("/api/v1/dhcp/scopes/scope1/leases?sort=ip_address&dir=asc")
    ips = [i["ip_address"] for i in r.json()["items"]]
    assert ips == sorted(ips)


def test_list_leases_sort_ip_asc_is_numeric_not_lexicographic(client, db):
    for ip in ["10.10.1.100", "10.10.1.1", "10.10.1.103", "10.10.1.11"]:
        _lease(db, ip=ip)
    r = client.get("/api/v1/dhcp/scopes/scope1/leases?sort=ip_address&dir=asc")
    ips = [i["ip_address"] for i in r.json()["items"]]
    assert ips == ["10.10.1.1", "10.10.1.11", "10.10.1.100", "10.10.1.103"]


def test_list_leases_unknown_sort_ignored(client, db):
    _lease(db)
    r = client.get("/api/v1/dhcp/scopes/scope1/leases?sort=drop_table")
    assert r.status_code == 200
    assert "items" in r.json()


def _scope(db, scope_id="scope1", start="10.0.0.10", end="10.0.0.19", source="keadhcp"):
    from app.models.cache import CachedDHCPScope
    db.add(CachedDHCPScope(scope_id=scope_id, name="s", subnet_mask="/24",
                           start_range=start, end_range=end, source=source,
                           synced_at=utcnow()))
    db.commit()


def test_scope_pool_utilization_is_scope_wide_and_in_pool_only(client, db):
    _scope(db)
    for i in range(10, 15):
        _lease(db, ip=f"10.0.0.{i}", mac=f"aa:bb:cc:dd:ee:{i:02x}", name=f"h{i}")
    _lease(db, ip="10.0.0.200", mac="aa:bb:cc:dd:ee:c8", name="outside")
    scope = client.get("/api/v1/dhcp/scopes").json()[0]
    assert scope["pool_size"] == 10
    assert scope["pool_used"] == 5


def test_scope_pool_utilization_sums_multiple_pools(client, db):
    from app.models.cache import CachedDHCPScopePool
    _scope(db, start="10.0.0.10", end="10.0.0.200")
    db.add_all([
        CachedDHCPScopePool(scope_id="scope1", source="keadhcp",
                            start_ip="10.0.0.10", end_ip="10.0.0.19"),
        CachedDHCPScopePool(scope_id="scope1", source="keadhcp",
                            start_ip="10.0.0.100", end_ip="10.0.0.109"),
    ])
    db.commit()
    _lease(db, ip="10.0.0.12")
    _lease(db, ip="10.0.0.50", mac="aa:bb:cc:dd:ee:02")  # gap between pools
    _lease(db, ip="10.0.0.101", mac="aa:bb:cc:dd:ee:03")
    scope = client.get("/api/v1/dhcp/scopes").json()[0]
    assert (scope["pool_size"], scope["pool_used"]) == (20, 2)


def test_scope_lease_count_is_unfiltered_and_counts_static_in_pool(client, db):
    _scope(db)
    _lease(db, ip="10.0.0.10", mac="aa:bb:cc:dd:ee:01", name="static-a")
    _lease(db, ip="10.0.0.11", mac="aa:bb:cc:dd:ee:02", name="static-b")
    _lease(db, ip="10.0.0.200", mac="aa:bb:cc:dd:ee:03", name="outside")
    scope = client.get("/api/v1/dhcp/scopes").json()[0]
    assert scope["lease_count"] == 3
    assert scope["pool_used"] == 2
