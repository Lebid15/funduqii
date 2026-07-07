# Funduqii — Monitoring & Observability Strategy

> **Status:** strategy established in **Phase 1.5** (expanded). Documentation
> only — no monitoring stack is deployed yet. Health endpoints already exist.

---

## 1. Logging

- **Structured logging** (JSON in production) with levels; the production
  settings already configure a console logger (`DJANGO_LOG_LEVEL`).
- No secrets or PII in logs. Correlate requests with an id where useful.
- Ship logs to a central sink later (e.g. Loki/ELK or a hosted service).

## 2. Error tracking (later)

- Integrate an error tracker (e.g. Sentry-compatible) for backend and frontend
  to capture exceptions, stack traces (server-side only), and release context.

## 3. Infrastructure metrics

Monitor on the server(s):
- **CPU / RAM / Disk** usage (and disk fill rate).
- **PostgreSQL** — connections, slow queries, replication lag (later), size.
- **Redis** — memory, evictions, connected clients, hit rate.
- **Celery** — worker liveness, queue depth, task failure/latency.

## 4. Application metrics

- **API response time** (p50/p95/p99) per endpoint group.
- **HTTP error rates** — 4xx and 5xx counts/ratios.
- **WebSocket connections** (later, once Channels carries real events) — active
  connections, connect/disconnect rates.
- Background task throughput and failures.

## 5. Alerting

Alert (email/Slack/etc.) when:
- CPU/RAM sustained high; **disk near full**.
- **Backup job fails**.
- **Celery stops** / queue backs up.
- **Redis down** / evictions spike.
- **Many HTTP 500s** in a short window.
- **API latency** exceeds the performance budget.

## 6. Health checks

| Check | How |
|---|---|
| Backend health | `GET /api/health/` → `{"status":"ok","service":"funduqii-api"}` |
| Database health | connectivity probe (simple `SELECT 1` / ORM check) |
| Redis health | `redis-cli PING` → `PONG` / cache round-trip |
| Celery health | `core.ping` task returns `pong` / worker ping |
| WebSocket health | connect `ws://…/ws/health/` → `{"status":"ok","service":"funduqii-ws"}` |

These probe both liveness (process up) and readiness (dependencies reachable).

## 7. Uptime monitoring option (Phase 1.8)

- **Uptime Kuma** is an acceptable **optional, early** uptime monitor for the
  public site, **API health**, **WebSocket health**, and the app page, with
  down alerts. It is **not mandatory** and complements (does not replace) the
  metrics/alerting above.

## 8. Out of scope for Phase 1.5

No dashboards, exporters, agents, or alert rules are deployed now. This document
defines what to measure and alert on when the monitoring stack is set up.
