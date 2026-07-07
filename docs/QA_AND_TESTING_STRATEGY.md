# Funduqii — QA & Testing Strategy

> **Status:** strategy established in **Phase 1.7**. Testing is part of "done" for
> every phase (Development Rule 11). This document defines the test types and the
> release gate.

---

## 1. Test types

- **Unit tests** — business logic in isolation (permissions logic, availability,
  money math, state machines). Fast, no external services.
- **API tests** — endpoint behavior: inputs/outputs, status codes, the unified
  error envelope, pagination.
- **Permission tests** — every `section.operation` is enforced on the backend
  (allow/deny); no cosmetic permissions.
- **Tenant isolation tests** — one hotel can never access another's data
  (a mandatory, standing invariant).
- **Frontend build/type tests** — `npm run lint`, `npx tsc --noEmit`,
  `npm run build` must pass.
- **Smoke tests** — after deploy, hit the health checks and a few critical paths
  (see [MONITORING_AND_OBSERVABILITY_STRATEGY.md](MONITORING_AND_OBSERVABILITY_STRATEGY.md)).

## 2. Later additions

- **End-to-end (E2E)** — full flows across frontend + backend (e.g. Playwright)
  once real UI exists.
- **Performance checks** — measure against the performance budget
  ([PERFORMANCE_AND_REALTIME_STRATEGY.md](PERFORMANCE_AND_REALTIME_STRATEGY.md));
  watch N+1 and slow queries.
- **Security checks** — dependency/vulnerability scanning, auth/permission abuse
  tests, and the security checklist
  ([SECURITY_AND_FIREWALL_CHECKLIST.md](SECURITY_AND_FIREWALL_CHECKLIST.md)).

## 3. Financial & sensitive logic

- Money is computed and validated on the backend; **payment calculation tests**
  and **void/refund** correctness tests are required in the finance phase.
- Sensitive multi-step operations get transaction + idempotency tests.

## 4. Standing commands

```
# Backend
cd backend && python manage.py check && python manage.py test
# Frontend
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

Current status: backend **46/46 tests pass**; frontend lint/type/build pass.

## 5. Release checklist (gate before any deploy)

- [ ] Scope matches the phase; nothing extra.
- [ ] `manage.py check` clean; `makemigrations --check` shows no un-committed migrations.
- [ ] Backend tests green (unit/API/permission/isolation as applicable).
- [ ] Frontend lint + type-check + build green.
- [ ] No hardcoded UI strings; ar/en/tr present for new strings.
- [ ] No secrets committed; env examples updated.
- [ ] Sensitive actions audited; new events in the events catalog.
- [ ] Migrations reviewed and backward-compatible.
- [ ] Backup taken before a significant release; rollback plan known.
- [ ] Smoke tests planned/post-deploy checks defined.

See [RELEASE_AND_DEPLOYMENT_WORKFLOW.md](RELEASE_AND_DEPLOYMENT_WORKFLOW.md).

## 6. Enhancement-driven tests (Phase 1.8 additions, for later)

When these backlog items are built, add tests for:

- **Reservation Timeline (Phase 6)** — overlap prevention / no double-booking.
- **Booking token (Phase 12)** — token validity, scope/expiry, no sensitive-data
  exposure.
- **Activity Feed (Phase 13)** — tenant scoping and permission filtering.
- **Realtime permission isolation** — a WebSocket topic rejects a user without
  membership/permission for that hotel.

See [PRODUCT_ENHANCEMENT_BACKLOG.md](PRODUCT_ENHANCEMENT_BACKLOG.md).
