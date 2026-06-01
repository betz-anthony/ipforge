# Screenshots

Documentation screenshots of the IPForge UI, captured against a seeded demo
dataset. Used in the project README, user guide, and launch material.

| File | Page |
|---|---|
| `01-dashboard.png` | Dashboard — stats, subnet utilization, capacity forecast |
| `02-subnets.png` | Subnets list (hierarchy + drift badges) |
| `03-subnet-map.png` | Subnet detail — address-space heatmap + reserved ranges + forecast |
| `04-addresses.png` | IP addresses table |
| `05-drift.png` | Drift reconciliation (all categories incl. v2) |
| `06-settings-providers.png` | Settings — DNS/DHCP providers, custom fields, drift policies |
| `07-security.png` | Security events (rogue / mac-move / quarantine) |
| `08-gitops.png` | GitOps declarative YAML apply |

## Regenerating

Everything runs locally against SQLite — no Postgres, no Docker.

```bash
# 1. Seed a demo DB
DATABASE_URL="sqlite:///$PWD/demo.db" python3 scripts/seed_demo.py

# 2. Serve the API against it (Alembic skipped; background loops frozen)
DATABASE_URL="sqlite:///$PWD/demo.db" python3 scripts/serve_demo.py   # :8000

# 3. Run the frontend dev server (separate shell)
cd frontend && npm run dev                                            # :5173

# 4. Capture (separate shell) — one-time Playwright install first
cd frontend
npm i -D playwright && npx playwright install chromium
node capture_screenshots.mjs
```

The seed is deterministic (`random.seed(42)`), so re-runs are stable.
`demo.db` is gitignored.
