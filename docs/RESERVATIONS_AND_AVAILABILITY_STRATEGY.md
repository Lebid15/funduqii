# Funduqii — Reservations & Availability Strategy

> **Status:** Implemented in **Phase 6 — Reservations + Availability Engine**.
> **Scope:** the hotel's **internal booking system** and a central **availability
> engine** that prevents overbooking. This is a sensitive phase — it becomes the
> foundation for check-in/out (Phase 7), the public website (Phase 12), and
> reports (Phase 13).
> **Deliberately NOT in scope:** no full guest profile, no check-in/check-out,
> no `occupied` state, no payments/folio/invoices/expenses, no public booking,
> no real WhatsApp/maps, no reports/daily-close/shifts. Phase 7 has not started.

---

## 1. Why a separate `apps/reservations` app

Each operational concern is its own app so phases stay self-contained:

- `apps/rooms` — physical inventory (floors, room types, rooms).
- `apps/hotels` — the hotel's own settings & media.
- **`apps/reservations`** — reservations and the availability engine.

Booking logic never lives inside `apps/rooms` or `apps/hotels`. Everything here
is scoped to a `tenancy.Hotel` via a `hotel` foreign key.

## 2. Models

### `Reservation` (`reservations`)
The head of a booking. Fields: `reservation_number`, `status`, `source`,
`check_in_date`, `check_out_date`, a **primary-guest snapshot**
(`primary_guest_name` required, `primary_guest_phone`, `primary_guest_email`),
`adults`, `children`, `notes`, `special_requests`, cancellation bookkeeping
(`cancellation_reason`, `cancelled_at`, `cancelled_by`), `hold_expires_at`
(only meaningful while held), and `created_by`/`updated_by`. `nights` and
`total_guests` are computed properties.

- **`primary_guest_*` is a snapshot only** — there is **no** `Guest` profile
  model. A full guest system is a later phase.
- **Constraints:** `UniqueConstraint(hotel, reservation_number)` — numbers are
  unique per hotel (each hotel has an independent `R00001…` sequence). A
  `CheckConstraint` enforces `check_out_date > check_in_date`.

### `ReservationRoomLine` (`reservation_room_lines`)
A requested block of rooms of one type within a reservation: `room_type`
(**PROTECT**), `quantity` (> 0), optional `adults`/`children`/`notes`. Booking
is **by room type and quantity**, not by a specific physical room.

### `ReservationStatusLog` (`reservation_status_logs`)
A lightweight per-reservation status history (`previous_status`, `new_status`,
`note`, `changed_by`). **Not** a general audit log — just this reservation's
status timeline. Implemented (the "preferred" optional model).

### `ReservationRoomAssignment` — **deferred to Phase 7** (documented decision)
Assigning a specific physical room to a reservation is conceptually part of the
**check-in** flow (Phase 7), and the Phase 6 frontend has no assignment surface.
Building it now would add a room-level overlap/locking path with no UI to drive
it. It is therefore deferred; the `reservations.assign_room` permission is
reserved in the registry (like `check_in`/`check_out`) for when Phase 7 builds
it. Booking-vs-inventory correctness in Phase 6 is enforced at the **room-type**
level, which is all the availability engine needs.

## 3. Reservation status model

`held` · `confirmed` · `cancelled` · `expired`. There is **no** `checked_in`,
`checked_out`, `occupied`, or `no_show` — those belong to Phase 7.

- **`confirmed`** consumes inventory.
- **`held`** consumes inventory **only while `hold_expires_at` is in the
  future**; a lapsed hold consumes nothing (see §5).
- **`cancelled`** / **`expired`** consume nothing.
- Transitions: created as `held` or `confirmed`; `held → confirmed` (confirm);
  `held`/`confirmed → cancelled` (cancel, reason required). A cancelled/expired
  reservation cannot be re-booked or confirmed. Invalid transitions return
  `400 invalid_reservation_transition`.

## 4. The availability engine (`AvailabilityService`)

All availability logic lives in one place (`apps/reservations/availability.py`).
Serializers and views never re-implement it.

### 4.1 Date overlap (and back-to-back)
A stay is the **half-open interval** `[check_in, check_out)`. Two stays overlap
iff `existing.check_in < requested.check_out AND requested.check_in <
existing.check_out`. Consequently **back-to-back** bookings (one checks out the
same day another checks in) do **not** overlap and are always allowed.

### 4.2 What consumes inventory
A reservation blocks rooms while it is `confirmed`, or `held` with a
`hold_expires_at` still in the future. `cancelled`, `expired`, and lapsed holds
block nothing.

### 4.3 How inventory is computed
Physical inventory comes from Phase 5. A room counts as **bookable** when it is
`is_active`, on an active floor, of an active room type, and its manual status
is **not** `maintenance` / `out_of_service` / `archived`.

- **Decision:** transient housekeeping states **`dirty` and `cleaning` are
  counted as bookable**, because a future stay is unaffected by today's
  housekeeping state. Only hard-unavailable states remove a room from inventory.

Per room type: `available = max(0, bookable_rooms − reserved_quantity)`, where
`reserved_quantity` sums the quantities of every blocking, overlapping line.

### 4.4 Overbooking prevention & concurrency
`ensure_can_book` **must** run inside a transaction. It locks the involved room
type rows with `select_for_update` in a **stable id order** (a serialization
point that avoids deadlocks), then re-computes availability and rejects the
operation with `409 no_availability` if any requested line does not fit. Two
concurrent bookings of the same type cannot both pass. **The frontend never
decides bookability — the backend is the source of truth.**

### 4.5 Re-checking on edit
Any change to `check_in_date`, `check_out_date`, or lines on a still-blocking
reservation re-runs the availability check, **excluding that reservation from
the calculation** so it never conflicts with itself. `confirm` re-checks too.

### 4.6 Availability endpoints
`GET /api/v1/hotel/availability/` (dates + optional `room_type`/`adults`/
`children`) returns, per room type: `total_rooms`, `blocked_rooms`,
`reserved_quantity`, `available_quantity`, `can_book`, and a `reason` when not
bookable. `GET /api/v1/hotel/availability/calendar/` returns a simple bounded
(≤ 62 days) per-day grid — no Gantt/drag-and-drop.

## 5. Held reservations

A `held` reservation requires `hold_expires_at`. The availability engine treats
it as blocking only while that time is in the future, so **no background job is
required for correctness** — holds expire lazily at read time. A cleanup task
that flips lapsed holds to `expired` can be added later (Celery) but is not
needed for the math. `POST /reservations/{id}/hold/` refreshes an existing
hold's expiry after re-checking availability.

## 6. Tenant isolation & permissions

- Every query is scoped to `request.hotel`. A reservation line may only
  reference a room type of the **same** hotel (else `400
  cross_tenant_reference`). A user of hotel A cannot read hotel B's
  reservations (404 outside their scope).
- Permissions (registry): `reservations.view/create/update/confirm/cancel`,
  `availability.view` (and reserved `reservations.assign_room` for Phase 7).
  Every endpoint enforces the matching permission on the **backend** via
  `HasHotelPermission`. A manager holds all; staff need explicit grants.
- A **suspended hotel** is read-only: view is allowed, every write
  (create/update/confirm/cancel/hold) returns `403 hotel_suspended`.
- There is **no hard-delete** endpoint. Cancelling (soft, reason required) is
  the only way to retire a reservation.

## 7. API surface (`/api/v1/hotel/`)

| Method | Path | Permission |
|---|---|---|
| GET / POST | `reservations/` | view / create |
| GET | `reservations/overview/` | view |
| GET / PATCH | `reservations/{id}/` | view / update |
| POST | `reservations/{id}/confirm/` | confirm |
| POST | `reservations/{id}/cancel/` | cancel |
| POST | `reservations/{id}/hold/` | update |
| GET | `reservations/{id}/logs/` | view |
| GET | `availability/` · `availability/calendar/` | availability.view |

New error codes: `no_availability` (409), `invalid_reservation_transition`
(400), `cancellation_reason_required` (400).

## 8. Frontend

A **Reservations** entry is added to the hotel sidebar. `/hotel/reservations`
is a tabbed console:

- **Overview** — status summary cards + upcoming arrivals/departures (view only;
  **no check-in/out buttons**).
- **Availability** — a backend-driven checker (dates/guests/type → per-type
  availability cards). The UI only renders the server's answer.
- **Reservations** — a filterable, paginated list (status/type/date-range/
  search) with a create/edit modal (dynamic room lines, guest snapshot,
  hold-or-confirm), a details modal (lines, status history, confirm/cancel/edit)
  and a cancel dialog (reason required).

All screens use the central design system, the single icon set, full **ar/en/tr**
with automatic **RTL/LTR**, unified loading/empty/error/success states, and real
responsiveness. No hardcoded text; no token/JWT in `localStorage`.

## 9. Why several things are deferred

- **No check-in/out or `occupied`** — arrival/departure are shown for planning
  only; actually admitting a guest is Phase 7.
- **No full guest profile** — only a contact snapshot is stored on the booking;
  a guest directory with history/documents is a later phase.
- **No payments/folio/invoices** — Phase 6 records intent to stay, not money
  (Phase 8).
- **No public booking/website** — this is the internal engine only (Phase 12).

## 10. Deferred to later phases

Room assignment, check-in/check-out, `no_show`, guest profiles/documents,
payments, folio, invoices, expenses, restaurant, housekeeping/maintenance
workflows, shifts, daily close, reports, notifications, public website & booking.
A broader PostgreSQL + large-dataset performance/concurrency pass is planned
before production.
