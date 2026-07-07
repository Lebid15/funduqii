# Funduqii — Performance & Realtime Strategy

> **Status:** foundation established in **Phase 1.5**. This document is the
> binding strategy for how Funduqii stays fast and scalable as data grows. It
> is **rules and decisions**, not feature work. Later phases must follow it.

---

## 1. Why we need this strategy

Funduqii is a multi-tenant SaaS. Over time there will be many hotels, and each
hotel accumulates large volumes of data: rooms, reservations, guests, payments,
expenses, folio items, restaurant orders, housekeeping/maintenance tasks,
shifts, daily closures, notifications, reports, images and documents. If we do
not design for scale from the start, list screens, dashboards and reports will
become slow and expensive. We establish the foundation now so no re-architecture
is needed later.

## 2. Core rules (non-negotiable)

- **Never load all data at once.** Every list is paginated.
- **All large lists are paginated** using DRF's default pagination
  (`apps/common/pagination.py`: page size 25, `?page_size=` up to 100).
- **All hotel data is tenant-scoped by `hotel_id`.** Every hotel-owned query is
  filtered by the current hotel (resolved from the `X-Hotel-ID` context in
  Phase 2). One hotel can never read another's data.
- **Every large table needs appropriate indexes.** See
  [DATABASE_INDEX_STRATEGY.md](DATABASE_INDEX_STRATEGY.md).
- **The backend is the source of truth.** The frontend renders backend results;
  it never computes money and never treats `localStorage` as a source of truth.

## 3. Caching (Redis)

- **Redis is the cache backend** in real environments (`REDIS_URL`). Development
  falls back to an in-process cache so the app runs without Redis, but real
  performance requires Redis.
- **When to use cache:** expensive, read-heavy, slow-changing, non-sensitive
  data (e.g. reference/config lookups, computed aggregates that tolerate slight
  staleness, rate-limiting counters).
- **When NOT to use cache:** authoritative financial figures, per-request
  authorization decisions, anything security-sensitive, or data that must be
  exact at read time. **Do not cache sensitive data.**
- **No business caching yet.** Phase 1.5 only wires the backend; caching of
  reservations/hotels/reports is added deliberately in later phases with
  explicit invalidation.

## 4. Background jobs (Celery)

- **Celery + Redis** is the background-task foundation (`config/celery.py`).
- **Use Celery for** heavy or slow work that must not block a request: sending
  emails/notifications, generating heavy reports/snapshots, reservation/
  subscription expiries, image processing, backups, bulk operations.
- **Phase 1.5 has no operational tasks** — only a trivial `core.ping` health
  task proving the pipeline. Real tasks arrive in their own phases.
- **Heavy reports** must eventually become **background jobs or precomputed
  snapshots**, never computed inline inside a request once data is large.

## 5. Realtime updates

**Decision: Django Channels + a Redis channel layer (WebSockets).** Rationale:

- We need **server-pushed, bidirectional, low-latency** updates (e.g. live room
  status, new reservations, notifications) across many concurrent dashboard
  users. WebSockets fit this better than one-directional SSE and integrate
  cleanly with a Redis channel layer for multi-process fan-out.
- Channels shares our Redis dependency and Django auth, keeping the stack
  coherent.

**When to use WebSocket:** live operational updates that should appear without a
refresh (room/reservation status changes, new notifications, dashboard tiles).

**When to use polling instead:** low-frequency or non-critical data, simple
status checks, or clients/environments where a socket is unavailable. Polling
must still hit **summary endpoints**, not full-table endpoints.

**Realtime rules:**
- A realtime update **does not reload the whole page** — it patches the specific
  piece of state that changed (server state / targeted UI update).
- Phase 1.5 ships only a **health WebSocket** (`/ws/health/`) to prove the
  ASGI/Channels pipeline. **No operational events** are emitted yet (no
  reservation/room/notification pushes).
- ASGI is served by an ASGI server (daphne/uvicorn) in realtime deployments;
  `runserver` remains Django's WSGI dev server for HTTP.

## 6. Query performance guardrails

- **Prevent N+1 queries.** Use `select_related` (FK/one-to-one) and
  `prefetch_related` (reverse/many-to-many) whenever serializing related data.
- **Only query what you need:** use `.only()/.values()` for wide tables where
  appropriate; avoid loading unused columns/relations.
- **Dashboards use summary endpoints** that return aggregates/counts, never
  whole tables loaded then counted on the client.
- **Watch queries in development.** Django Debug Toolbar may be added locally to
  inspect query counts and detect N+1 (development only; never in production).
  Until then, review query counts manually for new endpoints.

## 7. Transactions & idempotency

- **Sensitive multi-step operations use database transactions**
  (`transaction.atomic`) so they commit all-or-nothing (e.g. check-in/out,
  payments, daily close).
- **Payments and other sensitive operations must support idempotency** (an
  idempotency key / unique constraint) to prevent double execution (e.g. a
  double-submitted payment). Wired per-feature in its phase.

## 8. Files, images & storage

- **Do not store images or large files in the database.** Store only references
  (paths/URLs/keys).
- Use the filesystem `media/` in development and **object storage** (e.g. S3-
  compatible) in production for uploaded images and documents.

## 9. Frontend performance rules

- Large lists use **pagination + server state** (the `PaginatedResponse<T>`
  type), never "load everything".
- **No `localStorage` as a source of truth**; it may only cache
  non-authoritative, re-fetchable state.
- Dashboards consume **summary endpoints**, not full tables.
- Realtime updates patch targeted state; they never trigger a full page reload.

## 10. Performance Budget

Initial, directional targets (not final numbers — a clear baseline to hold the
line and to measure against later):

- **Normal API responses are fast** — target well under ~300 ms server time for
  typical reads at expected load; measure critical endpoints once built.
- **Large lists never exceed the page size** — default 25, hard max 100
  (`?page_size=`). No endpoint returns unbounded rows.
- **Dashboards never fetch whole tables** — they call summary endpoints
  returning aggregates/counts.
- **Images are lazy-loaded** and served in appropriate sizes; never block a
  request on media.
- **Heavy reports are never computed inside a direct request** once data is
  large — move to background jobs (Celery) or precomputed snapshots.
- **Zero N+1 queries** — related data uses `select_related`/`prefetch_related`.
- **Any endpoint exceeding the budget is reviewed** — profile it, add indexes,
  cache, or move work to the background before it ships.

These are enforced by review and by the guardrails in section 6 and
[DATABASE_INDEX_STRATEGY.md](DATABASE_INDEX_STRATEGY.md).

## 11. What Phase 1.5 delivered (foundation only)

Redis cache wiring, Celery app + health task, Channels ASGI + `/ws/health/`,
DRF default pagination, this strategy (incl. performance budget), the index
strategy, env/compose plumbing, and the production-readiness documentation set
(Hetzner deploy, production Docker example, backup/restore, security/firewall,
monitoring, media/object storage, scaling roadmap, environment matrix).
**No operational features, models, endpoints, or events.**

## 12. Enhancements adopted from the legacy reference (Phase 1.8)

- **Search index (later):** a fast engine (e.g. Meilisearch) may be added later
  as a **read/search index only** — PostgreSQL stays the source of truth;
  results remain tenant-scoped.
- **Optimistic updates (guarded):** allowed for non-critical UI actions (filter
  toggles, simple housekeeping status, UI prefs) with a **clear rollback UI**;
  **forbidden** for money, invoices, confirmed reservations, and check-in/out.
- **Skeleton loading:** part of perceived performance — skeletons instead of
  blank pages for tables/cards/detail/reports/results/calendar.
- **Realtime topics are permission-protected:** every WebSocket topic passes
  auth → hotel membership → permission → tenant isolation; never trust
  `hotel_id` alone.
- **Activity Feed ≠ Audit Log:** an operational read-only feed does not replace
  the audit log.

See [PRODUCT_ENHANCEMENT_BACKLOG.md](PRODUCT_ENHANCEMENT_BACKLOG.md) and
[LEGACY_REFERENCE_INSIGHTS.md](LEGACY_REFERENCE_INSIGHTS.md).
