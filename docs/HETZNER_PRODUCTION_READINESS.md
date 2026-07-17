# Funduqii — Hetzner Production Readiness

> **Status:** planning/strategy established in **Phase 1.5** (expanded). This is
> the professional deployment plan for Hetzner. It is **documentation only** —
> no server is provisioned and no operational features are built here.

Related: [SCALING_ROADMAP.md](SCALING_ROADMAP.md) ·
[SECURITY_AND_FIREWALL_CHECKLIST.md](SECURITY_AND_FIREWALL_CHECKLIST.md) ·
[BACKUP_AND_RESTORE_STRATEGY.md](BACKUP_AND_RESTORE_STRATEGY.md) ·
[MONITORING_AND_OBSERVABILITY_STRATEGY.md](MONITORING_AND_OBSERVABILITY_STRATEGY.md) ·
[MEDIA_AND_OBJECT_STORAGE_STRATEGY.md](MEDIA_AND_OBJECT_STORAGE_STRATEGY.md) ·
[PRODUCTION_ENVIRONMENT_MATRIX.md](PRODUCTION_ENVIRONMENT_MATRIX.md)

---

## 1. Proposed production architecture (Stage 1: single server)

A single Hetzner Cloud server (e.g. CPX/CCX) runs the whole stack behind Nginx,
with everything else on a private/internal Docker network:

```
                       Internet (443/80)
                             │
                        ┌────▼────┐
                        │  Nginx  │  reverse proxy + TLS (Let's Encrypt)
                        └──┬───┬──┘
          funduqii.com /   │   │   \ api.funduqii.com (+ /ws/)
          app.funduqii.com │   │
                    ┌───────▼┐  ┌▼─────────┐   ┌──────────┐
                    │ Next.js│  │ Django   │   │ Django   │
                    │ (3000) │  │ HTTP     │   │ WS (ASGI)│
                    └────────┘  │ Gunicorn │   │ Daphne   │
                                │ (8000)   │   │ (9000)   │
                                └────┬─────┘   └────┬─────┘
                          ┌──────────┼──────────────┤
                     ┌────▼────┐ ┌───▼────┐  ┌──────▼──────┐
                     │Postgres │ │ Redis  │  │ Celery      │
                     │ (5432)  │ │ (6379) │  │ worker      │
                     └─────────┘ └────────┘  └─────────────┘
```

The concrete service list is in
[`docker-compose.prod.example.yml`](../docker-compose.prod.example.yml).

## 2. Domains

| Domain | Serves |
|---|---|
| `funduqii.com` | Public website (visitors + hotel-owner marketing) |
| `app.funduqii.com` | Application shell / dashboards (later phases) |
| `api.funduqii.com` | Backend REST API + WebSockets (`/ws/`) |

DNS A/AAAA records point to the Hetzner server IP (or the Load Balancer later).

## 3. Reverse proxy (Nginx)

- Terminates TLS, forwards to internal services.
- `funduqii.com` / `app.funduqii.com` → `frontend:3000`.
- `api.funduqii.com` → `backend:8000`, and `api.funduqii.com/ws/` upgraded to
  `ws:9000` (WebSocket `Upgrade`/`Connection` headers).
- Serves `/static/` and `/media/` from mounted volumes (or proxies to object
  storage later).
- Adds security headers; enables gzip/brotli; sets sensible timeouts and
  client body size limits for uploads.

## 4. TLS (Let's Encrypt)

- Certificates via Certbot (webroot or DNS challenge), auto-renewed by a cron/
  systemd timer.
- HTTP → HTTPS redirect; HSTS enabled in production settings
  (`SECURE_HSTS_SECONDS`, already in `config/settings/production.py`).

## 5. Running the app processes

- **Django HTTP:** `gunicorn config.wsgi:application` (3+ workers).
- **WebSockets (ASGI):** `daphne config.asgi:application` as a **separate**
  process/service (Channels). Kept separate from the WSGI HTTP workers.
- **Next.js:** `npm run build` then `npm run start` (production server), or a
  static/SSR deployment behind Nginx.
- **PostgreSQL 16** and **Redis 7** as their own services.
- **Celery worker:** `celery -A config worker -l info`.
- **Celery beat** (scheduled tasks): `celery -A config beat -l info` as **one**
  dedicated process (never more than one scheduler). It dispatches the periodic
  jobs defined in `CELERY_BEAT_SCHEDULE` — currently the **hourly ReservationDraft
  cleanup** (`reservations.cleanup_reservation_drafts`) — to the worker over Redis.
  The `beat` service is enabled in `docker-compose.prod.example.yml`.

### Verifying scheduled jobs (worker + beat)

The reservation-number **correctness** never depends on beat (an expired draft is
rejected by its `expires_at` gate at reserve/consume time); beat only performs the
periodic housekeeping that flips stale OPEN drafts to `expired`. Still, confirm it
is actually running:

1. **Worker up:** `docker compose -f docker-compose.prod.yml logs worker` shows
   `celery@… ready`, and `celery -A config inspect ping` returns `pong`.
2. **Task registered:** `celery -A config inspect registered` (or `python manage.py
   shell -c "from config.celery import app; print('reservations.cleanup_reservation_drafts' in app.tasks)"`)
   → the task is present.
3. **Beat reads the schedule:** `docker compose -f docker-compose.prod.yml logs beat`
   shows `Scheduler: Sending due task cleanup-reservation-drafts (reservations.cleanup_reservation_drafts)`
   at the top of each hour.
4. **Executed idempotently:** the worker log shows the task received and succeeded;
   re-running changes nothing, no final `Reservation` is deleted, and no reservation
   number is reused (the cleanup only marks OPEN+expired drafts as `expired`).

Fallback (if not using Celery Beat): run the management command from cron instead —
`python manage.py cleanup_reservation_drafts` hourly — which shares the same core.
Do NOT run both a beat schedule and the cron for the same job.

## 6. Static & media files

- `python manage.py collectstatic` into `staticfiles/` (served by Nginx or a
  CDN). `whitenoise` may be added later if we serve static from Django.
- Media (uploads) live on a mounted volume in Stage 1, and move to
  **S3-compatible object storage** as data grows — see
  [MEDIA_AND_OBJECT_STORAGE_STRATEGY.md](MEDIA_AND_OBJECT_STORAGE_STRATEGY.md).
- **Images and documents are never stored in the database** — only references.

## 7. Environment & secrets

- Production uses `config.settings.production` (`DEBUG=False`, required
  `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`, security headers).
- Secrets live only in **uncommitted** env files on the server
  (`backend.env.prod`, `db.env.prod`, `frontend.env.prod`). Templates:
  `*.env.prod.example`. See
  [PRODUCTION_ENVIRONMENT_MATRIX.md](PRODUCTION_ENVIRONMENT_MATRIX.md).

## 8. Service-separation plan (future)

As load grows, split single-server services onto dedicated nodes (details in
[SCALING_ROADMAP.md](SCALING_ROADMAP.md)):

- **App server(s)** — Django HTTP + WS + Next.js.
- **Database server** — PostgreSQL (or Hetzner managed/dedicated).
- **Redis server** — cache + broker + channel layer.
- **Worker server(s)** — Celery workers (and beat).
- **Object storage** — media/documents (S3-compatible).
- **Load balancer** — Hetzner Cloud LB in front of multiple app servers.

## 9. Handling increased load

- Scale Gunicorn workers / add app servers behind a Load Balancer.
- Add Celery workers/queues for background pressure.
- Cache hot, non-sensitive reads in Redis; precompute heavy reports to snapshots.
- Move media to object storage + CDN to offload the app servers.
- Add read replicas / connection pooling (PgBouncer) for the database later.

## 10. Deploy, rollback & maintenance

- **Deploy:** build images → run migrations (`migrate`) → `collectstatic` →
  start/replace services → health-check before switching traffic.
- **Rollback:** keep the previous image tag; on failure, redeploy the last known
  good tag and restore the DB from backup only if a migration is
  irreversible (prefer backward-compatible migrations).
- **Maintenance mode (later):** a static "maintenance" page served by Nginx
  (feature-flag/env-driven) while migrations or restores run.
- **Zero-downtime later:** rolling updates behind the Load Balancer.

## 11. Health checks

Expose/monitor: backend HTTP `GET /api/health/`; DB connectivity; Redis PING;
Celery worker liveness; and the WebSocket health socket `/ws/health/`. Details in
[MONITORING_AND_OBSERVABILITY_STRATEGY.md](MONITORING_AND_OBSERVABILITY_STRATEGY.md).

## 12. Reverse proxy alternative (Phase 1.8 note)

- **Nginx is the default** reverse proxy in this plan (sections 1 & 3).
- **Caddy** (automatic SSL) is noted as an **optional alternative only** — not
  the primary decision and not adopted now.
