from datetime import datetime

from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDHCPLease, CachedDNSRecord


def test_search_requires_min_2_chars(client):
    r = client.get("/api/search?q=a")
    assert r.status_code == 422


def test_search_missing_q(client):
    r = client.get("/api/search")
    assert r.status_code == 422


def test_search_allows_2_char_query(client):
    r = client.get("/api/search?q=ab")
    assert r.status_code == 200


def test_search_returns_empty_on_no_match(client):
    r = client.get("/api/search?q=zzz")
    assert r.status_code == 200
    data = r.json()
    assert data["subnets"] == []
    assert data["addresses"] == []
    assert data["leases"] == []
    assert data["records"] == []


def test_search_matches_subnet_name(client, db):
    db.add(Subnet(name="CoreNet", cidr="10.0.0.0/24", ip_version=4))
    db.commit()
    r = client.get("/api/search?q=core")
    assert r.status_code == 200
    assert any(s["name"] == "CoreNet" for s in r.json()["subnets"])


def test_search_matches_subnet_cidr(client, db):
    db.add(Subnet(name="Net", cidr="192.168.50.0/24", ip_version=4))
    db.commit()
    r = client.get("/api/search?q=192.168.50")
    assert r.status_code == 200
    assert any(s["cidr"] == "192.168.50.0/24" for s in r.json()["subnets"])


def test_search_matches_address_hostname(client, db):
    s = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, hostname="webserver01", status=AddressStatus.assigned))
    db.commit()
    r = client.get("/api/search?q=webserver")
    assert r.status_code == 200
    assert any(a["hostname"] == "webserver01" for a in r.json()["addresses"])


def test_search_matches_address_ip(client, db):
    s = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    db.add(IPAddress(address="10.0.0.42", subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()
    r = client.get("/api/search?q=10.0.0.42")
    assert r.status_code == 200
    assert any(a["address"] == "10.0.0.42" for a in r.json()["addresses"])


def test_search_matches_dhcp_lease(client, db):
    db.add(CachedDHCPLease(
        scope_id="10.0.0.0", ip_address="10.0.0.10",
        mac_address="aa:bb:cc:dd:ee:ff", name="printer01", source="msdhcp",
        synced_at=datetime.utcnow(),
    ))
    db.commit()
    r = client.get("/api/search?q=printer")
    assert r.status_code == 200
    assert any(l["name"] == "printer01" for l in r.json()["leases"])


def test_search_matches_dns_record(client, db):
    db.add(CachedDNSRecord(
        name="mail.example.com", record_type="A", value="10.0.0.25",
        zone="example.com", source="msdns", synced_at=datetime.utcnow(),
    ))
    db.commit()
    r = client.get("/api/search?q=mail.example")
    assert r.status_code == 200
    assert any(rec["name"] == "mail.example.com" for rec in r.json()["records"])


def test_search_is_case_insensitive(client, db):
    db.add(Subnet(name="Management", cidr="10.1.0.0/24", ip_version=4))
    db.commit()
    r = client.get("/api/search?q=MANAGEMENT")
    assert r.status_code == 200
    assert any(s["name"] == "Management" for s in r.json()["subnets"])


def test_search_result_limit(client, db):
    for i in range(60):
        db.add(Subnet(name=f"Net{i:03d}", cidr=f"10.{i}.0.0/24", ip_version=4))
    db.commit()
    r = client.get("/api/search?q=Net")
    assert r.status_code == 200
    assert len(r.json()["subnets"]) <= 50
