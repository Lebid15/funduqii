# Funduqii — Guests, Check-in & Check-out Strategy

> **Status:** Implemented in **Phase 7 — Guests + Check-in + Check-out**.
> **Scope:** the hotel's guest directory and the operational front-desk cycle —
> check-in of a confirmed reservation into a room, current residents, arrivals /
> departures today, and operational check-out.
> **Deliberately NOT in scope:** no money at all — no payments, expenses, folio,
> invoices, or taxes; check-out is **operational only**. No restaurant,
> housekeeping/maintenance workflows, shifts, daily close, public website /
> booking, real WhatsApp/maps, or advanced reports. Phase 8 has not started.

---

## 1. Apps & layering

Two focused apps sit on top of the earlier phases:

- **`apps/guests`** — the `Guest` directory.
- **`apps/stays`** — the operational stay layer (`Stay`, `StayGuest`,
  `StayStatusLog`) plus the central `CheckInService` / `CheckOutService`.

Check-in logic never lives in `apps/reservations` (which stays for booking &
availability) or `apps/rooms` (physical inventory). Phase 7 builds the **actual
occupancy layer** on top of a reservation (Phase 6) and a room (Phase 5).

## 2. Models

### `Guest` (`guests`)
Scoped to a hotel: `full_name` (required), `phone`, `email`, `nationality`,
`document_type` + `document_number`, `date_of_birth`, `gender`, `address`,
`notes`, `is_active`, audit stamps. A recorded document is **unique per hotel +
type** (blank documents never collide). **No document images/attachments** are
stored in this phase (deferred — see §10). One hotel can never see another's
guests.

### `Stay` (`stays`)
One guest party occupying one room, from check-in to check-out. `hotel`,
`reservation` (nullable), `reservation_line` (nullable), `room` (PROTECT),
`primary_guest` (PROTECT), `status`, `planned_check_in_date` /
`planned_check_out_date`, `actual_check_in_at` / `actual_check_out_at`,
`checked_in_by` / `checked_out_by`, notes/reason. **Constraint:** a partial
unique index guarantees **at most one `in_house` stay per room** — the database
itself prevents double occupancy.

### `StayGuest` (`stay_guests`)
Links guests to a stay with a `role` (`primary` / `companion`). Unique
`(stay, guest)`, and a partial unique index enforces **exactly one primary
guest per stay**. Guests must belong to the stay's hotel.

### `StayStatusLog` (`stay_status_logs`)
A lightweight per-stay status history (`in_house` → `checked_out`). Not a general
audit log.

## 3. Stay status & derived occupancy

`StayStatus`: `in_house` · `checked_out` · `cancelled`.

**Occupancy is derived, never a manual room status.** A room is "occupied" iff it
has an `in_house` stay. We deliberately do **not** add an `occupied` value to the
Phase 5 `Room.status` — that field stays for manual housekeeping states
(`dirty`/`cleaning`/`maintenance`/`out_of_service`/`archived`). The UI may *show*
a room as occupied, but it reads that from the stay, not from `room.status`.
This keeps a single source of truth and avoids a stored state that could drift
from reality.

## 4. `CheckInService`

Check-in runs through one central service inside a transaction that locks the
room row. Rules:

- The **reservation must be `confirmed`** (held/cancelled/expired ⇒
  `400 invalid_check_in`).
- If a `reservation_line` is given it must belong to the reservation; if that
  line **pins a room**, that room is used (a mismatching passed room is
  rejected). If the line is unassigned, a **room must be chosen** at check-in.
- The room must belong to the hotel, be **`available`** (Phase 7 blocks
  `dirty`/`cleaning` as well as the hard-blocked `maintenance`/`out_of_service`/
  `archived` ⇒ `409 room_not_ready`), not be occupied
  (`409 room_occupied`), not be a duplicate check-in of the same line+room
  (`409 already_checked_in`), and not be **specifically held by a different
  reservation** (via `AvailabilityService.room_is_assigned_in_range` ⇒
  `409 room_assignment_conflict`).
- The primary guest (and any companions) must belong to the hotel.
- On success it creates the `Stay` (`in_house`), a primary `StayGuest` (+
  companions), and a `StayStatusLog`.

**Early/late check-in (documented decision):** check-in is gated by reservation
**status only**, not by today's date — early and late check-ins are both
allowed, with no fees. A multi-room line is checked in **room-by-room** (each
call creates one stay); partial check-in is therefore supported naturally.

## 5. `CheckOutService`

Check-out runs through one central service. Rules:

- Only an **`in_house`** stay can be checked out (else `400 invalid_check_out`).
- It stamps `actual_check_out_at` + `checked_out_by`, sets status
  `checked_out`, and — **documented decision** — flips the room to **`dirty`**
  via the Phase 5 controlled status service so housekeeping can ready it again.
- **No money.** No folio, payment, or invoice is created or closed, and no daily
  close runs. Any financial settlement is Phase 8.

## 6. Current residents / arrivals / departures

- **Current residents** = stays with `status = in_house`.
- **Arrivals today** = `confirmed` reservations with `check_in_date = today`
  that are **not fully checked in** (admitted stays < requested rooms). Purely
  operational display — no money.
- **Departures today** = `in_house` stays with `planned_check_out_date = today`.

## 7. Permissions & tenant isolation

Registry sections: `guests.view/create/update/delete` and
`stays.view/check_in/check_out/update`. Every endpoint enforces the matching
permission on the **backend** via `HasHotelPermission`; a manager holds all,
staff need explicit grants. A user of hotel A cannot touch hotel B; a platform
owner is not a hotel member unless explicitly added; unauthenticated is
rejected. A **suspended hotel** is read-only — view is allowed, but
create/update/check-in/check-out return `403 hotel_suspended`.

Deleting a guest that is referenced by a stay **deactivates** it (soft) instead
of hard-deleting, to preserve stay history; an unreferenced guest is hard-deleted.

## 8. API surface (`/api/v1/hotel/`)

| Method | Path | Permission |
|---|---|---|
| GET / POST | `guests/` | view / create |
| GET / PATCH / DELETE | `guests/{id}/` | view / update / delete |
| GET | `stays/` · `stays/current/` · `stays/departures-today/` | stays.view |
| GET | `stays/arrivals-today/` | stays.view |
| POST | `stays/check-in/` | stays.check_in |
| GET / PATCH | `stays/{id}/` (PATCH = notes only) | stays.view / stays.update |
| POST | `stays/{id}/check-out/` | stays.check_out |
| GET | `stays/{id}/logs/` | stays.view |

New error codes: `invalid_check_in` (400), `invalid_check_out` (400),
`room_occupied` (409), `room_not_ready` (409), `already_checked_in` (409).

## 9. Frontend

Two entries are added to the hotel sidebar: **Front desk** and **Guests**.

- **`/hotel/guests`** — a searchable, paginated guest directory with create/edit
  and delete-or-deactivate.
- **`/hotel/front-desk`** — a tabbed console: **Arrivals today** (confirmed
  arrivals with a check-in action → check-in modal that uses the pinned room or
  asks for one, selects/quick-creates the primary guest, adds companions),
  **Current residents** (occupancy cards with details + check-out), and
  **Departures today** (check-out). The check-out modal states plainly that any
  billing is handled in a later phase. **No check-in/out shortcuts imply money.**

All screens use the central design system, the single icon set, full **ar/en/tr**
with automatic RTL/LTR, unified loading/empty/error/success states, and real
responsiveness. No hardcoded text; no token/JWT in `localStorage`.

## 10. Deferred to later phases

- **Money — Phase 8:** payments, expenses, folio, invoices, taxes, and any
  settlement at check-out.
- **Guest document attachments/images:** deferred (only text fields now).
- Restaurant/cafeteria, full housekeeping & maintenance workflows, lost & found,
  shifts, daily close, public website & booking, real WhatsApp/maps, advanced
  reports and accounting. A broader PostgreSQL + large-dataset performance /
  concurrency pass is planned before production.
