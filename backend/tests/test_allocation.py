import ipaddress
from unittest.mock import MagicMock, patch
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.providers.dhcp.base import DHCPScope


def _subnet(db, cidr="10.0.1.0/24", name="test", **kwargs):
    s = Subnet(name=name, cidr=cidr, ip_version=4, **kwargs)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ── basic allocation ──────────────────────────────────────────────────────────

def test_allocate_returns_lowest_available(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["address"] == "10.0.1.2"  # .1 skipped
    assert body["hostname"] == "web-01"
    assert body["status"] == "reserved"
    assert body["is_new"] is True
    assert body["subnet_cidr"] == "10.0.1.0/24"


def test_allocate_skips_dot_one(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert not r.json()["address"].endswith(".1")


def test_allocate_skips_dot_255(client, db):
    # Use /16 so .255 is a valid host. Fill .2-.254 to force candidate into .255 range.
    s = _subnet(db, cidr="10.0.0.0/16")
    for b in range(2, 255):
        db.add(IPAddress(address=f"10.0.0.{b}", subnet_id=s.id, status=AddressStatus.reserved))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    # 10.0.0.255 is skipped; next candidate is 10.0.1.2
    assert r.json()["address"] == "10.0.1.2"


def test_allocate_skips_discovered(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id, status=AddressStatus.discovered))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    assert r.json()["address"] == "10.0.1.3"  # .1 and .2(discovered) skipped


def test_allocate_reuses_available_record(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id, status=AddressStatus.available))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "h"})
    assert r.status_code == 201
    assert r.json()["address"] == "10.0.1.2"
    addr = db.query(IPAddress).filter_by(address="10.0.1.2").first()
    assert addr.status == AddressStatus.reserved


def test_allocate_hostname_stored_lowercase(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "Web-01"})
    assert r.json()["hostname"] == "web-01"


def test_allocate_subnet_exhausted(client, db):
    # /30: hosts = .1,.2 → skip .1 → only .2 allocatable
    s = _subnet(db, cidr="10.0.0.0/30")
    db.add(IPAddress(address="10.0.0.2", subnet_id=s.id, status=AddressStatus.reserved))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "new"})
    assert r.status_code == 409


def test_allocate_subnet_not_found(client, db):
    r = client.post("/api/subnets/9999/allocate", json={"hostname": "web-01"})
    assert r.status_code == 404


def test_allocate_missing_hostname(client, db):
    s = _subnet(db)
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": ""})
    assert r.status_code == 422


# ── idempotency ───────────────────────────────────────────────────────────────

def test_allocate_idempotent_returns_same_ip(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    r2 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["address"] == r2.json()["address"]
    assert r2.json()["is_new"] is False
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 1


def test_allocate_idempotent_case_insensitive(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "Web-01"})
    r2 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "WEB-01"})
    assert r1.json()["address"] == r2.json()["address"]
    assert db.query(IPAddress).filter_by(subnet_id=s.id).count() == 1


def test_allocate_idempotent_updates_mac_if_blank(client, db):
    s = _subnet(db)
    r1 = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    client.post(f"/api/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "aa:bb:cc:dd:ee:ff"})
    addr = db.query(IPAddress).filter_by(address=r1.json()["address"]).first()
    db.refresh(addr)
    assert addr.mac_address == "aa:bb:cc:dd:ee:ff"


def test_allocate_idempotent_does_not_overwrite_existing_mac(client, db):
    s = _subnet(db)
    client.post(f"/api/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "11:22:33:44:55:66"})
    client.post(f"/api/subnets/{s.id}/allocate",
                json={"hostname": "web-01", "mac_address": "aa:bb:cc:dd:ee:ff"})
    addr = db.query(IPAddress).filter_by(hostname="web-01").first()
    db.refresh(addr)
    assert addr.mac_address == "11:22:33:44:55:66"  # original preserved


def test_allocate_deprecated_hostname_gets_new_ip(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.1.2", subnet_id=s.id,
                     hostname="web-01", status=AddressStatus.deprecated))
    db.commit()
    r = client.post(f"/api/subnets/{s.id}/allocate", json={"hostname": "web-01"})
    assert r.status_code == 201
    assert r.json()["is_new"] is True
    assert r.json()["address"] == "10.0.1.3"  # deprecated is in _INELIGIBLE, so .2 is skipped
