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
