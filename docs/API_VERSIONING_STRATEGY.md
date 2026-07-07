# Funduqii — API Versioning Strategy

> **Status:** decision established in **Phase 1.7**. No operational APIs are built
> now. This fixes the versioning approach before Phase 3 adds real endpoints.

---

## 1. Decision

- **All future operational APIs live under `/api/v1/`.** New business endpoints
  (platform panel, hotel operations, public booking, …) are versioned from day
  one.
- A single, explicit version prefix keeps clients stable and gives us a clean
  path for future `/api/v2/` when a breaking change is unavoidable.

## 2. Current foundation/infra endpoints (temporary exception)

Today's endpoints predate the v1 decision and are **infrastructure/auth
foundation**, not operational features:

- `GET /api/health/`
- `POST /api/auth/token/`, `/api/auth/token/refresh/`, `/api/auth/logout/`,
  `GET /api/auth/me/`, `GET /api/auth/context/`
- `GET /api/platform/ping/`, `GET /api/foundation/require-permission/` (probes)

**Decision:** these remain at their current paths for now and are **documented
as a temporary exception**. When v1 operational APIs land, auth/health may be
exposed under `/api/v1/` as well (with backward-compatible aliases during a
transition) so all clients converge on the versioned surface. No paths change in
Phase 1.7.

## 3. Handling breaking changes

- **Prefer backward-compatible changes** within a version: add fields/endpoints;
  don't remove or repurpose existing ones.
- A genuinely **breaking** change goes to the **next version** (`/api/v2/`); the
  previous version is supported for a defined deprecation window.
- Communicate deprecations in release notes with timelines.

## 4. Backward compatibility rules

- Additive by default (new optional fields, new endpoints).
- Never change the meaning/type of an existing field in place.
- Keep the unified error envelope stable (`{code, message, details?}`).
- Version is in the **URL path** (simple, cache-friendly, explicit).

## Out of scope for Phase 1.7

No `/api/v1/` routes are created now (that would be operational API work). This
document is the rule Phase 3+ follows.
