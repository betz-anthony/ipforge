#!/usr/bin/env python3
"""Serve the IPForge API against the bench Postgres DB with background loops disabled.

Runs real Alembic migrations + admin seed on startup (idempotent after scale_seed.py
has already run them), so the admin user exists for token minting. Disables the scan
scheduler and discovery poller loops so the seeded dataset stays quiescent during
benchmarking and TRUNCATE in subsequent tiers cannot deadlock.

Usage (called by bench-run.sh from the repo root):
    python3 scripts/serve_bench.py
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://ipam:ipam@localhost:5432/ipam")
os.environ.setdefault("SYNC_MODE", "off")

import bcrypt as _bcrypt_mod  # noqa: E402
_orig_hashpw = _bcrypt_mod.hashpw
_bcrypt_mod.hashpw = lambda pw, salt: _orig_hashpw(pw[:72], salt)

_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
os.chdir(_BACKEND_DIR)          # Alembic resolves script_location=alembic relative to CWD
sys.path.insert(0, _BACKEND_DIR)

import app.main as main  # noqa: E402
import app.scan as _scan  # noqa: E402
import app.discovery.runner as _disc  # noqa: E402

# Keep _run_migrations intact — we want real Postgres migrations + admin seed
# so the admin user exists for bench token minting.

# Freeze the seeded dataset: disable scan scheduler + discovery poller loops
# so they cannot mutate data or deadlock against scale_seed.py's TRUNCATE.
_scan.scan_scheduler_loop = lambda *a, **k: None
_disc.discovery_poller_loop = lambda *a, **k: None
main.scan_scheduler_loop = _scan.scan_scheduler_loop
main.discovery_poller_loop = _disc.discovery_poller_loop

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=8001, log_level="warning")
