#!/usr/bin/env python3
"""Seed a realistic demo dataset into a local SQLite DB for screenshots / demos.

Usage:
    DATABASE_URL=sqlite:///./demo.db python3 scripts/seed_demo.py

Builds the schema with Base.metadata.create_all (NOT Alembic — some migrations
use Postgres-only DDL) and fills every domain with believable data so the UI
screens look populated. Safe to re-run: drops and recreates all tables.

Pair with scripts/serve_demo.py to launch the API against the seeded DB.
"""
import os
import sys
import json
import random
from datetime import date, timedelta

# Default to a file DB next to the repo root if not provided.
os.environ.setdefault("DATABASE_URL", "sqlite:///./demo.db")
os.environ.setdefault("SYNC_MODE", "off")  # don't start background provider sync

# Passlib/bcrypt 4.x probe fix (mirrors tests/conftest.py).
import bcrypt as _bcrypt_mod  # noqa: E402
_orig_hashpw = _bcrypt_mod.hashpw
_bcrypt_mod.hashpw = lambda pw, salt: _orig_hashpw(pw[:72], salt)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import Base, engine, SessionLocal  # noqa: E402
import app.main  # noqa: E402,F401  (imports every router/model -> full metadata)

from app.core.time import utcnow  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vlan import Vlan  # noqa: E402
from app.models.subnet import Subnet  # noqa: E402
from app.models.subnet_range import SubnetRange  # noqa: E402
from app.models.address import IPAddress, AddressStatus  # noqa: E402
from app.models.custom_field import (  # noqa: E402
    CustomFieldDef, CustomFieldValue, Tag, TagAssignment,
)
from app.models.scan import (  # noqa: E402
    ScanResult, DriftItem, DriftPolicy, DriftCategory, DRIFT_SEVERITY,
    AlertEvent, SubnetUtilizationDay,
)
from app.models.security import SecurityEvent, MacLastSeen  # noqa: E402
from app.models.gitops import GitopsManaged  # noqa: E402
from app.models.provider_config import ProviderConfig  # noqa: E402
from app.models.cache import (  # noqa: E402
    CachedDNSZone, CachedDNSRecord, CachedDHCPScope, CachedDHCPLease, SyncStatus,
)
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.network_device import NetworkDevice, DiscoveredEndpoint  # noqa: E402

random.seed(42)
NOW = utcnow()
TODAY = date.today()


def reset_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed(db):
    # ── admin user ────────────────────────────────────────────────────────
    db.add(User(username="admin", hashed_password=hash_password("admin"),
                role="admin", enabled=True))

    # ── VLANs ─────────────────────────────────────────────────────────────
    vlans = [
        Vlan(vlan_id=10,  name="Management", description="Switch/router mgmt"),
        Vlan(vlan_id=20,  name="Servers",    description="Production servers"),
        Vlan(vlan_id=30,  name="Workstations", description="Office desktops"),
        Vlan(vlan_id=40,  name="VoIP",       description="IP phones"),
        Vlan(vlan_id=50,  name="Guest",      description="Guest wireless"),
        Vlan(vlan_id=100, name="DMZ",        description="Public-facing"),
    ]
    db.add_all(vlans)
    db.flush()

    # ── subnets (with a parent for hierarchy) ─────────────────────────────
    parent = Subnet(name="Corporate", cidr="10.0.0.0/8", ip_version=4,
                    description="Top-level corporate space")
    db.add(parent)
    db.flush()

    subnets = {
        "mgmt": Subnet(name="Management", cidr="10.10.0.0/24", ip_version=4,
                       vlan_id=10, parent_id=parent.id, description="Network mgmt",
                       dns_provider_name="corp-dns", dhcp_provider_name="corp-dhcp",
                       scan_interval_minutes=None),
        "srv": Subnet(name="Servers", cidr="10.20.0.0/24", ip_version=4,
                      vlan_id=20, parent_id=parent.id, description="Production servers",
                      dns_provider_name="corp-dns", dhcp_provider_name="corp-dhcp",
                      scan_interval_minutes=None),
        "wks": Subnet(name="Workstations", cidr="10.30.0.0/24", ip_version=4,
                      vlan_id=30, parent_id=parent.id, description="Office desktops",
                      dns_provider_name="corp-dns", dhcp_provider_name="corp-dhcp",
                      scan_interval_minutes=None),
        "voip": Subnet(name="VoIP", cidr="10.40.0.0/24", ip_version=4, vlan_id=40,
                       parent_id=parent.id, description="IP telephony",
                       scan_interval_minutes=None),
        "guest": Subnet(name="Guest", cidr="192.168.50.0/24", ip_version=4, vlan_id=50,
                        description="Guest WiFi", request_eligible=True,
                        scan_interval_minutes=None),
        "dmz": Subnet(name="DMZ", cidr="172.16.0.0/24", ip_version=4, vlan_id=100,
                      description="Public-facing services", dns_provider_name="cloudflare",
                      scan_interval_minutes=None),
    }
    db.add_all(subnets.values())
    db.flush()

    srv = subnets["srv"]

    # ── reserved ranges on the Servers subnet (drives the map legend) ─────
    db.add_all([
        SubnetRange(subnet_id=srv.id, start_ip="10.20.0.1", end_ip="10.20.0.1",
                    kind="gateway", label="Default gateway"),
        SubnetRange(subnet_id=srv.id, start_ip="10.20.0.2", end_ip="10.20.0.15",
                    kind="reserved", label="Infrastructure"),
        SubnetRange(subnet_id=srv.id, start_ip="10.20.0.100", end_ip="10.20.0.200",
                    kind="dhcp_pool", label="DHCP pool"),
    ])

    # ── custom field defs ─────────────────────────────────────────────────
    cf_owner = CustomFieldDef(entity_type="address", name="owner", label="Owner",
                              field_type="text")
    cf_env = CustomFieldDef(entity_type="address", name="environment",
                            label="Environment", field_type="select",
                            options=json.dumps(["prod", "staging", "dev"]))
    cf_site = CustomFieldDef(entity_type="subnet", name="site", label="Site",
                             field_type="select",
                             options=json.dumps(["HQ", "DR", "Branch"]))
    db.add_all([cf_owner, cf_env, cf_site])
    db.flush()

    # ── tags ──────────────────────────────────────────────────────────────
    tags = {n: Tag(name=n) for n in ("production", "critical", "legacy", "iot", "monitored")}
    db.add_all(tags.values())
    db.flush()

    # ── Servers subnet: dense, realistic address population ───────────────
    server_hosts = {
        2: ("dc01", "assigned", "prod", "Domain controller", ["production", "critical"]),
        3: ("dc02", "assigned", "prod", "Domain controller", ["production", "critical"]),
        5: ("dns01", "assigned", "prod", "Primary DNS", ["production", "critical", "monitored"]),
        6: ("dhcp01", "assigned", "prod", "DHCP server", ["production", "monitored"]),
        10: ("vcenter", "assigned", "prod", "VMware vCenter", ["production", "critical"]),
        20: ("app01", "assigned", "prod", "App server", ["production"]),
        21: ("app02", "assigned", "prod", "App server", ["production"]),
        22: ("app03", "assigned", "staging", "Staging app", []),
        30: ("db01", "assigned", "prod", "PostgreSQL primary", ["production", "critical"]),
        31: ("db02", "assigned", "prod", "PostgreSQL replica", ["production"]),
        40: ("web01", "assigned", "prod", "Web frontend", ["production"]),
        41: ("web02", "assigned", "prod", "Web frontend", ["production"]),
        50: ("backup01", "assigned", "prod", "Backup target", ["production"]),
        60: ("legacy-erp", "deprecated", "prod", "Old ERP (decommissioning)", ["legacy"]),
        70: ("monitoring", "assigned", "prod", "Prometheus/Grafana", ["production", "monitored"]),
        80: ("ci-runner", "assigned", "dev", "CI build runner", []),
        90: ("test-sandbox", "reserved", "dev", "Reserved for QA", []),
        205: ("scanner", "discovered", None, "Discovered host", []),
        206: ("unknown-206", "discovered", None, "Discovered host", []),
    }
    macs = lambda: ":".join(f"{random.randint(0,255):02x}" for _ in range(6))
    addr_objs = {}
    for host_n in range(2, 251):
        ip = f"10.20.0.{host_n}"
        if host_n in server_hosts:
            name, status, env, desc, taglist = server_hosts[host_n]
            a = IPAddress(address=ip, subnet_id=srv.id, hostname=name,
                          status=AddressStatus(status), mac_address=macs(),
                          description=desc, last_seen=NOW,
                          dns_provider="corp-dns", dns_zone="corp.example.com",
                          dhcp_provider="corp-dhcp", dhcp_scope_id="10.20.0.0")
            db.add(a); db.flush()
            addr_objs[host_n] = a
            if env:
                db.add(CustomFieldValue(field_id=cf_env.id, entity_id=a.id, value=env))
            db.add(CustomFieldValue(field_id=cf_owner.id, entity_id=a.id,
                                    value=random.choice(["netops", "platform", "dba", "appteam"])))
            for t in taglist:
                db.add(TagAssignment(tag_id=tags[t].id, entity_type="address", entity_id=a.id))
        elif 100 <= host_n <= 160:
            # DHCP pool — assigned leases
            db.add(IPAddress(address=ip, subnet_id=srv.id,
                             hostname=f"dyn-{host_n}", status=AddressStatus.assigned,
                             mac_address=macs(), last_seen=NOW))
        # remaining IPs left unmanaged (available) -> heatmap shows free space

    # site custom field on subnets
    db.add(CustomFieldValue(field_id=cf_site.id, entity_id=srv.id, value="HQ"))
    db.add(CustomFieldValue(field_id=cf_site.id, entity_id=subnets["dmz"].id, value="DR"))

    # ── scan results for the Servers subnet (heatmap reachability) ────────
    for host_n in range(2, 251):
        ip = f"10.20.0.{host_n}"
        managed = host_n in server_hosts or 100 <= host_n <= 160
        reachable = managed and random.random() > 0.12
        db.add(ScanResult(subnet_id=srv.id, ip_address=ip, reachable=reachable,
                          latency_ms=round(random.uniform(0.3, 8.0), 1) if reachable else None,
                          scanned_at=NOW))

    # ── capacity history -> forecast widget (growth trend per subnet) ─────
    for sub, base, growth, cap in [
        (srv, 70, 1.6, 254), (subnets["wks"], 120, 0.9, 254),
        (subnets["voip"], 40, 0.3, 254), (subnets["dmz"], 30, 0.5, 254),
    ]:
        for d in range(30, -1, -1):
            used = int(base + (30 - d) * growth + random.uniform(-2, 2))
            db.add(SubnetUtilizationDay(subnet_id=sub.id, date=TODAY - timedelta(days=d),
                                        used_count=max(0, min(used, cap)), total_count=cap))

    # ── DNS / DHCP cache (Dashboard counts + DNS/DHCP pages) ──────────────
    db.add_all([
        CachedDNSZone(zone="corp.example.com", source="corp-dns", synced_at=NOW),
        CachedDNSZone(zone="20.10.in-addr.arpa", source="corp-dns", synced_at=NOW),
        CachedDNSZone(zone="example.com", source="cloudflare", synced_at=NOW),
    ])
    for host_n, a in addr_objs.items():
        if a.status == AddressStatus.assigned:
            db.add(CachedDNSRecord(name=a.hostname, record_type="A", value=a.address,
                                   zone="corp.example.com", ttl=3600, source="corp-dns",
                                   synced_at=NOW))
            db.add(CachedDNSRecord(name=f"{host_n}.0.20.10.in-addr.arpa", record_type="PTR",
                                   value=f"{a.hostname}.corp.example.com.",
                                   zone="20.10.in-addr.arpa", ttl=3600, source="corp-dns",
                                   synced_at=NOW))
    # a couple of orphan / mismatched records to make Drift realistic
    db.add(CachedDNSRecord(name="ghost", record_type="A", value="10.20.0.240",
                           zone="corp.example.com", ttl=3600, source="corp-dns", synced_at=NOW))
    db.add(CachedDNSRecord(name="6.0.20.10.in-addr.arpa", record_type="PTR",
                           value="wrong-name.corp.example.com.", zone="20.10.in-addr.arpa",
                           ttl=3600, source="corp-dns", synced_at=NOW))

    db.add(CachedDHCPScope(scope_id="10.20.0.0", name="Servers", subnet_mask="255.255.255.0",
                           start_range="10.20.0.100", end_range="10.20.0.200",
                           source="corp-dhcp", synced_at=NOW))
    db.add(CachedDHCPScope(scope_id="10.30.0.0", name="Workstations", subnet_mask="255.255.255.0",
                           start_range="10.30.0.50", end_range="10.30.0.250",
                           source="corp-dhcp", synced_at=NOW))
    for host_n in range(100, 145):
        db.add(CachedDHCPLease(scope_id="10.20.0.0", ip_address=f"10.20.0.{host_n}",
                               mac_address=macs(), name=f"dyn-{host_n}",
                               source="corp-dhcp", synced_at=NOW))
    db.add(CachedDHCPLease(scope_id="10.20.0.0", ip_address="10.20.0.241",
                           mac_address=macs(), name="orphan-lease",
                           source="corp-dhcp", synced_at=NOW))

    db.add_all([
        SyncStatus(key="dns:corp-dns", synced_at=NOW, status="ok"),
        SyncStatus(key="dns:cloudflare", synced_at=NOW, status="ok"),
        SyncStatus(key="dhcp:corp-dhcp", synced_at=NOW, status="ok"),
    ])

    # ── drift items across categories ─────────────────────────────────────
    def drift(ip, cat, details, sid=srv.id, needs_review=False):
        db.add(DriftItem(ip_address=ip, category=cat.value, severity=DRIFT_SEVERITY[cat],
                         subnet_id=sid, details=json.dumps(details), detected_at=NOW,
                         resolved=False, needs_review=needs_review))
    drift("10.20.0.240", DriftCategory.orphan_dns, {"name": "ghost", "zone": "corp.example.com", "source": "corp-dns"})
    drift("10.20.0.241", DriftCategory.orphan_dhcp, {"name": "orphan-lease", "scope_id": "10.20.0.0", "source": "corp-dhcp"})
    drift("10.20.0.22", DriftCategory.missing_dns, {"hostname": "app03", "status": "assigned"}, needs_review=True)
    drift("10.20.0.80", DriftCategory.missing_dhcp, {"hostname": "ci-runner", "status": "assigned"})
    drift("10.20.0.6", DriftCategory.ptr_mismatch, {"a_name": "dhcp01", "ptr_value": "wrong-name.corp.example.com."})
    drift("10.20.0.60", DriftCategory.unreachable_assigned, {"last_scanned": NOW.isoformat()})
    drift("10.20.0.205", DriftCategory.active_but_available, {"ipam_status": "available", "latency_ms": 1.2})

    db.add_all([
        DriftPolicy(category=DriftCategory.orphan_dhcp.value, subnet_id=None,
                    mode="auto", dry_run=True, params={}, enabled=True),
        DriftPolicy(category=DriftCategory.missing_dns.value, subnet_id=None,
                    mode="review", dry_run=True, params={}, enabled=True),
        DriftPolicy(category=DriftCategory.orphan_dns.value, subnet_id=srv.id,
                    mode="auto", dry_run=False, params={"action": "delete_provider"}, enabled=True),
    ])

    # ── scan alerts (Dashboard) ───────────────────────────────────────────
    db.add_all([
        AlertEvent(event_type="went_down", ip_address="10.20.0.60", subnet_id=srv.id,
                   detected_at=NOW, details=json.dumps({"host": "legacy-erp"}), acknowledged=False),
        AlertEvent(event_type="new_host", ip_address="10.20.0.205", subnet_id=srv.id,
                   detected_at=NOW, details=json.dumps({"host": "scanner"}), acknowledged=False),
    ])

    # ── security events ───────────────────────────────────────────────────
    db.add_all([
        SecurityEvent(event_type="rogue_device", severity="high", mac=macs(), ip="10.20.0.206",
                      details=json.dumps({"reason": "unknown MAC on server VLAN"}),
                      detected_at=NOW, acknowledged=False, quarantined=True),
        SecurityEvent(event_type="mac_move", severity="medium", mac=macs(), ip="10.30.0.55",
                      details=json.dumps({"from_port": "Gi1/0/4", "to_port": "Gi1/0/9"}),
                      detected_at=NOW - timedelta(hours=2), acknowledged=False),
        SecurityEvent(event_type="ip_conflict", severity="high", mac=macs(), ip="10.20.0.40",
                      details=json.dumps({"macs": 2}), detected_at=NOW - timedelta(hours=5),
                      acknowledged=True, acknowledged_at=NOW),
        SecurityEvent(event_type="new_mac", severity="low", mac=macs(), ip="10.30.0.88",
                      details=json.dumps({}), detected_at=NOW - timedelta(days=1), acknowledged=True),
    ])
    db.add(MacLastSeen(mac=macs(), ip="10.20.0.2", port_name="Gi1/0/1", last_seen=NOW))

    # ── gitops-managed markers ────────────────────────────────────────────
    db.add_all([
        GitopsManaged(source="prod-cluster", resource_type="subnet", resource_id=srv.id),
        GitopsManaged(source="prod-cluster", resource_type="vlan", resource_id=vlans[1].id),
    ])
    if 30 in addr_objs:
        db.add(GitopsManaged(source="prod-cluster", resource_type="address", resource_id=addr_objs[30].id))

    # ── provider configs (Settings → Providers) ──────────────────────────
    db.add_all([
        ProviderConfig(category="dns", provider_type="msdns", name="corp-dns",
                       config=json.dumps({"winrm_host": "dc01.corp.example.com",
                                          "dns_server": "dc01.corp.example.com",
                                          "username": "svc-ipam"}),
                       enabled=True, sort_order=0),
        ProviderConfig(category="dns", provider_type="cloudflare", name="cloudflare",
                       config=json.dumps({"zone": "example.com"}), enabled=True, sort_order=1),
        ProviderConfig(category="dhcp", provider_type="msdhcp", name="corp-dhcp",
                       config=json.dumps({"winrm_host": "dc01.corp.example.com",
                                          "dhcp_server": "dc01.corp.example.com",
                                          "username": "svc-ipam"}),
                       enabled=True, sort_order=0),
        ProviderConfig(category="dhcp", provider_type="keadhcp", name="kea-lab",
                       config=json.dumps({"ctrl_agent_url": "http://10.20.0.6:8000"}),
                       enabled=False, sort_order=1),
    ])

    # ── audit log (so the Audit page is populated for demos/screenshots) ────────
    db.flush()  # give earlier rows ids before we reference/query them
    audit_actors = ["admin", "operator", "jdoe", "svc-terraform"]
    audit_events = [
        ("create", "subnet",           "10.30.0.0/24",            "Created subnet 10.30.0.0/24 (lab-dmz)"),
        ("create", "address",          "10.20.0.10",              "Allocated 10.20.0.10 (vcenter)"),
        ("update", "address",          "10.20.0.42",              "Changed status assigned -> reserved"),
        ("create", "dns_record",       "web01.corp.example.com",  "Added A web01 -> 10.20.0.55"),
        ("delete", "dhcp_reservation", "10.21.0.80",              "Removed reservation 10.21.0.80"),
        ("update", "subnet",           "10.21.0.0/24",            "Set scan interval to 15m"),
        ("create", "vlan",             "30",                      "Created VLAN 30 (dmz)"),
        ("create", "address",          "10.20.0.61",              "Allocated 10.20.0.61 (build-runner)"),
        ("delete", "address",          "10.22.0.13",              "Reclaimed stale address 10.22.0.13"),
        ("update", "dns_record",       "db01.corp.example.com",   "Updated A db01 -> 10.20.0.31"),
        ("create", "dhcp_reservation", "10.21.0.50",              "Reserved 10.21.0.50 (printer-2f)"),
        ("update", "address",          "10.20.0.10",              "Updated MAC and hostname"),
    ]
    for action, rtype, rid, summary in audit_events:
        ts = NOW - timedelta(days=random.randint(0, 12), hours=random.randint(0, 23),
                             minutes=random.randint(0, 59))
        before = after = None
        if action == "update":
            before, after = json.dumps({"status": "assigned"}), json.dumps({"status": "reserved"})
        elif action == "create":
            after = json.dumps({"id": rid})
        else:  # delete
            before = json.dumps({"id": rid})
        db.add(AuditLog(timestamp=ts, username=random.choice(audit_actors), action=action,
                        resource_type=rtype, resource_id=rid, summary=summary,
                        before_state=before, after_state=after))

    # ── SNMP discovery: switches + endpoints (Discovery page) ───────────────────
    sw_core = NetworkDevice(name="core-sw01", host="10.20.0.2", snmp_version="2c",
                            community="public", enabled=True, poll_interval_minutes=30)
    sw_acc = NetworkDevice(name="access-sw02", host="10.20.0.3", snmp_version="2c",
                           community="public", enabled=True, poll_interval_minutes=60)
    db.add_all([sw_core, sw_acc])
    db.flush()  # device ids

    endpoints_src = db.query(IPAddress).filter(IPAddress.mac_address.isnot(None)).limit(16).all()
    for n, addr in enumerate(endpoints_src):
        dev = sw_core if n % 2 == 0 else sw_acc
        db.add(DiscoveredEndpoint(
            device_id=dev.id, ip=addr.address, mac=addr.mac_address,
            ifindex=10001 + n, port_name=f"Gi1/0/{n + 1}",
            vlan=random.choice([10, 20, 30, 99]),
            last_seen=NOW - timedelta(minutes=random.randint(1, 240)),
            source=dev.name,
        ))

    db.commit()


if __name__ == "__main__":
    print(f"Seeding {os.environ['DATABASE_URL']} ...")
    reset_schema()
    s = SessionLocal()
    try:
        seed(s)
    finally:
        s.close()
    print("Demo data seeded.")
