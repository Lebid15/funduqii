# Funduqii / فندقي

A multi-tenant **SaaS platform for hotel management**: a full operations system
for each hotel, a subscription/billing panel for the platform owner, and a
public website for visitors and bookings.

> **Current status: Phase 6 — Reservations + Availability Engine (pending review).**
> Approved so far: all foundations (0, 1, 1.5, 1.6, 1.7, 1.8, 2), Phase 3
> (platform-owner console), Phase 3.1 (premium UI), Phase 4 (hotel settings &
> media) and Phase 5 (floors/room types/rooms). Phase 6 adds the hotel's
> **internal booking system** and a central **availability engine** that
> prevents overbooking — reservations by room type and quantity
> (held/confirmed/cancelled/expired), a date-overlap rule that allows
> back-to-back stays, and backend-enforced availability — under
> `/api/v1/hotel/`, plus a tabbed hotel-side console at `/hotel/reservations`,
> all scoped by hotel membership and permissions (`reservations.*`,
> `availability.view`).
> **Still no check-in/out, no `occupied` state, no full guest profile, no money
> (payments/folio/invoices), no public website/booking, and no real maps/WhatsApp**
> — those are later phases. See
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
│  └─ requirements/         # base / development / production dependencies
├─ frontend/                # Next.js + TypeScript app
│  └─ src/
│     ├─ app/               # routes: /login, /platform/*, BFF /api/session,/api/platform
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

### Platform-owner endpoints (Phase 3)

All under `/api/v1/platform/`, every one restricted to the platform owner
(`IsPlatformOwner`). Hotel users, staff and unauthenticated requests are rejected.

| Method & path | Purpose |
|---|---|
| `GET /api/v1/platform/overview/` | Dashboard counters + recent activity |
| `GET/POST /api/v1/platform/hotels/` | List / create hotel tenants (limited) |
| `GET/PATCH /api/v1/platform/hotels/{id}/` | Hotel detail / update name·slug·status |
| `POST /api/v1/platform/hotels/{id}/manager/` | Create or link the primary manager |
| `GET/POST /api/v1/platform/plans/` | List / create subscription plans |
| `GET/PATCH/DELETE /api/v1/platform/plans/{id}/` | Detail / update / delete (blocked if in use) |
| `GET/POST /api/v1/platform/subscriptions/` | List / create (start trial or activate paid) |
| `GET/PATCH /api/v1/platform/subscriptions/{id}/` | Detail / cancel·expire |
| `GET/PATCH /api/v1/platform/settings/` | Read / update basic platform settings |

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
