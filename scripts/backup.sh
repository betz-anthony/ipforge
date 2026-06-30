#!/usr/bin/env bash
# Back up the IPForge Postgres database (custom-format dump) for Docker Compose
# or Kubernetes. Runs pg_dump INSIDE the Postgres container, so it inherits the
# container's POSTGRES_USER / POSTGRES_DB and needs no credentials on the host.
#
# NOTE: this backs up the DATABASE ONLY. The Fernet SECRET_KEY is NOT in the dump.
# Encrypted columns (provider secrets, ldap_bind_password) are UNRECOVERABLE without
# the key — back up SECRET_KEY out-of-band separately. See docs/operations.md.
# shellcheck disable=SC2016  # single quotes intentional: vars expand inside container shell, not host
set -euo pipefail

TARGET=compose
OUT=./backups
SERVICE=db
SELECTOR=app=postgres
POD=""  # resolved once for --target k8s; see below

usage() { echo "usage: $0 [--target compose|k8s] [--out DIR] [--service NAME] [--selector LABEL]" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:?}"; shift 2;;
    --out) OUT="${2:?}"; shift 2;;
    --service) SERVICE="${2:?}"; shift 2;;
    --selector) SELECTOR="${2:?}"; shift 2;;
    -h|--help) usage;;
    *) echo "unknown arg: $1" >&2; usage;;
  esac
done

TS="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
DUMP="$OUT/ipforge-backup-$TS.dump"
MANIFEST="$OUT/ipforge-backup-$TS.manifest.txt"
TMP="$DUMP.partial"
trap 'rm -f "$TMP"' EXIT  # remove partial dump on any exit (no-op after successful mv)

dump_compose() {
  docker compose exec -T "$SERVICE" sh -c \
    'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$TMP"
}

k8s_pod() { kubectl get pod -l "$SELECTOR" -o jsonpath='{.items[0].metadata.name}'; }

dump_k8s() {
  kubectl exec "$POD" -- sh -c \
    'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$TMP"
}

pg_version() {
  case "$TARGET" in
    compose) docker compose exec -T "$SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version()"' 2>/dev/null || echo "unknown";;
    k8s) kubectl exec "$POD" -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version()"' 2>/dev/null || echo "unknown";;
  esac
}

schema_rev() {
  case "$TARGET" in
    compose) docker compose exec -T "$SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version"' 2>/dev/null || echo "unknown";;
    k8s) kubectl exec "$POD" -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version"' 2>/dev/null || echo "unknown";;
  esac
}

# Resolve k8s pod once so all three functions share the same target
if [ "$TARGET" = k8s ]; then
  POD="$(k8s_pod)"
  [ -n "$POD" ] || { echo "no pod matched selector '$SELECTOR'" >&2; exit 1; }
fi

case "$TARGET" in
  compose) dump_compose;;
  k8s) dump_k8s;;
  *) echo "invalid --target: $TARGET" >&2; usage;;
esac

mv "$TMP" "$DUMP"
{
  echo "timestamp_utc: $TS"
  echo "target: $TARGET"
  echo "alembic_revision: $(schema_rev | tr -d '[:space:]')"
  echo "postgres_version: $(pg_version | tr -d '\n')"
  echo "dump_file: $(basename "$DUMP")"
} > "$MANIFEST"

echo "Backup written: $DUMP"
echo "Manifest:       $MANIFEST"
echo
echo "REMINDER: this dump does NOT include SECRET_KEY. Back the key up separately,"
echo "or encrypted provider/LDAP credentials cannot be recovered. See docs/operations.md."
