#!/usr/bin/env bash
# Orchestrate the IPForge scale benchmark against a DEDICATED ephemeral Postgres 16
# container (published on localhost:5432). Per tier: seed, serve (background loops
# disabled), mint an admin token, run bench.py, stop the API. See docs/scaling.md.
set -euo pipefail

DB_URL="postgresql://ipam:ipam@localhost:5432/ipam"
BASE_URL="http://localhost:8001"
CONTAINER="ipfg-bench-db"
ITER=40
TIERS=()

usage() { echo "usage: $0 (--tier 10k|50k|100k | --all) [--iterations N]" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIERS+=("${2:?}"); shift 2;;
    --all) TIERS=(10k 50k 100k); shift;;
    --iterations) ITER="${2:?}"; shift 2;;
    -h|--help) usage;;
    *) echo "unknown arg: $1" >&2; usage;;
  esac
done
[ "${#TIERS[@]}" -gt 0 ] || usage

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

API_PID=""
cleanup() { kill "${API_PID:-}" 2>/dev/null || true; docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  -e POSTGRES_USER=ipam -e POSTGRES_PASSWORD=ipam -e POSTGRES_DB=ipam \
  -p 5432:5432 postgres:16-alpine >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U ipam -d ipam >/dev/null 2>&1; then break; fi
  sleep 2
done

mint_token() {
  DATABASE_URL="$DB_URL" SYNC_MODE=off python3 - <<'PY'
import os, sys
sys.path.insert(0, "backend")
from app.database import SessionLocal
from app.models.user import User
from app.models.api_token import ApiToken
from app.core.security import generate_api_token, hash_api_token, API_TOKEN_DISPLAY_PREFIX_LEN
db = SessionLocal()
admin = db.query(User).order_by(User.id).first()
value = generate_api_token()
db.add(ApiToken(user_id=admin.id, name="bench", token_hash=hash_api_token(value),
                token_prefix=value[:API_TOKEN_DISPLAY_PREFIX_LEN], read_only=False))
db.commit(); print(value)
PY
}

for tier in "${TIERS[@]}"; do
  echo "=== tier $tier ==="
  python3 scripts/scale_seed.py --tier "$tier" --database-url "$DB_URL"

  python3 scripts/serve_bench.py &
  API_PID=$!
  for _ in $(seq 1 40); do
    if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then break; fi
    sleep 1
  done

  TOKEN="$(mint_token)"
  python3 scripts/bench.py --base-url "$BASE_URL" --token "$TOKEN" --tier "$tier" --iterations "$ITER"

  kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; API_PID=""
done

echo "Done. Results: bench-results-*.json"
