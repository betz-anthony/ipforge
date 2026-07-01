# backend/tests/test_drift_perf.py
"""Characterization test for DRIFT-PERF-001: locks detect_drift's output + emit
events so the N+1 refactor can be proven behavior-preserving."""
from collections import Counter

from app.drift import detect_drift
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.scan import DriftItem, DriftCategory
from app.models.cache import CachedDNSRecord, CachedDHCPLease
from app.core.time import utcnow
from app.alerting.emit import drain_queue


def _rows(db):
    return {
        (d.ip_address, d.category, d.resolved)
        for d in db.query(DriftItem).all()
    }


def _fixture(db):
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    # a1: assigned, no DNS/DHCP -> missing_dns + missing_dhcp
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id,
                     status=AddressStatus.assigned, hostname="web"))
    # a2: assigned, has matching DNS + DHCP -> no missing_* ; give it a MAC mismatch
    db.add(IPAddress(address="10.0.0.6", subnet_id=s.id,
                     status=AddressStatus.assigned, hostname="db",
                     mac_address="aa:bb:cc:dd:ee:ff"))
    db.add(CachedDNSRecord(name="db", record_type="A", value="10.0.0.6",
                           zone="x", source="msdns", synced_at=utcnow()))
    db.add(CachedDHCPLease(scope_id="s", ip_address="10.0.0.6", name="db",
                           mac_address="11:22:33:44:55:66", source="msdhcp",
                           synced_at=utcnow()))
    # a pre-existing RESOLVED drift item that should re-open this pass
    # (10.0.0.5 missing_dhcp was resolved before; it drifts again now)
    db.add(DriftItem(ip_address="10.0.0.5", category=DriftCategory.missing_dhcp.value,
                     severity="warning", subnet_id=s.id, details="{}",
                     detected_at=utcnow(), resolved=True, resolved_at=utcnow()))
    db.commit()


def test_detect_drift_characterization(db):
    _fixture(db)
    drain_queue()                     # clear any residue
    detect_drift(db)

    rows = _rows(db)
    # 10.0.0.5: missing_dns (new) + missing_dhcp (reopened -> resolved False)
    assert ("10.0.0.5", DriftCategory.missing_dns.value, False) in rows
    assert ("10.0.0.5", DriftCategory.missing_dhcp.value, False) in rows
    # 10.0.0.6: mac_mismatch; NOT missing_dns/dhcp (has both)
    assert ("10.0.0.6", DriftCategory.mac_mismatch.value, False) in rows
    assert ("10.0.0.6", DriftCategory.missing_dns.value, False) not in rows
    assert ("10.0.0.6", DriftCategory.missing_dhcp.value, False) not in rows

    events = Counter((e.trigger_type, e.resource_key) for e in drain_queue())
    # every detected item emits a "drift" event; reopened missing_dhcp re-emits
    assert events[("drift", "ip:10.0.0.5:missing_dns")] == 1
    assert events[("drift", "ip:10.0.0.5:missing_dhcp")] == 1
    assert events[("drift", "ip:10.0.0.6:mac_mismatch")] == 1
    # none of these categories are conflict categories -> no "collision" events here
    assert all(t != "collision" for (t, _k) in events)
