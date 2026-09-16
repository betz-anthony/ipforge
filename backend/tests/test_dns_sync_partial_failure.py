"""Regression: sync_dns() wiped a provider's ENTIRE cache (all zones) before
reinserting only the zones whose get_records() succeeded — a single zone
timing out (e.g. a very large zone taking longer post the CNAME/NS fix)
meant that zone's last-known-good cache was deleted and never replaced,
instead of being left alone until the next successful sync."""
from unittest.mock import patch

from app.providers.dns.base import DNSRecord
from app.models.cache import CachedDNSZone, CachedDNSRecord
from app.core.time import utcnow
from tests.conftest import TestingSessionLocal


class _PartiallyFailingProvider:
    source = "msdns01"

    def get_zones(self):
        return ["ok.example.com", "big.example.com"]

    def get_records(self, zone):
        if zone == "big.example.com":
            raise RuntimeError("WinRM operation timed out")
        return [DNSRecord(name="www", record_type="A", value="10.0.0.1",
                           zone=zone, ttl=3600, source=self.source)]


def _make_session():
    return TestingSessionLocal()


def test_partial_dns_sync_failure_preserves_the_failing_zones_cache():
    from app import sync as sync_module

    now = utcnow()
    db = TestingSessionLocal()
    db.add(CachedDNSZone(zone="big.example.com", source="msdns01", synced_at=now))
    db.add(CachedDNSRecord(name="stale-but-real", record_type="A", value="10.0.0.9",
                            zone="big.example.com", ttl=3600, source="msdns01", synced_at=now))
    db.add(CachedDNSZone(zone="ok.example.com", source="msdns01", synced_at=now))
    db.add(CachedDNSRecord(name="old", record_type="A", value="10.0.0.2",
                            zone="ok.example.com", ttl=3600, source="msdns01", synced_at=now))
    db.commit()
    db.close()

    with patch("app.providers.registry.get_dns_providers",
               return_value=[_PartiallyFailingProvider()]), \
         patch("app.sync.SessionLocal", side_effect=_make_session), \
         patch("app.providers.registry.get_dhcp_providers", return_value=[]):
        sync_module.sync_dns()

    db = TestingSessionLocal()
    try:
        big_records = db.query(CachedDNSRecord).filter_by(zone="big.example.com").all()
        assert len(big_records) == 1, "the failing zone's last-known-good cache must survive"
        assert big_records[0].name == "stale-but-real"

        ok_records = db.query(CachedDNSRecord).filter_by(zone="ok.example.com").all()
        assert len(ok_records) == 1
        assert ok_records[0].name == "www", "the succeeding zone must still refresh normally"
    finally:
        db.close()
