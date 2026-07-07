# Funduqii — Backup & Restore Strategy

> **Status:** strategy established in **Phase 1.5** (expanded). Documentation
> only — no backup jobs are implemented yet. Backups are automated at the
> deployment phase, but the policy below is binding.

---

## 1. What we back up

- **PostgreSQL database** — the source of truth for all business data.
- **Media files** — uploaded images/documents (see
  [MEDIA_AND_OBJECT_STORAGE_STRATEGY.md](MEDIA_AND_OBJECT_STORAGE_STRATEGY.md)).
- **Env templates only** (`*.env.example`, `*.env.prod.example`) — **never real
  secrets**. Real env files are recreated on the server, not restored from a
  repo.

## 2. Database backups (`pg_dump`)

- **Daily** logical backup via `pg_dump` (custom/compressed format), run by a
  cron/systemd timer or a Celery beat job later.
- Example (illustrative, not wired yet):
  `pg_dump --format=custom --file=funduqii_$(date +%F).dump "$DATABASE_URL"`.
- Restore with `pg_restore` into a fresh database.

## 3. Retention policy

| Tier | Frequency | Keep |
|---|---|---|
| Daily | every day | 7 days |
| Weekly | one per week | 4–5 weeks |
| Monthly | one per month | 6–12 months |

Older backups are pruned automatically.

## 4. Off-server copies

- Backups are copied **off the application server** (e.g. Hetzner Storage Box /
  another region / S3-compatible bucket).
- **Do not rely only on server snapshots.** Snapshots are convenient but are not
  a substitute for tested, off-site logical backups.

## 5. Media backups

- Media on a server volume is included in the backup routine (sync to off-site
  storage). Once media moves to object storage, rely on the provider's
  versioning/replication plus periodic integrity checks.

## 6. Restore testing

- **Periodically test a full restore** into a staging/throwaway environment
  (e.g. monthly). A backup that has never been restored is not a backup.
- Verify row counts and a few critical invariants after restore.

## 7. Disaster runbooks (initial)

**Database corruption:**
1. Stop writes (maintenance mode).
2. Restore the latest good `pg_dump` into a new database.
3. Point `DATABASE_URL` at it; run `migrate` if needed; verify; resume.

**Lost server:**
1. Provision a new Hetzner server.
2. Recreate env files (secrets) — not from Git.
3. Restore the latest DB backup and media from off-site storage.
4. Bring services up behind Nginx/TLS; verify health checks.

**Failed new deploy:**
1. Redeploy the previous known-good image tag (rollback).
2. Only restore the DB if a non-reversible migration ran (prefer backward-
   compatible migrations to avoid this).
3. Investigate before re-attempting.

## 8. Out of scope for Phase 1.5

No backup automation, cron jobs, or Celery beat schedules are created now. This
document defines the policy that the deployment phase must implement.
