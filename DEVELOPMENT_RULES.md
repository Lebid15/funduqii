# Funduqii — Development Rules (قواعد التطوير الإلزامية)

These rules are mandatory for every contributor and every phase. They exist to
keep the project clean, correct, and faithful to the blueprint. Breaking one of
these rules is a defect, not a shortcut.

---

## 1. The blueprint is the single source of truth
- [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md) governs scope, phases, and design.
- If code and blueprint disagree, the blueprint wins until the blueprint is
  formally updated.

## 2. Phases are closed and sequential
- No phase begins before the previous one is complete, tested, and reviewed.
- No feature is built outside the current phase's scope.
- "While I'm here" additions are not allowed.

## 3. No random or throwaway code
- No random test/seed data committed as if it were real.
- No temporary hacks that quietly become permanent. If something is temporary,
  it is tracked and removed before the phase closes.

## 4. Data ownership & source of truth
- The **backend is the source of truth**. The frontend renders backend results.
- `localStorage` (or any client storage) is **never** a source of truth. It may
  only cache non-authoritative, re-fetchable state.
- **Financial figures are never computed on the frontend.** All money math is
  done and validated on the backend.

## 5. Internationalization
- **No hardcoded user-facing strings** in the UI. Every string comes from the
  central translation dictionaries (ar / en / tr).
- Error and success messages are translatable (via keys/codes, not raw text).

## 6. Permissions & security (from Phase 2 onward)
- Permissions are the source of truth for what a user can do — not job titles.
- **No cosmetic permissions.** Every permission is enforced on the backend.
- Hiding a button is **not** protection. Any unauthorized operation must be
  rejected by the backend even if the API is called directly.
- Every sensitive operation is checked on the backend and, where relevant,
  written to the audit log.
- **Session tokens live only in HttpOnly Secure cookies (from Phase 3).** JWTs
  (access/refresh) are **never** stored in `localStorage`, `sessionStorage`, or
  any JS-readable place, and are never logged. The browser talks to same-origin
  Backend-for-Frontend (BFF) route handlers that attach the token server-side;
  token refresh (with refresh-token rotation) happens only in route handlers so
  the rotated pair is always persisted. Server-side gates (layout + `proxy.ts`)
  are UX/defense-in-depth only — the backend stays the source of truth.

## 7. Multi-Tenant isolation (from Phase 4 onward)
- Multi-tenant isolation is a foundational rule: one hotel can **never** read or
  write another hotel's data.
- Isolation is enforced on the backend (query scoping + object-level checks),
  not by frontend filtering.

## 8. Secrets & configuration
- **No secrets in Git.** Only `.env.example` files (with placeholder values) are
  committed. Real `.env` / `.env.local` files are git-ignored.
- Configuration comes from the environment, with development and production
  settings kept separate.

### 8a. Media / file uploads (from Phase 4)
- **Files are stored via the storage backend, never in the DB and never as
  base64.** API responses return URLs + metadata only.
- **Media is separate from text.** Image upload/replace/delete have their own
  endpoints; a text `PATCH` must never touch, re-send, or re-validate existing
  images.
- **Validate every upload** by extension + content-type + magic-byte signature,
  reject SVG, and enforce per-kind size and count limits (configurable via env).
- **Safe replace:** validate first; never remove the old file before the new one
  is stored; keep at most one active logo/cover per hotel.
- Full rules: [docs/HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md](docs/HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md).

### 8b. Rooms inventory & manual status (from Phase 5)
- **Room status is manual ops state only** — `available`, `dirty`, `cleaning`,
  `maintenance`, `out_of_service`, `archived`. **Never** add `reserved` or
  `occupied` here; those are **system-derived** from reservations/check-in in
  later phases.
- **Controlled status path:** all status changes go through one service that
  validates, records a `RoomStatusLog` row, and stamps who/when. A note is
  **required** for `maintenance` / `out_of_service`.
- **Inventory integrity:** room number unique per hotel; room-type code unique
  per hotel; a room's floor and room type must belong to the **same** hotel; a
  floor/room type with rooms **cannot be deleted** — deactivate it instead.
- Full rules: [docs/FLOORS_ROOM_TYPES_ROOMS_STRATEGY.md](docs/FLOORS_ROOM_TYPES_ROOMS_STRATEGY.md).

### 8c. Reservations & availability (from Phase 6)
- **The backend is the source of truth for availability.** Overbooking is
  prevented on the server inside a transaction that locks the involved room
  types before re-computing availability; the frontend only renders the answer.
- **One availability engine.** All overlap/inventory logic lives in a central
  service (`AvailabilityService`) — never re-implemented in serializers/views.
- **Date overlap is half-open** (`[check_in, check_out)`): back-to-back stays do
  not overlap and are allowed; genuinely overlapping stays are blocked.
- **Blocking statuses:** `confirmed` and non-expired `held` consume inventory;
  `cancelled`/`expired`/lapsed holds do not. Holds expire **lazily** at read
  time (no background job needed for correctness).
- **No `reserved`/`occupied`/`checked_in`/`checked_out`** statuses, **no guest
  profile**, and **no money** in Phase 6. Store only a primary-guest snapshot on
  the booking. Cancelling is a soft action (reason required) — **no hard-delete**.
- **Room assignment (Phase 6.1)** is an OPTIONAL specific room on a line
  (`quantity` 1, same hotel + room type, bookable), gated by
  `reservations.assign_room`. Assigning a room is **not** check-in. A specific
  room cannot overlap two blocking reservations (back-to-back is fine).
- Full rules: [docs/RESERVATIONS_AND_AVAILABILITY_STRATEGY.md](docs/RESERVATIONS_AND_AVAILABILITY_STRATEGY.md).

### 8d. Guests, check-in & check-out (from Phase 7)
- **Occupancy is DERIVED from an active (`in_house`) stay — never a manual
  `room.status = occupied`.** `Room.status` stays for housekeeping states only.
- **Check-in and check-out go through central services** (`CheckInService` /
  `CheckOutService`), never a view directly. Check-in requires a **confirmed**
  reservation and an **available**, unoccupied room; a DB partial-unique index
  enforces at most one in-house stay per room.
- **Check-out is operational only — no money.** No folio, payment, or invoice is
  created or closed. A vacated room becomes `dirty` (documented decision).
- **No document images/attachments** on guests in this phase. Deleting a guest
  referenced by a stay **deactivates** it (preserves history).
- Full rules: [docs/GUESTS_CHECKIN_CHECKOUT_STRATEGY.md](docs/GUESTS_CHECKIN_CHECKOUT_STRATEGY.md).

### 8e. Finance — folios, payments, invoices, expenses (from Phase 8)
- **Money is `Decimal` only — never a float.** Every amount is quantized to two
  places (`money()`); a single service module (`apps/finance/services.py`) is the
  only path that writes money — views never mutate money fields directly.
- **No hard delete of posted financial records — `void` with a reason.** Charges,
  payments, invoices, and expenses are voided (status + `void_reason` +
  `voided_at`/`voided_by`); a blank reason is rejected. Folios hold their charges/
  payments/invoices with `on_delete=PROTECT`.
- **Balances are computed from posted records — never a stored number.**
  `folio_balance = Σ posted charges − Σ posted payments`. A folio **cannot be
  closed with a non-zero balance**; charges/payments are only allowed while it is
  open.
- **An issued invoice is an immutable snapshot** (frozen lines + totals +
  `balance_at_issue`); later folio activity never changes it — correct by voiding
  and re-issuing. Document numbers (folio/receipt/invoice/expense) are **per
  hotel** and allocated under `select_for_update`.
- **Internal layer only — no external payment gateway, no bank reconciliation,
  no e-invoicing/government integration, no accounting ledger, no payroll.**
  `card`/`electronic` methods are labels on an internal receipt, not a real
  transaction. **Early-checkout settlement is manual** (void or adjustment
  charge — no auto-refund).
- Full rules: [docs/FINANCE_FOLIO_PAYMENTS_INVOICES_STRATEGY.md](docs/FINANCE_FOLIO_PAYMENTS_INVOICES_STRATEGY.md).

### 8f. Service orders — restaurant / café / room service (from Phase 9)
- **Service orders never write money themselves.** Their ONLY financial exit is
  one FolioCharge created through `apps/finance/services.py`
  (`type=service`, `source=service_order`) — no Payment, Invoice, or Expense is
  ever created from an order, and no direct/standalone payment exists.
- **Posting is deliver-gated and once-only.** Only a `delivered` order posts;
  a posted order can never be posted again (row-locked check) nor cancelled —
  corrections are a finance-side charge **void**, never an un-post.
- **Order lines are snapshots** (`item_name`, price, tax frozen at order time)
  with server-computed Decimal totals; items are editable only while draft.
- **Cancellation requires a reason; orders are never hard-deleted**; catalog
  rows in use are deactivated, not deleted. All status changes are logged.
- Full rules: [docs/SERVICE_ORDERS_RESTAURANT_CAFE_STRATEGY.md](docs/SERVICE_ORDERS_RESTAURANT_CAFE_STRATEGY.md).

### 8g. Operations — housekeeping / maintenance / lost & found (from Phase 10)
- **Room status is only ever changed through `apps/rooms/services.change_room_status`**
  (validated + logged). `apps/operations` never writes `Room.status` directly,
  and there is **no `occupied` room status** — occupancy stays derived from
  in-house stays.
- **Housekeeping never overrides a maintenance block.** A room that is
  `maintenance`/`out_of_service`/`archived`, or that has an open
  availability-affecting maintenance request, cannot be made `available` from
  housekeeping (`room_blocked_by_maintenance`). Releasing a room is always an
  explicit action, never a side effect.
- **Closing a maintenance request never auto-releases the room.** Close is
  resolve-gated and requires an explicit `room_next_status`
  (keep / dirty / available); `available` is refused while another open
  blocking request exists.
- **Check-out auto-creates ONE `checkout_cleaning` task per stay** (idempotent,
  same transaction); cancelling any task/request requires a reason; disposing a
  lost & found item requires a reason; returning one requires a claimant name
  or linked guest. Nothing is ever hard-deleted (no DELETE routes) and every
  status change is logged in a lightweight per-record status log.
- Full rules: [docs/HOUSEKEEPING_MAINTENANCE_LOST_FOUND_STRATEGY.md](docs/HOUSEKEEPING_MAINTENANCE_LOST_FOUND_STRATEGY.md).

## 9. Database & migrations
- No random/ad-hoc schema. Models follow the conceptual data model in the
  blueprint.
- Migrations are reviewed, not generated blindly in bulk.

## 10. Design consistency
- One central Design System. No bespoke, one-off styling per page.
- Pages are composed from shared components, tokens, and layout primitives.

## 11. Testing is part of "done"
- No feature is complete without tests appropriate to it (unit, API, permission,
  isolation, availability, financial, etc.).
- Each phase must be tested and green before it is closed.

## 12. Performance, scale, realtime & production (from Phase 1.5)
See [docs/PERFORMANCE_AND_REALTIME_STRATEGY.md](docs/PERFORMANCE_AND_REALTIME_STRATEGY.md),
[docs/DATABASE_INDEX_STRATEGY.md](docs/DATABASE_INDEX_STRATEGY.md), and the
production-readiness set in [docs/](docs/) (Hetzner deploy, backup/restore,
security/firewall, monitoring, media/object storage, scaling roadmap,
environment matrix). Production uses `config.settings.production` with
`DEBUG=False`; **real production secrets live only on the server, never in Git**.
- **Every large list is paginated.** Never return all rows in one response.
- **Every hotel-owned endpoint is tenant-scoped** by the current hotel; never
  rely on the frontend to filter tenants.
- **No unindexed queries on large tables.** Index for real query patterns
  (tenant-first); no random indexes.
- **No heavy report computation inside a direct request** once data is large —
  move to background jobs (Celery) or precomputed snapshots.
- **Do not store images or large files in the database** — use `media/` /
  object storage; keep only references.
- **No `localStorage` as a source of truth** (repeats Rule 4, applied to lists).
- **Sensitive multi-step operations use transactions**; **payments and other
  sensitive operations must support idempotency** to prevent double execution.
- **Watch N+1 queries in development** (`select_related`/`prefetch_related`);
  dashboards use summary endpoints, not full-table loads.
- **Realtime updates patch targeted state** — they never reload the whole page,
  and only foundation health sockets exist until a feature's phase adds events.

## 13. External integrations, maps & messaging (from Phase 1.6)
See [docs/EXTERNAL_INTEGRATIONS_ARCHITECTURE.md](docs/EXTERNAL_INTEGRATIONS_ARCHITECTURE.md),
[docs/WHATSAPP_AND_MESSAGING_STRATEGY.md](docs/WHATSAPP_AND_MESSAGING_STRATEGY.md),
[docs/MAPS_AND_LOCATION_STRATEGY.md](docs/MAPS_AND_LOCATION_STRATEGY.md), and
[docs/NOTIFICATION_EVENTS_CATALOG.md](docs/NOTIFICATION_EVENTS_CATALOG.md).
- **Official WhatsApp only** (WhatsApp Business Platform / Cloud API or an
  approved BSP). **No** WhatsApp Web automation or unofficial solutions, ever.
- **No API keys or tokens in Git** — only disabled placeholders in `*.example`
  files; real values live on the server.
- **Every external integration goes through a provider/adapter** — never couple
  business code to a single vendor. The default provider is a disabled no-op.
- **Non-critical messaging/integration work is async via Celery**, never inside a
  direct request; a non-critical failure must not break the core operation.
- **Guest messages respect consent** and use approved, multi-language templates.
- **Every new notification event is added to the Notification Events Catalog
  before it is implemented.**
- **Location data stays provider-neutral** (coords + neutral `map_url`); map keys
  are domain/permission-restricted, and secret keys stay in the backend env.

## 14. Governance, compliance, QA & release (from Phase 1.7)
See [docs/DATA_GOVERNANCE_STRATEGY.md](docs/DATA_GOVERNANCE_STRATEGY.md),
[docs/AUDIT_LOG_STRATEGY.md](docs/AUDIT_LOG_STRATEGY.md),
[docs/RATE_LIMITING_AND_ABUSE_PROTECTION.md](docs/RATE_LIMITING_AND_ABUSE_PROTECTION.md),
[docs/FEATURE_FLAGS_STRATEGY.md](docs/FEATURE_FLAGS_STRATEGY.md),
[docs/API_VERSIONING_STRATEGY.md](docs/API_VERSIONING_STRATEGY.md),
[docs/QA_AND_TESTING_STRATEGY.md](docs/QA_AND_TESTING_STRATEGY.md),
[docs/RELEASE_AND_DEPLOYMENT_WORKFLOW.md](docs/RELEASE_AND_DEPLOYMENT_WORKFLOW.md),
[docs/SUPPORT_AND_INCIDENT_RESPONSE.md](docs/SUPPORT_AND_INCIDENT_RESPONSE.md).
- **Any sensitive action must write an audit log entry** (who/what/when/which
  hotel) when its phase is built.
- **Any public/auth-facing endpoint must get rate limiting** (app-layer +
  edge) in its phase.
- **Any future operational API is versioned** under `/api/v1/` (breaking changes
  → next version; keep backward compatibility within a version).
- **Any sellable / package-gated capability goes through feature flags** — a
  feature must be enabled for the hotel AND permitted for the user.
- **Any production release requires the QA release checklist** and explicit
  approval; back up before a significant release; keep migrations
  backward-compatible with a known rollback.
- **Any change to sensitive/tenant data requires a tenant-isolation test.**
- **Financial records are voided, never hard-deleted**; prefer soft delete /
  disable over hard delete for meaningful records.

## 15. Legacy reference & enhancement backlog (from Phase 1.8)
See [docs/LEGACY_REFERENCE_INSIGHTS.md](docs/LEGACY_REFERENCE_INSIGHTS.md) and
[docs/PRODUCT_ENHANCEMENT_BACKLOG.md](docs/PRODUCT_ENHANCEMENT_BACKLOG.md).
- **No code is ported from old projects** without review and approval; the
  current project is the single source of technical truth.
- **Every idea from an old reference enters the Product Enhancement Backlog
  first**, before any implementation.
- **Every WebSocket topic is protected** by membership + permission (+ tenant
  isolation); never trust `hotel_id` alone.
- **No optimistic updates** for financial or critical reservation operations
  without a clear rollback path.
- **No sequential IDs exposed** in public URLs / sensitive public APIs (use
  UUID/`public_id`).
- **A search index is never the source of truth** (PostgreSQL is).
- **An Activity Feed never replaces the Audit Log.**
- **Every Command Palette action respects permissions and feature flags.**
- **Every booking token is access-limited/scoped** and exposes no sensitive
  data.

## 16. Centralized UI / UX / responsive / translation (MANDATORY from Phase 3)
Full rules: [docs/FRONTEND_DESIGN_SYSTEM_GUIDELINES.md](docs/FRONTEND_DESIGN_SYSTEM_GUIDELINES.md)
and the premium visual standard [docs/PREMIUM_UI_DESIGN_SYSTEM.md](docs/PREMIUM_UI_DESIGN_SYSTEM.md).
From Phase 3 onward, **no page/component/button/table/form is built ad-hoc**.
- **Premium look is the baseline (from Phase 3.1):** the product must read as a
  finished, sellable SaaS — calm, clean, consistent — never prototype-grade.
- **One icon system only:** `lucide-react` through the central `Icon` wrapper
  (standard size + stroke). **No emoji as icons, no mixing icon sources.**
- **Design tokens only** for colors/fonts/spacing/sizes/shadows/borders/radius/
  states/z-index — no random colors or repeated ad-hoc CSS.
- **Central components only** (Button, Table/DataTable, Input/Select, Modal/
  ConfirmDialog, Toast, EmptyState/LoadingState/ErrorState, PageHeader, FilterBar,
  Pagination, ResponsiveGrid, …); a bespoke variant needs a documented reason.
- **No hardcoded strings** — all text via central i18n (ar/en/tr), with
  automatic RTL/LTR and no breakage on text-length changes.
- **Responsive** on mobile/tablet/laptop/desktop/large; large tables get a mobile
  treatment (cards / controlled horizontal scroll / alt layout); controls wrap.
- **Central layout only** (AppShell/Sidebar/Topbar/Content/PageContainer,
  responsive sidebar) — no per-page layout.
- **Unified states** on every data page: loading / empty / error / success /
  permission-denied / feature-disabled / subscription-restricted (offline later)
  — never a blank page.
- **Accessibility:** focus states, field labels, contrast, not color-only,
  keyboard nav.
- **UI reflects permissions & feature flags but never replaces backend
  enforcement**; UI uses the central API client; money is never computed on the
  frontend.
- **Page acceptance gate:** a new page is accepted only if it meets the checklist
  in the guidelines doc (central components, translations, RTL/LTR, responsive,
  central API client, loading/empty/error, permissions, feature flags, no ad-hoc
  CSS, no hardcoded text, and green build/lint/typecheck).

---

### Quick checklist before closing any phase
- [ ] Scope matches the phase in the blueprint (nothing extra).
- [ ] Backend enforces all sensitive logic (permissions, money, isolation).
- [ ] No hardcoded UI strings; translations present for ar/en/tr.
- [ ] No secrets committed; `.env.example` up to date.
- [ ] Tests written and passing.
- [ ] Lint / type checks passing.
