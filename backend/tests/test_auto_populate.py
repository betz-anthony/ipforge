from datetime import datetime, timezone

import pytest

from app.models.address import IPAddress, AddressStatus
from app.models.cache import CachedDNSRecord, CachedDHCPLease
from app.models.subnet import Subnet
from app.sync import _auto_populate_from_cache, _ip_in_cidr


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _subnet(db, cidr="10.0.0.0/24", name="Net"):
    s = Subnet(name=name, cidr=cidr)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _dns_a(db, name, value, zone="example.com", source="msdns"):
    r = CachedDNSRecord(
        name=name, record_type="A", value=value,
        zone=zone, ttl=300, source=source, synced_at=_now(),
    )
    db.add(r)
    db.commit()


def _dhcp_lease(db, ip, name=None, mac=None, scope_id="10.0.0.0", source="msdhcp"):
    l = CachedDHCPLease(
        scope_id=scope_id, ip_address=ip,
        mac_address=mac, name=name,
        source=source, synced_at=_now(),
    )
    db.add(l)
    db.commit()


# ── _ip_in_cidr ──────────────────────────────────────────────────────────────

def test_ip_in_cidr_match():
    assert _ip_in_cidr("10.0.0.5", "10.0.0.0/24") is True


def test_ip_in_cidr_no_match():
    assert _ip_in_cidr("192.168.1.1", "10.0.0.0/24") is False


def test_ip_in_cidr_bad_input():
    assert _ip_in_cidr("notanip", "10.0.0.0/24") is False


# ── auto-populate: create ─────────────────────────────────────────────────────

def test_dns_a_record_creates_ipam_entry(db):
    _subnet(db)
    _dns_a(db, "server01", "10.0.0.5")

    _auto_populate_from_cache(db)

    addr = db.query(IPAddress).filter_by(address="10.0.0.5").first()
    assert addr is not None
    assert addr.hostname == "server01"
    assert addr.status == AddressStatus.assigned


def test_dhcp_lease_creates_ipam_entry(db):
    _subnet(db)
    _dhcp_lease(db, "10.0.0.10", name="desktop01", mac="AA-BB-CC-DD-EE-FF")

    _auto_populate_from_cache(db)

    addr = db.query(IPAddress).filter_by(address="10.0.0.10").first()
    assert addr is not None
    assert addr.hostname == "desktop01"
    assert addr.mac_address == "AA-BB-CC-DD-EE-FF"
    assert addr.status == AddressStatus.assigned


def test_ip_outside_all_subnets_skipped(db):
    _subnet(db, cidr="10.0.0.0/24")
    _dns_a(db, "external", "192.168.1.50")

    _auto_populate_from_cache(db)

    assert db.query(IPAddress).count() == 0


def test_no_subnets_does_nothing(db):
    _dns_a(db, "server01", "10.0.0.5")

    _auto_populate_from_cache(db)

    assert db.query(IPAddress).count() == 0


def test_existing_address_not_duplicated(db):
    s = _subnet(db)
    existing = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned)
    db.add(existing)
    db.commit()

    _dns_a(db, "server01", "10.0.0.5")
    _auto_populate_from_cache(db)

    assert db.query(IPAddress).filter_by(address="10.0.0.5").count() == 1


# ── auto-populate: upsert fields ─────────────────────────────────────────────

def test_existing_record_gets_hostname_from_dhcp(db):
    s = _subnet(db)
    existing = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned)
    db.add(existing)
    db.commit()

    _dhcp_lease(db, "10.0.0.5", name="newname", mac="AA-BB-CC-DD-EE-FF")
    _auto_populate_from_cache(db)

    db.refresh(existing)
    assert existing.hostname == "newname"
    assert existing.mac_address == "AA-BB-CC-DD-EE-FF"


def test_existing_hostname_not_overwritten(db):
    s = _subnet(db)
    existing = IPAddress(
        address="10.0.0.5", subnet_id=s.id,
        status=AddressStatus.assigned, hostname="manual-name",
    )
    db.add(existing)
    db.commit()

    _dhcp_lease(db, "10.0.0.5", name="dhcp-name")
    _auto_populate_from_cache(db)

    db.refresh(existing)
    assert existing.hostname == "manual-name"


def test_dhcp_overwrites_dns_hostname_for_new_ip(db):
    _subnet(db)
    _dns_a(db, "dns-name", "10.0.0.20")
    _dhcp_lease(db, "10.0.0.20", name="dhcp-name", mac="11-22-33-44-55-66")

    _auto_populate_from_cache(db)

    addr = db.query(IPAddress).filter_by(address="10.0.0.20").first()
    assert addr.hostname == "dhcp-name"
    assert addr.mac_address == "11-22-33-44-55-66"


def test_aaaa_record_not_created(db):
    _subnet(db, cidr="10.0.0.0/24")
    r = CachedDNSRecord(
        name="v6host", record_type="AAAA", value="2001:db8::1",
        zone="example.com", ttl=300, source="msdns", synced_at=_now(),
    )
    db.add(r)
    db.commit()

    # No IPv6 subnet — should be skipped
    _auto_populate_from_cache(db)
    assert db.query(IPAddress).count() == 0


def test_idempotent_multiple_calls(db):
    _subnet(db)
    _dns_a(db, "server01", "10.0.0.5")

    _auto_populate_from_cache(db)
    _auto_populate_from_cache(db)

    assert db.query(IPAddress).filter_by(address="10.0.0.5").count() == 1
