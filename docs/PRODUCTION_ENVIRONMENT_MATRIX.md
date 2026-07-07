# Funduqii — Production Environment Matrix

> **Status:** established in **Phase 1.5** (expanded). Documentation only. Only
> **development** exists today; **staging** and **production** are described so
> the differences are explicit before they are provisioned.

---

## Environment comparison

| Aspect | development | staging | production |
|---|---|---|---|
| Settings module | `config.settings.development` | `config.settings.production` | `config.settings.production` |
| `DEBUG` | `True` | **`False`** | **`False`** |
| Database | SQLite fallback or local Postgres | dedicated Postgres (prod-like) | dedicated/managed Postgres |
| Redis | optional (in-process fallback) | required | required |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | `staging.funduqii.com` | `api.funduqii.com,app.funduqii.com` |
| CORS | `http://localhost:3000` | staging origins (HTTPS) | `https://funduqii.com,https://app.funduqii.com` |
| Logging | console, verbose | structured, INFO | structured, INFO + error tracking |
| Email | console backend (later) | real provider (test) | real provider |
| Storage (media) | local `media/` | local or object storage | object storage (S3-compatible) |
| SSL / HSTS | off | on | on (HSTS, redirect) |
| Backups | none | periodic (test restores) | daily + weekly + monthly, off-site |
| Secrets | `*.env.example` placeholders | server-only env, real | server-only env, real |

## Notes

- **No `DEBUG=True` in staging or production**, ever. The production settings
  module hard-requires `SECRET_KEY`, `ALLOWED_HOSTS`, and `DATABASE_URL` from the
  environment and enables the security headers.
- **Secrets never live in Git.** Development uses committed `*.example`
  placeholders; staging/production use uncommitted env files created on the
  server (`backend.env.prod`, `db.env.prod`, `frontend.env.prod`).
- **Staging is not provisioned yet** — this matrix documents the intended
  differences so staging/production can be stood up consistently later.
