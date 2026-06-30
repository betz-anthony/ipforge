# IPForge Operations & Disaster Recovery

## What to back up
Three things, not one:
1. **Postgres database** — all IPAM data. Use `scripts/backup.sh`.
2. **`SECRET_KEY`** (Fernet) — encrypts provider credentials and the LDAP bind
   password at rest. **It is NOT in the database dump.** Lose it and those
   encrypted columns are unrecoverable. Store it in a password manager / secrets
   vault, separate from the DB backup.
3. **Deployment config** — `.env` (Compose) or your Secret/ConfigMap manifests (k8s),
   minus any plaintext secrets you keep in a vault.

## Backup
Docker Compose:
    scripts/backup.sh --target compose --out ./backups
Kubernetes:
    scripts/backup.sh --target k8s --out ./backups
Raw fallback (Compose):
    docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup.dump

Each run writes `ipforge-backup-<ts>.dump` + a `.manifest.txt` (schema revision,
pg version). Keep the manifest with the dump — restore uses it for a safety check.

## Restore
Order matters:
1. Ensure `SECRET_KEY` is set on the deployment (same value used when the data was
   encrypted). Set it BEFORE restoring.
2. Restore the database:
       scripts/restore.sh --target compose ./backups/ipforge-backup-<ts>.dump
   > The restore prompts for an interactive confirmation (type `restore`). Add `--yes` to skip it for unattended/scripted recovery.
3. Restart the app so migrations run to head:
       docker compose restart api      # or: kubectl rollout restart deploy/api -n ipforge

Raw fallback (Compose):
    docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.dump

Never restore a dump taken from a NEWER app version into an OLDER image — there is no
automatic schema downgrade. Match or exceed the dump's code version.

## Rotating SECRET_KEY
Use `scripts/rotate_secret_key.py` — it re-encrypts every stored secret old→new key.
1. Generate a new key:
       python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
2. Dry-run (no writes):
       OLD_SECRET_KEY=<current> python3 scripts/rotate_secret_key.py --new-key <new> --dry-run
3. Apply, then set `SECRET_KEY=<new>` on the deployment and restart:
       OLD_SECRET_KEY=<current> python3 scripts/rotate_secret_key.py --new-key <new>
Values that don't decrypt with the old key are left untouched and reported — a
half-rotated DB is not corrupted. Re-enter any reported credentials in the UI.

## Upgrade path
Migrations run automatically at boot (`_run_migrations()` upgrades Alembic to head).
1. **Back up first** (`backup.sh`).
2. Pull the new image / `docker compose up --build` (or bump the k8s image tag).
3. The app migrates the schema on start. Watch logs for migration errors.
4. To roll back: redeploy the old image AND restore the pre-upgrade backup — there is
   no automatic downgrade.

## Disaster scenarios
| Scenario | Recovery |
|----------|----------|
| Lost/corrupt database | Restore latest `.dump` (Restore section). `SECRET_KEY` unchanged → encrypted creds intact. |
| Lost `SECRET_KEY` | DB data is fine, but provider/LDAP secrets can't be decrypted. Restore DB, then re-enter every provider credential in Settings → Providers and the LDAP bind password. |
| Failed migration on upgrade | Redeploy previous image, restore pre-upgrade backup, investigate before retrying. |
| Total host loss | Re-provision; set `SECRET_KEY` from your vault; restore latest `.dump`; start app. |
