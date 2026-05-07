from datetime import datetime, timezone
from app.models.cache import CachedDNSRecord, CachedDHCPScope, CachedDHCPLease


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── DNS by-IP ──────────────────────────────────────────────────────────────

def test_dns_by_ip_returns_matching_records(client, db):
    db.add(CachedDNSRecord(
        name="plex.local", record_type="A", value="10.0.0.5",
        zone="local", ttl=300, source="msdns", synced_at=_now(),
    ))
    db.add(CachedDNSRecord(
        name="other.local", record_type="A", value="10.0.0.6",
        zone="local", ttl=300, source="msdns", synced_at=_now(),
    ))
    db.flush()

    r = client.get("/api/dns/by-ip/10.0.0.5")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "plex.local"
    assert data[0]["record_type"] == "A"
    assert data[0]["value"] == "10.0.0.5"


def test_dns_by_ip_returns_empty_when_not_found(client):
    r = client.get("/api/dns/by-ip/192.168.99.99")
    assert r.status_code == 200
    assert r.json() == []


def test_dns_by_ip_returns_multiple_records(client, db):
    for name in ("a.local", "b.local"):
        db.add(CachedDNSRecord(
            name=name, record_type="A", value="10.0.0.10",
            zone="local", ttl=300, source="msdns", synced_at=_now(),
        ))
    db.flush()

    r = client.get("/api/dns/by-ip/10.0.0.10")
    assert r.status_code == 200
    assert len(r.json()) == 2


# ── DHCP by-IP ─────────────────────────────────────────────────────────────

def test_dhcp_by_ip_returns_matching_leases(client, db):
    db.add(CachedDHCPLease(
        scope_id="192.168.1.0", ip_address="192.168.1.105",
        mac_address="AA-BB-CC-DD-EE-FF", client_duid="", iaid=0,
        name="server01", description="rack A", source="msdhcp", synced_at=_now(),
    ))
    db.flush()

    r = client.get("/api/dhcp/by-ip/192.168.1.105")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["ip_address"] == "192.168.1.105"
    assert data[0]["mac_address"] == "AA-BB-CC-DD-EE-FF"
    assert data[0]["name"] == "server01"


def test_dhcp_by_ip_returns_empty_when_not_found(client):
    r = client.get("/api/dhcp/by-ip/10.99.99.99")
    assert r.status_code == 200
    assert r.json() == []
