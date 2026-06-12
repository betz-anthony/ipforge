#!/usr/bin/env bash
# Tear down the full demo environment (stack + demo backends) and wipe all
# volumes (Postgres data, Kea host DB, BIND zone state), so the next
# scripts/demo-up.sh starts clean.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose \
  -f docker-compose.yml \
  -f examples/demo-backends/docker-compose.demo-backends.yml \
  down -v
echo "Demo environment torn down (volumes wiped)."
