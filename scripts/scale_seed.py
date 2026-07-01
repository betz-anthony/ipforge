#!/usr/bin/env python3
"""Bulk-seed Postgres with a large IPForge dataset for scale benchmarking.

Runs Alembic migrations to head (so production indexes exist), then bulk-inserts
subnets and addresses. Postgres only — SQLite numbers are not
representative. Idempotent: truncates the seeded tables and reseeds; leaves the
admin user and provider configs intact.

Usage:
    python3 scripts/scale_seed.py --tier 100k
    python3 scripts/scale_seed.py --addresses 10000 --subnets 100 \
        --database-url postgresql://ipam:ipam@localhost:5432/ipam
"""
import argparse
import os
import sys
import time

# Tier -> (addresses, subnets)
TIERS = {"10k": (10000, 100), "50k": (50000, 300), "100k": (100000, 500)}

_STATUSES = ["available", "reserved", "assigned", "deprecated", "discovered"]


def build_subnet_rows(n_subnets: int) -> list[dict]:
    """Unique /24 CIDRs in 10.0.0.0/8, deterministic."""
    rows = []
    for i in range(n_subnets):
        b = (i >> 8) & 0xFF
        c = i & 0xFF
        rows.append({
            "name": f"bench-subnet-{i}",
            "cidr": f"10.{b}.{c}.0/24",
            "ip_version": 4,
            "request_eligible": False,
        })
    return rows


def build_address_rows(n_addr: int, subnet_ids: list[int]) -> list[dict]:
    """Addresses placed inside each subnet's /24 (10.b.c.host), round-robin by
    subnet index so each address lives in its subnet's CIDR. host stays 1..254."""
    s = len(subnet_ids)
    max_host = (n_addr - 1) // s + 1 if n_addr else 0
    if max_host > 254:
        raise ValueError(
            f"{n_addr} addresses across {s} subnets = {max_host} hosts/subnet, "
            f"exceeds a /24 (254). Use more subnets.")
    rows = []
    for i in range(n_addr):
        k = i % s
        host = i // s + 1
        b = (k >> 8) & 0xFF
        c = k & 0xFF
        rows.append({
            "address": f"10.{b}.{c}.{host}",
            "subnet_id": subnet_ids[k],
            "hostname": f"host-{i}.bench.example.com" if i % 2 == 0 else None,
            "status": _STATUSES[i % len(_STATUSES)],
            "mac_address": f"02:00:{(i>>24)&0xFF:02x}:{(i>>16)&0xFF:02x}:{(i>>8)&0xFF:02x}:{i&0xFF:02x}" if i % 3 == 0 else None,
        })
    return rows


def _bootstrap_path():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def seed(database_url: str, n_addr: int, n_subnets: int) -> dict:
    os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("SYNC_MODE", "off")
    _bootstrap_path()

    # Run real migrations (indexes!), not create_all.
    from alembic import command
    from alembic.config import Config
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")

    from sqlalchemy import insert, text
    from app.database import SessionLocal
    from app.models.subnet import Subnet
    from app.models.address import IPAddress

    t0 = time.monotonic()
    db = SessionLocal()
    try:
        # Truncate only the seeded tables; keep users/provider_configs.
        # CASCADE also clears tables referencing subnets/addresses (scan results, drift items, etc.).
        db.execute(text("TRUNCATE ip_addresses, subnet_ranges, subnets RESTART IDENTITY CASCADE"))
        db.commit()

        subnet_rows = build_subnet_rows(n_subnets)
        db.execute(insert(Subnet), subnet_rows)
        db.commit()
        subnet_ids = [r[0] for r in db.execute(text("SELECT id FROM subnets ORDER BY id")).all()]

        addr_rows = build_address_rows(n_addr, subnet_ids)
        CHUNK = 5000
        for i in range(0, len(addr_rows), CHUNK):
            db.execute(insert(IPAddress), addr_rows[i:i + CHUNK])
            db.commit()

        counts = {
            "subnets": db.execute(text("SELECT count(*) FROM subnets")).scalar_one(),
            "addresses": db.execute(text("SELECT count(*) FROM ip_addresses")).scalar_one(),
        }
    finally:
        db.close()
    counts["seconds"] = round(time.monotonic() - t0, 1)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=sorted(TIERS))
    ap.add_argument("--addresses", type=int)
    ap.add_argument("--subnets", type=int)
    ap.add_argument("--database-url",
                    default=os.environ.get("DATABASE_URL",
                                           "postgresql://ipam:ipam@localhost:5432/ipam"))
    args = ap.parse_args()
    if args.tier:
        n_addr, n_subnets = TIERS[args.tier]
    elif args.addresses and args.subnets:
        n_addr, n_subnets = args.addresses, args.subnets
    else:
        print("ERROR: pass --tier or both --addresses and --subnets", file=sys.stderr)
        return 2
    counts = seed(args.database_url, n_addr, n_subnets)
    print(f"Seeded: subnets={counts['subnets']} addresses={counts['addresses']} "
          f"in {counts['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
