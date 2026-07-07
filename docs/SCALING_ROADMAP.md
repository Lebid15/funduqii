# Funduqii — Scaling Roadmap

> **Status:** roadmap established in **Phase 1.5** (expanded). Documentation
> only — nothing here is implemented now. It describes how the deployment grows
> from one server to a horizontally scaled system without re-architecture.

---

## Stage 1 — Single production server

One Hetzner server runs everything behind Nginx:

- Nginx (reverse proxy + TLS)
- Backend (Django HTTP via Gunicorn) + WS (Daphne, ASGI)
- Frontend (Next.js)
- PostgreSQL
- Redis (cache + broker + channel layer)
- Celery worker
- Media on a local volume

Good for launch and early load. See
[HETZNER_PRODUCTION_READINESS.md](HETZNER_PRODUCTION_READINESS.md).

## Stage 2 — Split the database (and stateful services)

Move stateful services off the app server:

- **App server** — Django + WS + Next.js + Celery (or split worker too).
- **Database server** — dedicated PostgreSQL (or Hetzner managed/dedicated),
  with connection pooling (PgBouncer) as needed.
- **Redis server** — dedicated instance for cache/broker/channels.
- **Backups** — off-site, separate from all of the above.

This isolates the heaviest resource (the DB) and makes the app tier easier to
scale.

## Stage 3 — Load balancer + multiple app servers

- **Multiple app servers** (stateless) behind a **Hetzner Cloud Load Balancer**.
- **Shared media/object storage** (S3-compatible) so any app server can serve
  any request — no local media.
- **Session/sticky considerations:** JWT auth is stateless (no sticky sessions
  needed for the API). WebSockets use the **Redis channel layer** for
  cross-node fan-out; the LB must support WebSocket upgrades (and sticky routing
  for a socket's lifetime if required).
- Redis and PostgreSQL remain centralized (or clustered) shared services.

## Stage 4 — Specialized services

Split concerns into dedicated services as scale demands:

- **Search service** (e.g. for hotels/guests) separate from the primary DB.
- **Reporting/analytics service** — heavy reports computed off the OLTP path
  (snapshots / a read replica / a warehouse).
- **Realtime gateway** — dedicated WS/ASGI tier scaled independently.
- **Worker servers** — dedicated Celery worker nodes (and beat) per queue.
- **Integration services** — payment/notification/third-party integrations
  isolated behind their own boundaries.

## Guiding principles

- Keep app servers **stateless** so they scale horizontally.
- Centralize state in **PostgreSQL, Redis, and object storage**.
- Push heavy/slow work to **background jobs** and **precomputed snapshots**.
- Everything tenant-scoped and paginated from day one (Phase 1.5 foundation) so
  no query pattern blocks scaling later.
