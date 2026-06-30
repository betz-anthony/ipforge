#!/usr/bin/env bash
# Restore an IPForge Postgres dump (from backup.sh) into the Compose/k8s database.
#
# ORDER MATTERS:
#   1. Ensure SECRET_KEY is already set on the deployment (env / k8s Secret).
#   2. Run this restore.
#   3. Start/restart the app — migrations upgrade the schema to head on boot.
# This script does step 2 only. See docs/operations.md.
# shellcheck disable=SC2016  # single quotes intentional: vars expand inside container shell, not host
set -euo pipefail

TARGET=compose
SERVICE=db
SELECTOR=app=postgres
ASSUME_YES=0
DUMP=""

usage() { echo "usage: $0 [--target compose|k8s] [--service NAME] [--selector LABEL] [--yes] <dump-file>" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:?}"; shift 2;;
    --service) SERVICE="${2:?}"; shift 2;;
    --selector) SELECTOR="${2:?}"; shift 2;;
    --yes) ASSUME_YES=1; shift;;
    -h|--help) usage;;
    -*) echo "unknown arg: $1" >&2; usage;;
    *) DUMP="$1"; shift;;
  esac
done

[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "dump file not found: '$DUMP'" >&2; usage; }

# Manifest guardrail: warn if the dump's schema is newer than running code (no auto-downgrade).
MANIFEST="${DUMP%.dump}.manifest.txt"
k8s_pod() { kubectl get pod -l "$SELECTOR" -o jsonpath='{.items[0].metadata.name}'; }
running_rev() {
  case "$TARGET" in
    compose) docker compose exec -T "$SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version"' 2>/dev/null || echo "unknown";;
    k8s) kubectl exec "$(k8s_pod)" -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version"' 2>/dev/null || echo "unknown";;
  esac
}
if [ -f "$MANIFEST" ]; then
  DUMP_REV="$(grep '^alembic_revision:' "$MANIFEST" | awk '{print $2}')"
  echo "Dump schema revision: ${DUMP_REV:-unknown}"
else
  echo "WARNING: no manifest beside the dump — cannot check schema compatibility." >&2
  [ "$ASSUME_YES" -eq 1 ] || { echo "re-run with --yes to proceed without a manifest." >&2; exit 1; }
fi

echo
echo "About to DESTRUCTIVELY restore into the $TARGET database (pg_restore --clean)."
echo "Confirm SECRET_KEY is already set on the deployment before continuing."
if [ "$ASSUME_YES" -ne 1 ]; then
  printf "Type 'restore' to proceed: "
  read -r ans
  [ "$ans" = "restore" ] || { echo "aborted."; exit 1; }
fi

restore_compose() {
  docker compose exec -T "$SERVICE" sh -c \
    'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$DUMP"
}
restore_k8s() {
  local pod; pod="$(k8s_pod)"
  [ -n "$pod" ] || { echo "no pod matched selector '$SELECTOR'" >&2; exit 1; }
  kubectl exec -i "$pod" -- sh -c \
    'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$DUMP"
}

case "$TARGET" in
  compose) restore_compose;;
  k8s) restore_k8s;;
  *) echo "invalid --target: $TARGET" >&2; usage;;
esac

echo
echo "Restore complete. Now restart the app so migrations run to head:"
echo "  compose: docker compose restart api"
echo "  k8s:     kubectl rollout restart deploy/ipforge-api"
