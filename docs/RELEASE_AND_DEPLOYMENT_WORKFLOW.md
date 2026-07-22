# Funduqii — Release & Deployment Workflow

> **Status:** workflow established in **Phase 1.7**. Documentation only — no CI/CD
> pipeline is built now. This is the process the deployment phase implements.

---

## 1. Environments

- **development** — local; `config.settings.development`, `DEBUG=True`, SQLite/
  local Postgres + optional Redis.
- **staging** — production-like; `config.settings.production`, `DEBUG=False`,
  real Postgres + Redis, used to validate a release before production.
- **production** — live; `config.settings.production`, `DEBUG=False`, backups,
  monitoring, TLS. See
  [PRODUCTION_ENVIRONMENT_MATRIX.md](PRODUCTION_ENVIRONMENT_MATRIX.md).

## 2. Release flow

1. **Gate:** pass the QA release checklist
   ([QA_AND_TESTING_STRATEGY.md](QA_AND_TESTING_STRATEGY.md)) — backend/frontend
   checks green, migrations reviewed.
2. **Build** immutable, tagged images for backend and frontend.
3. **Validate on staging** — deploy, run migrations, smoke test.
4. **Backup before a significant production release** — DB (and media) per
   [BACKUP_AND_RESTORE_STRATEGY.md](BACKUP_AND_RESTORE_STRATEGY.md).
5. **Migrate** — run `migrate` (backward-compatible migrations preferred) and
   `collectstatic`.
6. **Deploy** the new tag; health-check before/while switching traffic.
7. **Smoke test in production** — health endpoints (backend/DB/Redis/Celery/WS)
   + a few critical paths.
8. **Release notes** — what changed, migrations, any deprecations.

## 3. Migrations & release safety

- Migrations run **before/at** deploy, and are **backward-compatible** so the old
  and new code can briefly coexist (enables rollback and zero-downtime later).
- Avoid destructive/irreversible migrations in the same release as the code that
  depends on them; split across releases when needed.

## 4. Rollback

- Keep the **previous known-good image tag**; on failure, redeploy it.
- Because migrations are backward-compatible, code rollback usually needs **no**
  DB restore. Restore the DB from backup only if an irreversible migration ran.
- Document the failure; fix forward before re-attempting.

## 5. Approval & failure handling

- **Who approves:** production releases require explicit owner/maintainer
  approval (mirrors the phase-approval discipline in this project).
- **On failed deploy:** stop, roll back to the last good tag, run smoke tests,
  and only retry after root-cause is understood.
- **Maintenance mode** (later): a static Nginx page while migrations/restores run.

## Out of scope for Phase 1.7

No CI/CD, no pipeline scripts, no Dockerfiles are added now. This is the agreed
workflow for when deployment is set up.

---

## 6. EXPENSES-CLOSURE — release policy for migrations 0011–0013

This chain introduces the manageable `ExpenseType`, the multi-currency FX
snapshot, the private attachment and creation idempotency.

### 6.1 Forward-only — rollback behind 0011 is NOT a supported recovery path

- `0011` additive (all new columns nullable/defaulted) → `0012` seed the default
  catalogue for every hotel + backfill each expense from its legacy `category` →
  `0013` heal any late row, then enforce `expense_type NOT NULL`.
- Reversing **behind 0011** DROPS the `expense_types` table. The retained
  `category` column preserves the classification of rows created BEFORE the
  release, but expenses created AFTER it do not write `category`, so their
  classification would be lost permanently.
- Therefore: **never roll back behind 0011.** Recovery from a bad release is
  **restore from backup** (see `BACKUP_AND_RESTORE_STRATEGY.md`), never a
  destructive reverse migration. Fix forward.

### 6.2 Deployment sequence (mandatory order)

1. **Take a database backup** and verify it is restorable.
2. **Suspend expense writes** (maintenance window for the expenses surface):
   `0013` enforces `NOT NULL`, so a row inserted by the OLD release between
   `0012` and `0013` would arrive without a type — `0013` heals such stragglers,
   but suspending writes removes the race entirely. After `0013` the old code
   can no longer insert expenses at all (it does not know the column), so the
   window must not stay open.
3. **Run migrations 0011 → 0013.**
4. **Deploy the new application code.**
5. **Run smoke tests** — record an expense (base and foreign currency), edit it,
   cancel it, post a corrective movement on a closed day, upload and open a
   receipt, and confirm the shift drawer + daily-close totals.
6. **Re-open expense writes.**

> The current `render.yaml` runs `manage.py migrate` inside `buildCommand`,
> i.e. while the previous release is still serving traffic. That ordering does
> not satisfy steps 2–4 and must be changed (or the window accepted explicitly)
> before this chain runs against real data.

### 6.3 Attachment storage prerequisite

Expense receipts are financial documents written to `PRIVATE_MEDIA_ROOT`. That
path MUST resolve to durable private storage (a mounted persistent volume or
private object storage served through the existing gated streaming view) BEFORE
the feature is used in production — see
`MEDIA_AND_OBJECT_STORAGE_STRATEGY.md`. A container-local, ephemeral filesystem
is not acceptable: every redeploy would destroy receipts while the database rows
continue to reference them. Attachments must never be exposed as public media.
