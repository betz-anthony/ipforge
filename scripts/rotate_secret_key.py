#!/usr/bin/env python3
"""Rotate the Fernet SECRET_KEY: re-encrypt all stored secrets old key → new key.

Re-encrypts every encrypted field (provider_configs secret fields per
SECRET_FIELDS, plus the ldap_bind_password AppSetting) so the database matches a
new SECRET_KEY. Run this BEFORE swapping the deployment's SECRET_KEY.

Usage:
    # OLD key = the deployment's current SECRET_KEY; NEW key = the replacement.
    OLD_SECRET_KEY=<current> python3 scripts/rotate_secret_key.py --new-key <new> [--dry-run]

    # OLD_SECRET_KEY defaults to the SECRET_KEY env / config value if unset.
    DATABASE_URL=postgresql://... OLD_SECRET_KEY=<old> \
      python3 scripts/rotate_secret_key.py --new-key <new>

Then set SECRET_KEY=<new> on the deployment and restart.

Idempotent-ish: values that don't decrypt with the OLD key are left untouched
and reported (so a half-rotated DB won't be corrupted).
"""
import argparse
import json
import os
import sys

from cryptography.fernet import Fernet, InvalidToken

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

_FERNET_PREFIX = "gAAAAA"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-key", required=True, help="new Fernet SECRET_KEY")
    ap.add_argument("--old-key", default=os.environ.get("OLD_SECRET_KEY"),
                    help="current SECRET_KEY (defaults to $OLD_SECRET_KEY, "
                         "then the app's configured SECRET_KEY)")
    ap.add_argument("--dry-run", action="store_true", help="report only; no writes")
    args = ap.parse_args()

    from app.config import settings
    old_key = args.old_key or settings.secret_key
    if not old_key:
        print("ERROR: no OLD key (set --old-key / OLD_SECRET_KEY / SECRET_KEY).", file=sys.stderr)
        return 2
    try:
        f_old = Fernet(old_key.encode())
        f_new = Fernet(args.new_key.encode())
    except Exception as exc:
        print(f"ERROR: invalid Fernet key: {exc}", file=sys.stderr)
        return 2
    if old_key == args.new_key:
        print("ERROR: new key equals old key.", file=sys.stderr)
        return 2

    from app.database import SessionLocal
    from app.models.provider_config import ProviderConfig, SECRET_FIELDS
    from app.models.setting import AppSetting

    def rekey(val: str) -> tuple[str, str]:
        """Return (new_value, status). status: rekeyed | plaintext | failed | empty."""
        if not val:
            return val, "empty"
        if not val.startswith(_FERNET_PREFIX):
            # plaintext (pre-encryption row): encrypt under the new key
            return f_new.encrypt(val.encode()).decode(), "plaintext"
        try:
            plain = f_old.decrypt(val.encode()).decode()
        except InvalidToken:
            return val, "failed"
        return f_new.encrypt(plain.encode()).decode(), "rekeyed"

    db = SessionLocal()
    counts = {"rekeyed": 0, "plaintext": 0, "failed": 0, "empty": 0}
    failures: list[str] = []
    try:
        for row in db.query(ProviderConfig).all():
            cfg = json.loads(row.config or "{}")
            row_changed = False
            for field in SECRET_FIELDS.get(row.provider_type, []):
                if field not in cfg:
                    continue
                new_val, status = rekey(cfg[field])
                counts[status] += 1
                if status == "failed":
                    failures.append(f"provider {row.name!r} field {field!r}")
                elif new_val != cfg[field]:
                    cfg[field] = new_val
                    row_changed = True
            if row_changed and not args.dry_run:
                row.config = json.dumps(cfg)

        for row in db.query(AppSetting).filter(AppSetting.key == "ldap_bind_password").all():
            new_val, status = rekey(row.value)
            counts[status] += 1
            if status == "failed":
                failures.append("ldap_bind_password")
            elif new_val != row.value and not args.dry_run:
                row.value = new_val

        if not args.dry_run:
            db.commit()
    finally:
        db.close()

    print(f"{'DRY-RUN ' if args.dry_run else ''}re-key summary: "
          f"rekeyed={counts['rekeyed']} plaintext={counts['plaintext']} "
          f"failed={counts['failed']} empty={counts['empty']}")
    if failures:
        print("WARNING: could not decrypt with the OLD key (left untouched):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("Check the OLD key is correct, or re-enter those secrets in the UI.", file=sys.stderr)
        return 1
    if not args.dry_run:
        print("Done. Now set SECRET_KEY to the new key on the deployment and restart.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
