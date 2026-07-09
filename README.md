# Funduqii / فندقي

A multi-tenant **SaaS platform for hotel management**: a full operations system
for each hotel, a subscription/billing panel for the platform owner, and a
public website for visitors and bookings.

> **Current status: Phase 16 — Platform Owner Panel Completion (pending review).**
> Approved so far: all foundations (0, 1, 1.5, 1.6, 1.7, 1.8, 2), Phase 3
> (platform-owner console), Phase 3.1 (premium UI), Phase 4 (hotel settings &
> media), Phase 5 (floors/room types/rooms), Phase 6 (reservations +
> availability, incl. 6.1 room assignment), Phase 7 (guests + operational
> check-in/out), Phase 8 + 8.1 (internal finance), Phase 9 (internal service
> orders), Phase 10 (housekeeping + maintenance + lost & found), Phase 11
> (staff + flexible permissions), Phase 12 (shifts + handover + daily close),
> Phase 13 (read-only reports & analytics), Phase 14 (in-app notifications +
> activity center) and Phase 15 (public website + public booking with
> one-time manage tokens). Phase 16 completes the **platform owner panel**:
> a real dashboard (counts + expiring-soon + **estimated recurring revenue**
> per currency — never "profit"), audited hotel lifecycle (activate /
> suspend-with-reason / unsuspend; status no longer patchable; no hard
> delete), completed plans (Decimal prices, yearly price, public flag,
> limits; deactivate instead of deleting used plans), the full subscription
> lifecycle (**one-time trial as the FIRST subscription only**, manual paid
> activation with optional manual payment records — cash/bank transfer,
> void-not-delete, fully separate from hotel finance —, renew, cancel,
> expire, preserved history) and **central subscription enforcement**: one
> backend chokepoint refuses every important write (`subscription_inactive`)
> and stops public booking when a hotel has no effectively-live
> subscription, while reads/reports/notifications keep working and nothing
> is deleted; suspension keeps `hotel_suspended` and wins. The hotel console
> shows subscription banners (expiring soon / expired / suspended), and the
> platform owner controls the public site's header links/buttons (per-locale
> label overrides), hero, contact info and footer from a new admin page —
> consumed by the Phase 15 public site with dictionary fallbacks.
> Platform events surface in the hotel's activity feed via Phase 14
> (`hotel.suspended`, `subscription.*`). **No payment gateway, no online
> subscription payment, no customer accounts, no OTA, no external
> messaging, no CRM** — deliberately.
> See
> [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md) for the plan,
> [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) for the engineering rules,
> [PROGRESS_LOG.md](PROGRESS_LOG.md) for per-phase status, and
> [docs/](docs/) for all strategy documents.

---

## Repository structure

```
funduqii/
├─ backend/                 # Django + Django REST Framework API
│  ├─ config/               # project config + split settings (base/dev/prod)
│  ├─ apps/core/            # infrastructure app (health endpoint)
│  ├─ apps/accounts/        # custom user + JWT auth (Phase 2)
│  ├─ apps/tenancy/         # hotels (tenants) + memberships (Phase 2)
│  ├─ apps/rbac/            # permission registry + enforcement (Phase 2)
│  ├─ apps/subscriptions/   # SubscriptionPlan + HotelSubscription (Phase 3)
│  ├─ apps/platform/        # platform-owner API /api/v1/platform/ (Phase 3)
│  ├─ apps/hotels/          # hotel settings + media /api/v1/hotel/ (Phase 4)
│  ├─ apps/rooms/           # floors + room types + rooms /api/v1/hotel/ (Phase 5)
│  ├─ apps/reservations/    # reservations + availability engine /api/v1/hotel/ (Phase 6)
│  ├─ apps/guests/          # guest directory /api/v1/hotel/ (Phase 7)
│  ├─ apps/stays/           # check-in/out + occupancy /api/v1/hotel/ (Phase 7)
│  ├─ apps/finance/         # folios + charges + payments + invoices + expenses /api/v1/hotel/finance/ (Phase 8)
│  ├─ apps/services/        # service catalog + orders -> folio charge /api/v1/hotel/services/ (Phase 9)
│  ├─ apps/operations/      # housekeeping + maintenance + lost & found /api/v1/hotel/operations/ (Phase 10)
│  ├─ apps/staff/           # staff + permission grants management /api/v1/hotel/staff/ (Phase 11)
│  ├─ apps/shifts/          # shifts + handover + daily close /api/v1/hotel/shifts/ (Phase 12)
│  ├─ apps/reports/         # read-only reports & analytics /api/v1/hotel/reports/ (Phase 13)
│  ├─ apps/notifications/   # in-app notifications + activity center /api/v1/hotel/notifications/ (Phase 14)
│  ├─ apps/public_site/     # anonymous public website + booking /api/v1/public/ (Phase 15)
│  └─ requirements/         # base / development / production dependencies
├─ frontend/                # Next.js + TypeScript app
│  └─ src/
│     ├─ app/               # routes: public site (/,/hotels,/booking/manage), /login, /platform/*, /hotel/*, BFF /api/session,/api/platform,/api/hotel,/api/public
│     ├─ components/        # central UI library + layout (AppShell/Sidebar/Topbar)
│     ├─ lib/               # api client, session (BFF), i18n (ar/en/tr), format
│     └─ styles/            # design tokens + global component styles
├─ docs/                    # project documentation
├─ docker-compose.yml       # local PostgreSQL for development
├─ .env.example             # reference for all environment variables
├─ PROJECT_BLUEPRINT.md
├─ DEVELOPMENT_RULES.md
└─ README.md
```

## Requirements

- **Python** 3.12+
- **Node.js** 20+ (tested on 24) and **npm** 10+
- **PostgreSQL** 16 (canonical DB) — or **Docker** to run it via `docker-compose`

---

## Environment setup

Environment files are never committed. Copy the examples and edit as needed:

```powershell
# Backend
copy backend\.env.example backend\.env

# Frontend
copy frontend\.env.local.example frontend\.env.local
```

`.env.example` (repo root) is a combined reference of all variables.

### Start services with Docker (PostgreSQL + Redis)

```powershell
docker compose up -d db redis   # both
# or individually:
docker compose up -d db
docker compose up -d redis
```

- **PostgreSQL** — database/user/password `funduqii` on port `5432`, matching the
  example `DATABASE_URL`. If you do not run Postgres, development falls back to a
  local SQLite file so the app and tests still run — but **PostgreSQL is the
  canonical database**.
- **Redis** — on port `6379`, used for the cache, the Celery broker/result
  backend, and the Channels realtime layer. If `REDIS_URL` is empty, development
  falls back to safe in-process implementations — but **real performance and
  realtime require Redis**. See
  [docs/PERFORMANCE_AND_REALTIME_STRATEGY.md](docs/PERFORMANCE_AND_REALTIME_STRATEGY.md).

---

## Running the backend (Windows / PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements\development.txt
python manage.py migrate
python manage.py runserver
```

- API base:        http://localhost:8000/api/
- Health check:    http://localhost:8000/api/health/  →  `{"status":"ok","service":"funduqii-api"}`

> Using CMD instead of PowerShell? Activate with `.venv\Scripts\activate.bat`.

### Running the Celery worker (background tasks)

Requires Redis (see Docker section) and `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND`
in `backend/.env`.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
# On Windows use the solo pool:
celery -A config worker --pool=solo -l info
```

There are no operational tasks yet — only a `core.ping` health task.

### Realtime / WebSockets (ASGI)

`runserver` serves HTTP (WSGI). WebSockets are served by an ASGI server:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
daphne config.asgi:application
```

A single health socket exists at `ws://localhost:8000/ws/health/` (foundation
only; no operational events). Requires `CHANNEL_LAYER_REDIS_URL` for multi-process
use; otherwise an in-memory layer is used.

## Running the frontend

```powershell
cd frontend
npm install
npm run dev
```

- App: http://localhost:3000 — redirects to `/login`; after signing in as a
  platform owner you land on the console at `/platform`.
- The frontend talks to the API through same-origin **Backend-for-Frontend
  (BFF)** route handlers under `/api/session/*` and `/api/platform/*`. JWTs are
  stored only in **HttpOnly Secure cookies** — never in `localStorage` or any
  JS-readable place. Point the server at the API with `API_INTERNAL_BASE_URL`
  (server-side) and `NEXT_PUBLIC_API_BASE_URL`; both default to
  `http://localhost:8000/api`.
- The console is **platform-owner only**. Non-owners and unauthenticated users
  are rejected by the backend on every call and gated server-side by the
  platform layout; `proxy.ts` additionally redirects to `/login` when no session
  cookie is present.
- The UI follows a **premium design system** (Phase 3.1): centralized design
  tokens, a single icon set (`lucide-react` via the central `Icon` wrapper — no
  emoji), unified components, and full RTL/LTR support. See
  [docs/PREMIUM_UI_DESIGN_SYSTEM.md](docs/PREMIUM_UI_DESIGN_SYSTEM.md).

---

## Running tests & checks

Backend tests:

```powershell
cd backend
python manage.py test
```

Frontend checks:

```powershell
cd frontend
npm run lint
npm run build
```

---

## Authentication, tenancy & permissions (Phase 2)

Phase 2 adds the security foundation: a custom user model, JWT auth, a minimal
multi-tenant (hotel) foundation with memberships, and a flexible permission
system. **No UI is built yet** — these are backend APIs plus the frontend
transport layer only.

### Create the first platform owner

The password is never written in code. It is taken from `--password`, then the
`FUNDUQII_PLATFORM_OWNER_PASSWORD` env var, then an interactive prompt.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
# Non-interactive (env var):
$env:FUNDUQII_PLATFORM_OWNER_PASSWORD = "choose-a-strong-password"
python manage.py create_platform_owner --email owner@example.com --full-name "Platform Owner"
# ...or interactive (prompts for the password):
python manage.py create_platform_owner --email owner@example.com --full-name "Platform Owner"
```

> `python manage.py createsuperuser` still works too (for Django admin access);
> it creates a platform-owner-typed superuser.

### Run migrations

```powershell
cd backend
python manage.py makemigrations
python manage.py migrate
```

### Get a JWT and call the API

```powershell
# 1) Obtain access + refresh tokens
curl -X POST http://localhost:8000/api/auth/token/ -H "Content-Type: application/json" -d "{\"email\":\"owner@example.com\",\"password\":\"...\"}"

# 2) Current user, memberships, and (optional) current hotel context
curl http://localhost:8000/api/auth/me/ -H "Authorization: Bearer <access>"

# 3) Refresh the access token
curl -X POST http://localhost:8000/api/auth/token/refresh/ -H "Content-Type: application/json" -d "{\"refresh\":\"<refresh>\"}"

# 4) Log out (blacklist a refresh token)
curl -X POST http://localhost:8000/api/auth/logout/ -H "Authorization: Bearer <access>" -H "Content-Type: application/json" -d "{\"refresh\":\"<refresh>\"}"
```

### Selecting the current hotel (`X-Hotel-ID`)

Endpoints that operate inside a hotel read the **`X-Hotel-ID`** request header.
The user must hold an *active* membership in that hotel; sending another hotel's
id is rejected. A platform owner is not treated as hotel staff unless they have
an explicit membership.

```powershell
curl http://localhost:8000/api/auth/context/ -H "Authorization: Bearer <access>" -H "X-Hotel-ID: 1"
```

### Permissions (`section.operation`)

Authorization is backend-enforced and expressed as `section.operation` codes
(e.g. `reservations.view`, `payments.void`, `daily_close.run`). A **manager**
holds all of their hotel's permissions by default; **staff** hold only the
codes granted to their membership. Unknown codes are rejected. The registry
lives in `backend/apps/rbac/registry.py`.

### Auth endpoints summary

| Method & path | Purpose | Access |
|---|---|---|
| `POST /api/auth/token/` | Obtain access + refresh | public |
| `POST /api/auth/token/refresh/` | Rotate access token | public (valid refresh) |
| `POST /api/auth/logout/` | Blacklist a refresh token | authenticated |
| `GET /api/auth/me/` | Current user + memberships + hotel context | authenticated |
| `GET /api/auth/context/` | Current hotel context + permissions | member of `X-Hotel-ID` |
| `GET /api/platform/ping/` | Platform-owner foundation probe | platform owner |
| `GET /api/foundation/require-permission/` | Permission-class foundation probe | needs `reports.view` in hotel |

> The `/api/platform/ping/` and `/api/foundation/...` endpoints are **foundation
> probes** used to verify wiring — they are not business features.

### Hotel-side endpoints (Phase 4)

All under `/api/v1/hotel/`, scoped to the caller's hotel context (`X-Hotel-ID`)
and guarded by hotel membership + the `settings.view` / `settings.update`
permission. A user of one hotel cannot access another; a platform owner is not a
hotel member unless explicitly added; a suspended hotel is read-only.

| Method & path | Purpose |
|---|---|
| `GET/PATCH /api/v1/hotel/settings/` | Read / update the hotel's text settings |
| `GET /api/v1/hotel/profile/` | Compact current-hotel view (settings + active logo/cover + gallery count) |
| `GET/POST /api/v1/hotel/media/` | List media / upload one image (multipart; logo/cover/gallery) |
| `PATCH/DELETE /api/v1/hotel/media/{id}/` | Update image metadata / delete |

Text and media are strictly separate — a settings `PATCH` never touches images.
Images are stored files (never base64); responses return URLs + metadata. See
[docs/HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md](docs/HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md).

### Rooms endpoints (Phase 5)

Also under `/api/v1/hotel/`, scoped to the caller's hotel context and guarded by
the `rooms.*` permissions. A floor and room type referenced by a room must
belong to the same hotel; a floor/room type with rooms cannot be deleted
(deactivate instead); a suspended hotel is read-only.

| Method & path | Purpose |
|---|---|
| `GET/POST /api/v1/hotel/floors/` · `GET/PATCH/DELETE .../floors/{id}/` | Floors CRUD |
| `GET/POST /api/v1/hotel/room-types/` · `GET/PATCH/DELETE .../room-types/{id}/` | Room types CRUD |
| `GET/POST /api/v1/hotel/rooms/` · `GET/PATCH/DELETE .../rooms/{id}/` | Rooms CRUD (filters: floor/type/status/search) |
| `POST/PATCH /api/v1/hotel/rooms/{id}/status/` | Change a room's manual status (note required for maintenance/out-of-service) |

Room status is manual ops state only (available/dirty/cleaning/maintenance/
out_of_service/archived) — there is no `reserved`/`occupied` (system-derived
later). See
[docs/FLOORS_ROOM_TYPES_ROOMS_STRATEGY.md](docs/FLOORS_ROOM_TYPES_ROOMS_STRATEGY.md).

### Reservations & availability endpoints (Phase 6)

Also under `/api/v1/hotel/`, scoped to the caller's hotel and guarded by
`reservations.*` / `availability.view`. Bookings are by room type + quantity;
overbooking is prevented on the backend (transaction + row locks). A suspended
hotel is read-only; there is **no hard-delete** — cancelling is the only path.

| Method & path | Purpose |
|---|---|
| `GET/POST /api/v1/hotel/reservations/` | List (filters: status/type/date range/search) / create |
| `GET /api/v1/hotel/reservations/overview/` | Counts + upcoming arrivals/departures (view only) |
| `GET/PATCH /api/v1/hotel/reservations/{id}/` | Read / update (re-checks availability) |
| `POST .../reservations/{id}/confirm/` · `/cancel/` · `/hold/` | Confirm / cancel (reason required) / refresh hold |
| `GET .../reservations/{id}/logs/` | Reservation status history |
| `GET /api/v1/hotel/availability/` · `/availability/calendar/` | Availability by dates (per room type / per day) |

Reservation status is `held`/`confirmed`/`cancelled`/`expired` — no
check-in/out, no `occupied`, no guest profile, no money. Back-to-back stays are
allowed; overlapping ones are blocked. A line may **optionally** pin a specific
room (Phase 6.1, gated by `reservations.assign_room`); a room cannot be assigned
to two overlapping bookings. See
[docs/RESERVATIONS_AND_AVAILABILITY_STRATEGY.md](docs/RESERVATIONS_AND_AVAILABILITY_STRATEGY.md).

### Guests & front-desk endpoints (Phase 7)

Also under `/api/v1/hotel/`, scoped to the caller's hotel and guarded by
`guests.*` / `stays.*`. Check-in/out are **operational only** — no money. A
suspended hotel is read-only.

| Method & path | Purpose |
|---|---|
| `GET/POST /api/v1/hotel/guests/` · `GET/PATCH/DELETE .../guests/{id}/` | Guest directory (delete of a referenced guest deactivates it) |
| `GET /api/v1/hotel/stays/` · `.../stays/current/` | Stays list / current residents |
| `GET .../stays/arrivals-today/` · `.../stays/departures-today/` | Operational arrivals / departures for today |
| `POST /api/v1/hotel/stays/check-in/` | Admit a confirmed reservation into a room (creates a Stay) |
| `POST .../stays/{id}/check-out/` | Operational check-out (room becomes dirty; no invoice) |
| `GET/PATCH .../stays/{id}/` · `GET .../stays/{id}/logs/` | Stay details (PATCH = notes only) / status history |

Occupancy is **derived from active stays** — there is no manual `occupied` room
status. Check-out creates **no** folio/payment/invoice. See
[docs/GUESTS_CHECKIN_CHECKOUT_STRATEGY.md](docs/GUESTS_CHECKIN_CHECKOUT_STRATEGY.md).

### Finance endpoints (Phase 8)

Under `/api/v1/hotel/finance/`, scoped to the caller's hotel and guarded by
`finance.*` / `expenses.*`. This is the **internal money layer** — no external
payment gateway is ever contacted. All money is **Decimal**; posted records are
**voided** (with a reason), never hard-deleted; balances are **computed** from
posted line items; a suspended hotel is read-only.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/hotel/finance/overview/` | Today's totals (open folios, outstanding, payments/expenses today, net, issued invoices) |
| `GET/POST .../finance/folios/` · `GET/PATCH .../folios/{id}/` | Folios (PATCH = notes only) |
| `POST .../folios/{id}/close/` · `/void/` | Close (blocked if balance ≠ 0) / void (reason required) |
| `POST .../folios/{id}/charges/` · `POST .../charges/{id}/void/` | Add a charge (per-line tax) / void a charge |
| `POST .../folios/{id}/payments/` · `POST .../payments/{id}/void/` | Record a receipt / void it |
| `GET .../payments/` · `GET .../payments/{id}/receipt/` | Payments list / printable receipt |
| `POST .../folios/{id}/invoices/` · `POST .../invoices/{id}/issue/` | Create a draft invoice / issue it (freezes an immutable snapshot) |
| `GET .../invoices/` · `GET .../invoices/{id}/` · `.../print/` · `POST .../void/` | Invoices list / detail / printable / void |
| `GET/POST .../finance/expenses/` · `GET/PATCH .../expenses/{id}/` · `.../void/` · `.../voucher/` | Expense vouchers (PATCH only while posted) |

An **issued invoice is an immutable snapshot** — later folio activity never
changes it; corrections are made by voiding and re-issuing. A folio **cannot be
closed with a non-zero balance**. Early-checkout settlement is **manual** (void
or adjustment charge — no auto-refund). See
[docs/FINANCE_FOLIO_PAYMENTS_INVOICES_STRATEGY.md](docs/FINANCE_FOLIO_PAYMENTS_INVOICES_STRATEGY.md).

### Service-order endpoints (Phase 9)

Under `/api/v1/hotel/services/`, scoped to the caller's hotel and guarded by
`services.*` / `service_orders.*`. Orders are an internal order pad; their only
financial exit is **one folio charge, posted once**, created through the
finance services (`type=service`, `source=service_order`).

| Method & path | Purpose |
|---|---|
| `GET /api/v1/hotel/services/overview/` | Today's orders by status, delivered-not-posted, posted-today total, active items |
| `GET/POST .../services/categories/` · `GET/PATCH/DELETE .../categories/{id}/` | Catalog sections (delete blocked while items exist) |
| `GET/POST .../services/items/` · `GET/PATCH/DELETE .../items/{id}/` | Items with Decimal price + tax % (delete blocked once ordered — deactivate) |
| `GET/POST .../services/orders/` · `GET/PATCH .../orders/{id}/` | Orders (line snapshots; items editable only while draft; no DELETE route) |
| `POST .../orders/{id}/status/` | Forward-only workflow `submitted → preparing → ready → delivered` (logged) |
| `POST .../orders/{id}/cancel/` | Cancel with a mandatory reason (blocked once posted) |
| `POST .../orders/{id}/post-to-folio/` | Deliver-gated, once-only posting; auto-creates/reuses the stay's open folio |
| `GET .../orders/{id}/ticket/` | Print-friendly service ticket payload |

See [docs/SERVICE_ORDERS_RESTAURANT_CAFE_STRATEGY.md](docs/SERVICE_ORDERS_RESTAURANT_CAFE_STRATEGY.md).

### Operations endpoints (Phase 10)

Under `/api/v1/hotel/operations/`, scoped to the caller's hotel and guarded by
`housekeeping.*` / `maintenance.*` / `lost_found.*`. Every room status change
goes through the Phase 5 controlled path (validated + logged); nothing here
writes money, and there is no DELETE route anywhere (history is never erased).

| Method & path | Purpose |
|---|---|
| `GET /api/v1/hotel/operations/overview/` | Dirty rooms, waiting/in-progress cleaning, open maintenance, blocked rooms, open lost & found, urgent tasks |
| `GET/POST .../operations/housekeeping/` · `GET/PATCH .../housekeeping/{id}/` | Cleaning tasks `HK00001` (room required; PATCH = metadata while active) |
| `POST .../housekeeping/{id}/status|assign|complete|cancel/` | Forward-only workflow; start ⇒ room `cleaning`; complete ⇒ explicit release-or-keep-dirty; cancel needs a reason |
| `GET/POST .../operations/maintenance/` · `GET/PATCH .../maintenance/{id}/` | Requests `MT00001`; an availability-affecting request blocks the room (`maintenance`/`out_of_service`) |
| `POST .../maintenance/{id}/status|assign|resolve|close|cancel/` | Close is resolve-gated and asks an explicit `room_next_status` (keep/dirty/available) — never an automatic release |
| `GET/POST .../operations/lost-found/` · `GET/PATCH .../lost-found/{id}/` | Lost & found log `LF00001` (text only — no photos/files/barcodes) |
| `POST .../lost-found/{id}/status|claim|return|dispose|close/` | `found → stored → claimed → returned → closed` or dispose-with-reason; returning requires a claimant name or linked guest |

Check-out (Phase 7) additionally auto-creates ONE `checkout_cleaning` task per
stay (idempotent). See
[docs/HOUSEKEEPING_MAINTENANCE_LOST_FOUND_STRATEGY.md](docs/HOUSEKEEPING_MAINTENANCE_LOST_FOUND_STRATEGY.md).

### Staff & permissions endpoints (Phase 11)

Under `/api/v1/hotel/staff/`, scoped to the caller's hotel and guarded by
`staff.*`. Built entirely on the Phase 2 foundation — access is decided by
permission GRANTS only; job titles are descriptive labels and there are no
fixed roles anywhere. Passwords are validated, hashed, and never echoed back.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/hotel/staff/overview/` | Total/active/inactive staff, managers, staff with/without grants |
| `GET/POST .../staff/` · `GET/PATCH .../staff/{id}/` | List/search/filter members; create a NEW staff user; PATCH = descriptive fields only |
| `POST .../staff/link-existing-user/` | Attach an existing user by email (platform owners refused; duplicates 409) |
| `POST .../staff/{id}/deactivate|reactivate/` | Lifecycle instead of delete; the last active manager is protected (409) |
| `POST .../staff/{id}/reset-password/` | Local temporary password (no email is ever sent — delivered outside the system) |
| `GET .../staff/permission-registry/` | The full registry grouped by section — the matrix builds from this |
| `GET/PUT .../staff/{id}/permissions/` | Granted + effective permissions; PUT = transaction-safe bulk replace with anti-escalation guard |
| `GET .../staff/my-permissions/` | Current user's effective permissions — powers the permission-aware sidebar + route guard |

See [docs/STAFF_PERMISSIONS_MANAGEMENT_STRATEGY.md](docs/STAFF_PERMISSIONS_MANAGEMENT_STRATEGY.md).

### Shifts & daily-close endpoints (Phase 12)

Under `/api/v1/hotel/shifts/`, scoped to the caller's hotel and guarded by
`shifts.*` / `daily_close.*`. Shifts organize the daily work — they never
create or mutate finance records (attachment happens inside the finance
services), and the daily-close snapshot documents the day while Phase 8
records remain the single source of financial truth. No DELETE routes.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/hotel/shifts/overview/` | Open/today shifts, pending handovers, last close, expected/counted cash, unassigned movements, today's close status |
| `GET .../shifts/current/` | The caller's open shift + live drawer summary |
| `GET/POST .../shifts/` · `GET/PATCH .../shifts/{id}/` | Shifts `SH00001` (one OPEN per user per hotel — DB-enforced; manager-only open-for-others/pinned date) |
| `POST .../shifts/{id}/close/` | Server-computed expected cash; a counted difference REQUIRES a reason; row-locked |
| `POST .../shifts/{id}/cancel/` · `GET .../shifts/{id}/summary/` | Cancel (reason; blocked once movements attached) / drawer summary by method |
| `GET/POST .../shifts/handovers/` · `GET/PATCH .../handovers/{id}/` | Handovers `HO00001` (draft-editable; accepted = frozen) |
| `POST .../handovers/{id}/submit|accept|reject|cancel/` | Recipient-or-manager guard on accept/reject; reject/cancel need a reason |
| `GET .../shifts/daily-close/` · `GET .../daily-close/{date}/` | Closed/draft days with snapshot + totals |
| `POST .../daily-close/prepare/` | Idempotent DRAFT snapshot preview (locks nothing) |
| `POST .../daily-close/close/` | Validates no open shifts / no pending handovers / never twice, then locks the date for NEW payments, expenses, service postings and shifts (voids stay allowed by design) |

See [docs/SHIFTS_HANDOVER_DAILY_CLOSE_STRATEGY.md](docs/SHIFTS_HANDOVER_DAILY_CLOSE_STRATEGY.md).

### Report endpoints (Phase 13)

Under `/api/v1/hotel/reports/`, scoped to the caller's hotel and guarded by
`reports.*`. **GET-only** (POST → 405): reports never write anything, so a
suspended hotel may still read them. NO new models — every number is computed
on demand from the source records (Decimal money, serialized as strings).
Ranges default to the current month (hotel business date) and are capped at
366 days; occupancy is derived from stay intervals, never from Room.status.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/hotel/reports/overview/` | Ranged counters + `net_cashflow_simple` (deliberately never "profit") |
| `GET .../reports/reservations/` (+`export.csv`) | Status/source/booking-kind/room-type buckets, avg nights, per-day arrivals/departures, paginated list |
| `GET .../reports/occupancy/` | Stay-derived per-day occupancy + rate, live room-status counts, room-type breakdown |
| `GET .../reports/guests/` | New/repeat guests, top nationalities, residents, paginated list |
| `GET .../reports/finance/` (+`payments/export.csv`) | Payments by method/day, expenses by category/day, invoices, folios, voided counts (excluded from totals) — needs `reports.finance` |
| `GET .../reports/services/` | Orders by status/source, posted vs unposted delivered, posted totals, top items |
| `GET .../reports/operations/` | HK/MT/LF buckets + urgent + rooms under maintenance — needs `reports.operations` |
| `GET .../reports/shifts/` (+`export.csv`) · `GET .../reports/daily-close/`(+`/{date}/`) | Shifts with drawer differences, handovers, unassigned movements, closed days + stored snapshots — needs `reports.shifts` |

CSV export additionally requires `reports.export` (AND with the section
permission), respects the same filters/isolation, and is capped at 5000 rows.
See [docs/REPORTS_ANALYTICS_STRATEGY.md](docs/REPORTS_ANALYTICS_STRATEGY.md).

### Notification & activity endpoints (Phase 14)

Under `/api/v1/hotel/notifications/`, scoped to the caller's hotel and
guarded by `notifications.*` / `activity.*`. In-app ONLY — no external
channels exist. Events are recorded exclusively through the central service;
recipients are permission-matched (managers + section viewers, never the
actor, never a deactivated member, never another hotel). No DELETE routes.
A suspended hotel may read AND mark read/archive (user-state only).

| Method & path | Purpose |
|---|---|
| `GET /api/v1/hotel/notifications/overview/` | Unread/warning/danger/today/archived counters + today's visible activity |
| `GET .../notifications/` · `GET .../{id}/` | The caller's OWN inbox (others' notifications are invisible), filterable by unread/archived/category/severity/date |
| `POST .../{id}/mark-read|archive/` · `POST .../mark-all-read/` | Recipient-state operations (`notifications.update`) |
| `GET .../unread-count/` | One-shot badge count for the topbar bell (no polling) |
| `GET .../activity/` · `GET .../activity/{id}/` | The activity feed: everything for managers / `activity.view_all`; otherwise the caller's permission categories plus events they acted in or were targeted by |

14 event types are wired (reservations created/cancelled, check-in/out,
payment recorded/voided, service posting, housekeeping/maintenance
created+done, shift closed, daily close, staff permissions). Metadata is
scrubbed of secret-looking keys; related URLs are internal paths only. See
[docs/NOTIFICATIONS_ACTIVITY_CENTER_STRATEGY.md](docs/NOTIFICATIONS_ACTIVITY_CENTER_STRATEGY.md).

### Public website endpoints (Phase 15)

Under `/api/v1/public/` — **anonymous** (no auth, no hotel header) and
throttled per scope (`public` 300/min, `public_booking` 60/hour). Only
published hotels (`ACTIVE` + `public_is_listed` + slug) are ever visible;
suspended/unlisted hotels are 404. Nothing internal (staff, finance, folios,
internal notes, room numbers) is serialized. No payment and no customer-auth
endpoints exist.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/public/hotels/` | Published hotels (search `q`/`city`/`country`, capped) |
| `GET .../hotels/{slug}/` | Public profile: media, policies, terms, visible room types |
| `GET .../hotels/{slug}/availability/?check_in&check_out` | Per-type available COUNTS via the internal engine — never room numbers |
| `POST .../hotels/{slug}/bookings/` | Create a public booking (no payment, no account): `held` + 72h hold by default, `booking_kind=future` always, overbooking → 409; returns reference + ONE-TIME manage token (SHA-256 stored) |
| `GET .../bookings/{reference}/?token=…` | Manage view (token-gated; wrong ref and wrong token are the same 404) |
| `POST .../bookings/{reference}/cancel-request/` | Cancellation REQUEST (idempotent) — never voids or deletes; staff decide in the console |

Public pages: `/`, `/hotels`, `/hotels/[slug]`, `/booking/manage` through the
auth-less BFF passthrough `/api/public/*`. See
[docs/PUBLIC_WEBSITE_BOOKING_STRATEGY.md](docs/PUBLIC_WEBSITE_BOOKING_STRATEGY.md).

### Platform-owner endpoints (Phase 3 + Phase 16)

All under `/api/v1/platform/`, every one restricted to the platform owner
(`IsPlatformOwner`). Hotel users, staff and unauthenticated requests are rejected.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/platform/overview/` | Phase 3 counters + recent activity |
| `GET /api/v1/platform/dashboard/` | Phase 16 dashboard: hotel/subscription counts, expiring soon, public counts, estimated recurring revenue per currency (never "profit"), recent events |
| `GET/POST /api/v1/platform/hotels/` | List (filters: status/subscription/public/city/search) / create hotel tenants |
| `GET/PATCH /api/v1/platform/hotels/{id}/` | Hotel detail (enriched: subscription, trial_used, public flags, counts, suspension audit) / update name·slug — status is NOT patchable |
| `POST .../hotels/{id}/activate|suspend|unsuspend/` | Audited status lifecycle — suspend REQUIRES a reason; who/when recorded; no hard delete anywhere |
| `POST .../hotels/{id}/manager/` | Create or link the primary manager |
| `POST .../hotels/{id}/subscriptions/start-trial/` | The ONE-TIME free trial — first subscription only, never re-granted |
| `POST .../hotels/{id}/subscriptions/activate-paid/` | Manual paid activation (optional manual payment record) — no gateway |
| `POST .../hotels/{id}/subscriptions/renew|cancel|expire/` | Explicit lifecycle actions; history preserved |
| `GET .../hotels/{id}/subscriptions/history/` | The hotel's full subscription history |
| `GET/POST .../subscription-payments/` · `POST .../{id}/void/` | Manual platform payments (Decimal, void-not-delete, separate from hotel finance) |
| `GET/POST /api/v1/platform/plans/` | List / create plans (+ yearly price, public flag, limits, notes) |
| `GET/PATCH/DELETE .../plans/{id}/` · `POST .../activate|deactivate/` | Update / delete (blocked if in use → deactivate instead) |
| `GET/POST /api/v1/platform/subscriptions/` | List (filters incl. `expiring=soon`) / create |
| `GET/PATCH /api/v1/platform/subscriptions/{id}/` | Detail / cancel·expire |
| `GET/PATCH /api/v1/platform/settings/` | Basic platform settings |
| `GET/PATCH /api/v1/platform/public-site-settings/` | Public-site admin: header links/buttons + per-locale label overrides, hero, contact, footer (safe URLs only) — read publicly at `GET /api/v1/public/site-settings/` |

**Subscription enforcement (Phase 16):** one central backend rule
(`apps/subscriptions/enforcement.py`) refuses every important hotel write —
reservations, check-in/out, payments/expenses/invoices, service orders,
housekeeping/maintenance, staff/permissions, shifts/daily close, rooms and
PUBLIC BOOKING — with `subscription_inactive` when the hotel has no
effectively-live subscription (suspension keeps `hotel_suspended` and wins).
Reads, reports and notifications keep working; nothing is deleted; hotels
with no subscription history (not yet onboarded to billing) are not blocked.
The hotel console reads its own state from `GET /api/v1/hotel/profile/`
(`subscription_state`) and shows expiring-soon/expired/suspended banners.
See [docs/PLATFORM_OWNER_PANEL_STRATEGY.md](docs/PLATFORM_OWNER_PANEL_STRATEGY.md).

### Running tests on PostgreSQL

The suite runs on SQLite by default. To run it against PostgreSQL, point
`DATABASE_URL` at a running instance (e.g. via `docker compose up -d db`):

```powershell
cd backend
$env:DATABASE_URL = "postgres://funduqii:funduqii@localhost:5432/funduqii"
python manage.py test
```

---

## What is implemented so far

- **Phase 1 — Foundation:** monorepo layout, split Django settings, DRF,
  `GET /api/health/`, Next.js + i18n + design tokens + API client.
- **Phase 2 — Auth/Tenancy/RBAC:** custom user model, JWT auth, minimal hotel
  tenant + memberships, tenant-context resolver (`X-Hotel-ID`), a
  `section.operation` permission registry with backend-enforced permission
  classes, a secure platform-owner bootstrap command, and a unified error
  envelope. Frontend gains an auth-aware API client and DTO types (no UI).
- **Phase 1.5 — Scalability & production readiness:** Redis cache (with dev
  fallback), Celery app + `core.ping` health task, Django Channels realtime
  (ASGI router + `/ws/health/`), DRF default pagination (25/`?page_size=`/max
  100), a `PaginatedResponse<T>` frontend type, and the full strategy docs
  (performance + budget, DB indexes, Hetzner deploy, production Docker example,
  backup/restore, security/firewall, monitoring, media/object storage, scaling
  roadmap, environment matrix). Foundation/docs only — no operational tasks,
  events, or models.
- **Phase 1.6 — Maps / messaging / integrations foundation:** strategy docs
  (maps & location, WhatsApp & messaging, external-integrations architecture,
  notification events catalog), disabled-by-default env placeholders, and a
  lightweight `apps/integrations` (provider interfaces + no-op providers).
  Documentation + safe seam only — no maps/WhatsApp calls, no real keys, no
  messages sent, no models.
- **Phase 1.7 — Governance / compliance / QA / release foundation:** strategy
  docs for data governance, audit log, rate limiting & abuse protection, feature
  flags, API versioning (`/api/v1/` going forward), QA & testing (with a release
  checklist), release & deployment workflow, and support & incident response.
  Documentation only — no code, models, endpoints, or UI.
- **Phase 1.8 — Legacy reference insights & enhancement backlog:** useful ideas
  from the legacy reference captured as `docs/LEGACY_REFERENCE_INSIGHTS.md` and a
  tracked `docs/PRODUCT_ENHANCEMENT_BACKLOG.md`, each mapped to its phase, plus a
  blueprint appendix. Documentation only — no code ported, no models/APIs/UI.

### Legacy Reference Usage

The legacy reference (`script1.md` and prior MVP notes) is an **ideas reference
only**. **No code is ported from it.** Its useful ideas were captured in the
backlog and strategy docs and linked to the right phases; the rejected parts
(static roles, old auth/JWT flow, un-isolated WebSockets, DRF→Ninja, committed
env/db) are explicitly not adopted. **The current project remains the single
source of technical truth.** See
[docs/LEGACY_REFERENCE_INSIGHTS.md](docs/LEGACY_REFERENCE_INSIGHTS.md).

### Frontend UI standard (mandatory from Phase 3)

From Phase 3 onward, **no page/component is built ad-hoc**. Every interface uses
the central design system (tokens + shared components), the central i18n
(ar/en/tr with automatic RTL/LTR), a central layout, unified loading/empty/error
states, real responsiveness (mobile → large), accessibility, and the central API
client — and it respects permissions and feature flags while the backend stays
the source of truth. Rules & the page acceptance checklist:
[docs/FRONTEND_DESIGN_SYSTEM_GUIDELINES.md](docs/FRONTEND_DESIGN_SYSTEM_GUIDELINES.md).

### Production deployment

Production runs on `config.settings.production` (`DEBUG=False`) behind Nginx +
TLS on Hetzner. **Production requires real environment values that live only on
the server and are never committed to Git** — see the `*.env.prod.example`
templates, [docker-compose.prod.example.yml](docker-compose.prod.example.yml),
and [docs/HETZNER_PRODUCTION_READINESS.md](docs/HETZNER_PRODUCTION_READINESS.md).

### Maps, Messaging & Integrations Foundation

- **Maps and WhatsApp are NOT enabled yet.** All provider settings default to
  `disabled`, and every value in the env examples is a **placeholder** — no real
  keys or tokens are stored, and no external API is called.
- **Real sending/geocoding comes in later phases.** Integrations use an
  **adapter/provider pattern** (`apps/integrations`), so Funduqii is never tied
  to one vendor; the default provider is a **no-op that sends nothing**.
- **Only the official WhatsApp Business Platform / Cloud API** is supported —
  never WhatsApp Web automation or unofficial solutions.
- **Non-critical messages run asynchronously via Celery** (not inside a request).
- Details: [docs/MAPS_AND_LOCATION_STRATEGY.md](docs/MAPS_AND_LOCATION_STRATEGY.md),
  [docs/WHATSAPP_AND_MESSAGING_STRATEGY.md](docs/WHATSAPP_AND_MESSAGING_STRATEGY.md),
  [docs/EXTERNAL_INTEGRATIONS_ARCHITECTURE.md](docs/EXTERNAL_INTEGRATIONS_ARCHITECTURE.md),
  [docs/NOTIFICATION_EVENTS_CATALOG.md](docs/NOTIFICATION_EVENTS_CATALOG.md).

## What is implemented so far

Through **Phase 3 (pending review)**, the **platform owner's console basics**:

- Platform owner panel basics
- Login UI
- Platform dashboard
- Hotels-as-tenants management (limited: name/slug/status + primary manager)
- Subscription plans
- Hotel subscriptions
- Basic platform settings

## What is NOT implemented yet (later phases)

Everything below is a later phase, delivered per the blueprint:

- Hotel panel
- Public website
- Public booking
- Hotel detailed settings (logo/cover/gallery, address, maps)
- Rooms / floors
- Reservations
- Guests
- Check-in / check-out
- Payments / expenses / folio / invoices
- Restaurant / cafeteria
- Housekeeping / maintenance / lost & found
- Shifts / daily close
- Reports / notifications / full audit log
- Real WhatsApp / maps / search / payment gateway

Roughly:

- **Phase 4+** — Hotels, rooms, reservations, finance, and beyond
