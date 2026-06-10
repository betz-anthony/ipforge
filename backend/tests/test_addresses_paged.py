# backend/tests/test_addresses_paged.py
import pytest
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus


def _subnet(db, cidr="10.0.0.0/24"):
    s = Subnet(name="Net", cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    return s


def _addr(db, subnet_id, ip, hostname=None, status=AddressStatus.assigned, mac=None, desc=None):
    a = IPAddress(address=ip, subnet_id=subnet_id, hostname=hostname,
                  status=status, mac_address=mac, description=desc)
    db.add(a)
    db.commit()
    return a


def test_list_addresses_returns_envelope(client, db):
    sn = _subnet(db)
    _addr(db, sn.id, "10.0.0.1")
    r = client.get("/api/v1/addresses")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "limit" in body
    assert "offset" in body
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_list_addresses_q_ilike(client, db):
    sn = _subnet(db)
    _addr(db, sn.id, "10.0.0.1", hostname="web-prod")
    _addr(db, sn.id, "10.0.0.2", hostname="db-prod")
    _addr(db, sn.id, "10.0.0.3", hostname="cache")
    r = client.get("/api/v1/addresses?q=prod")
    body = r.json()
    assert body["total"] == 2
    assert {a["hostname"] for a in body["items"]} == {"web-prod", "db-prod"}


def test_list_addresses_q_matches_ip(client, db):
    sn = _subnet(db)
    _addr(db, sn.id, "10.0.0.99")
    _addr(db, sn.id, "10.0.0.100")
    r = client.get("/api/v1/addresses?q=10.0.0.99")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["address"] == "10.0.0.99"


def test_list_addresses_sort_hostname_asc(client, db):
    sn = _subnet(db)
    _addr(db, sn.id, "10.0.0.1", hostname="zebra")
    _addr(db, sn.id, "10.0.0.2", hostname="alpha")
    r = client.get("/api/v1/addresses?sort=hostname&dir=asc")
    items = r.json()["items"]
    hostnames = [a["hostname"] for a in items]
    assert hostnames == sorted(hostnames)


def test_list_addresses_sort_hostname_desc(client, db):
    sn = _subnet(db)
    _addr(db, sn.id, "10.0.0.1", hostname="alpha")
    _addr(db, sn.id, "10.0.0.2", hostname="zebra")
    r = client.get("/api/v1/addresses?sort=hostname&dir=desc")
    items = r.json()["items"]
    hostnames = [a["hostname"] for a in items]
    assert hostnames == sorted(hostnames, reverse=True)


def test_list_addresses_offset_window(client, db):
    sn = _subnet(db)
    for i in range(1, 6):
        _addr(db, sn.id, f"10.0.0.{i}")
    r = client.get("/api/v1/addresses?sort=address&dir=asc&limit=2&offset=2")
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["items"][0]["address"] == "10.0.0.3"


def test_list_addresses_total_honors_filters(client, db):
    sn = _subnet(db)
    _addr(db, sn.id, "10.0.0.1", status=AddressStatus.assigned)
    _addr(db, sn.id, "10.0.0.2", status=AddressStatus.assigned)
    _addr(db, sn.id, "10.0.0.3", status=AddressStatus.available)
    r = client.get("/api/v1/addresses?status=assigned")
    body = r.json()
    assert body["total"] == 2
    assert all(a["status"] == "assigned" for a in body["items"])


def test_list_addresses_unknown_sort_ignored(client, db):
    sn = _subnet(db)
    _addr(db, sn.id, "10.0.0.1")
    r = client.get("/api/v1/addresses?sort=injected_column&dir=asc")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
