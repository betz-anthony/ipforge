#!/usr/bin/env python3
"""Serve the IPForge API against the seeded SQLite demo DB (for screenshots).

Patches out the Alembic migration step on startup (the schema is created by
scripts/seed_demo.py via create_all; some migrations are Postgres-only) and
launches uvicorn.

Usage:
    DATABASE_URL=sqlite:///./demo.db python3 scripts/serve_demo.py
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./demo.db")
os.environ.setdefault("SYNC_MODE", "off")

import bcrypt as _bcrypt_mod  # noqa: E402
_orig_hashpw = _bcrypt_mod.hashpw
_bcrypt_mod.hashpw = lambda pw, salt: _orig_hashpw(pw[:72], salt)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import app.main as main  # noqa: E402
import app.scan as _scan  # noqa: E402
import app.discovery.runner as _disc  # noqa: E402

# Schema already built by seed_demo.py; skip Alembic (Postgres-only DDL).
main._run_migrations = lambda: None

# Freeze the seeded dataset: stop the scan scheduler + discovery poller loops
# (started unconditionally by the lifespan) from mutating demo data — they
# would otherwise generate live scan results and rogue-device security events.
_scan.scan_scheduler_loop = lambda *a, **k: None
_disc.discovery_poller_loop = lambda *a, **k: None
main.scan_scheduler_loop = _scan.scan_scheduler_loop
main.discovery_poller_loop = _disc.discovery_poller_loop

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=8000, log_level="warning")
