"""Tests for stale cache cleanup (STALE-CACHE-001)."""
from app.models.cache import (
    CachedDNSZone, CachedDNSRecord, CachedDHCPScope, CachedDHCPLease, SyncStatus,
)
from app.models.provider_config import ProviderConfig
from datetime import datetime


def _now():
    return datetime.utcnow()


def _add_dns_cache(db, source: str):
    db.add(CachedDNSZone(source=source, zone="example.com", synced_at=_now()))
    db.add(CachedDNSRecord(
        source=source, name="host.example.com", record_type="A",
        value="1.2.3.4", zone="example.com", ttl=300, synced_at=_now(),
    ))
    db.commit()


def _add_dhcp_cache(db, source: str):
    db.add(CachedDHCPScope(
        source=source, scope_id="10.0.0.0/24", name="Corp",
        start_range="10.0.0.1", end_range="10.0.0.254",
        subnet_mask="255.255.255.0", synced_at=_now(),
    ))
    db.add(CachedDHCPLease(
        source=source, scope_id="10.0.0.0/24", ip_address="10.0.0.5",
        name="host", synced_at=_now(),
    ))
    db.commit()


# ── purge endpoint ───────────────────────────────────────────────────────────

def test_purge_dns_cache_deletes_zones_and_records(client, db):
    _add_dns_cache(db, "msdns-prod")
    _add_dns_cache(db, "msdns-other")

    r = client.delete("/api/v1/cache/dns", params={"source": "msdns-prod"})
    assert r.status_code == 200
    data = r.json()
    assert data["deleted"] == 2  # 1 zone + 1 record
    assert data["source"] == "msdns-prod"

    assert db.query(CachedDNSZone).filter_by(source="msdns-prod").count() == 0
    assert db.query(CachedDNSRecord).filter_by(source="msdns-prod").count() == 0
    # other source untouched
    assert db.query(CachedDNSZone).filter_by(source="msdns-other").count() == 1


def test_purge_dhcp_cache_deletes_scopes_and_leases(client, db):
    _add_dhcp_cache(db, "msdhcp-prod")

    r = client.delete("/api/v1/cache/dhcp", params={"source": "msdhcp-prod"})
    assert r.status_code == 200
    assert r.json()["deleted"] == 2  # 1 scope + 1 lease

    assert db.query(CachedDHCPScope).filter_by(source="msdhcp-prod").count() == 0
    assert db.query(CachedDHCPLease).filter_by(source="msdhcp-prod").count() == 0


def test_purge_nonexistent_source_returns_zero(client, db):
    r = client.delete("/api/v1/cache/dns", params={"source": "ghost"})
    assert r.status_code == 200
    assert r.json()["deleted"] == 0


def test_purge_invalid_category_returns_400(client, db):
    r = client.delete("/api/v1/cache/foobar", params={"source": "x"})
    assert r.status_code == 400


def test_purge_missing_source_returns_422(client, db):
    r = client.delete("/api/v1/cache/dns")
    assert r.status_code == 422


# ── auto-purge on provider delete ────────────────────────────────────────────

def test_delete_provider_config_purges_cache(client, db):
    _add_dns_cache(db, "msdns-todelete")
    row = ProviderConfig(
        category="dns", provider_type="msdns",
        name="msdns-todelete", config="{}", enabled=True, sort_order=0,
    )
    db.add(row)
    db.commit()

    r = client.delete(f"/api/v1/provider-configs/{row.id}")
    assert r.status_code == 204

    assert db.query(CachedDNSZone).filter_by(source="msdns-todelete").count() == 0
    assert db.query(CachedDNSRecord).filter_by(source="msdns-todelete").count() == 0


def test_delete_dhcp_provider_config_purges_cache(client, db):
    _add_dhcp_cache(db, "msdhcp-todelete")
    row = ProviderConfig(
        category="dhcp", provider_type="msdhcp",
        name="msdhcp-todelete", config="{}", enabled=True, sort_order=0,
    )
    db.add(row)
    db.commit()

    r = client.delete(f"/api/v1/provider-configs/{row.id}")
    assert r.status_code == 204

    assert db.query(CachedDHCPScope).filter_by(source="msdhcp-todelete").count() == 0
    assert db.query(CachedDHCPLease).filter_by(source="msdhcp-todelete").count() == 0


def test_delete_provider_config_only_purges_own_source(client, db):
    _add_dns_cache(db, "msdns-keep")
    _add_dns_cache(db, "msdns-todelete2")
    row = ProviderConfig(
        category="dns", provider_type="msdns",
        name="msdns-todelete2", config="{}", enabled=True, sort_order=0,
    )
    db.add(row)
    db.commit()

    client.delete(f"/api/v1/provider-configs/{row.id}")

    assert db.query(CachedDNSZone).filter_by(source="msdns-keep").count() == 1
