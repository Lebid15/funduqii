# Funduqii — Floors, Room Types & Rooms Strategy

> **Status:** Implemented in **Phase 5 — Floors + Room Types + Rooms**.
> **Scope:** the hotel's physical **inventory** — its floors, the room types it
> offers, and the actual rooms with a basic **manual** operational status.
> This is the hotel's **first operational phase**, but it is deliberately **not**
> reservations, availability, guests, check-in/out, or money. Those are later
> phases (6/7/8). No public website or public booking either.

---

## 1. Why a separate `apps/rooms` app

`apps/hotels` owns the hotel's **own configuration** (settings + media).
`apps/rooms` owns the hotel's **physical inventory**. Keeping them in separate
apps keeps each model set small and each phase self-contained. `tenancy.Hotel`
stays the minimal tenant entity (name, slug, status); everything here is scoped
to a hotel via a `hotel` foreign key.

Four models:

- **`Floor`** — a floor / wing within a hotel.
- **`RoomType`** — a category of room (e.g. Standard Double).
- **`Room`** — an actual physical room with a manual status.
- **`RoomStatusLog`** — a lightweight per-room status history (not a general
  audit log).

## 2. Models

### `Floor` (`floors`)
`hotel` (FK, CASCADE), `name` (required), `number`, `description`,
`sort_order`, `is_active`, timestamps. Ordered by `sort_order, id`.

### `RoomType` (`room_types`)
`hotel` (FK, CASCADE), `name`, `code`, `description`, `base_capacity`,
`max_capacity`, `bed_type` (single/double/twin/king/queen/suite, optional),
`amenities` (JSON list), `base_rate` (Decimal, **reference value only** — not a
pricing/billing engine), `is_active`, `sort_order`, timestamps.
**Constraint:** `UniqueConstraint(hotel, code)` — a room-type code is unique
**within a hotel** but reusable across hotels.

### `Room` (`rooms`)
`hotel` (FK, CASCADE), `floor` (FK, **PROTECT**), `room_type` (FK, **PROTECT**),
`number`, `display_name`, `status`, `status_note`, `status_changed_at`,
`status_changed_by` (FK user, SET_NULL), `is_active`, timestamps.
**Constraint:** `UniqueConstraint(hotel, number)` — a room number is unique
**within a hotel** but reusable across hotels. `PROTECT` on floor/room_type is a
second line of defence behind the "cannot delete while in use" service check.

### `RoomStatusLog` (`room_status_logs`)
`hotel`, `room` (CASCADE), `previous_status`, `new_status`, `note`,
`changed_by` (SET_NULL), `created_at`. Every status change writes one row.

## 3. Room status model — manual ops state only

`RoomStatus` choices: **`available`, `dirty`, `cleaning`, `maintenance`,
`out_of_service`, `archived`**.

Intentionally **absent**: `reserved` and `occupied`. Those are **system-derived**
from reservations (Phase 6) and check-in (Phase 7) — they are never a manual
status a user sets here. Phase 5 status is purely housekeeping/operational.

- **Note required:** moving a room into `maintenance` or `out_of_service`
  requires a non-empty `status_note` (`NOTE_REQUIRED_STATUSES`). A missing note
  returns `400 status_note_required`.
- **`archived`:** a soft-retire state. Archived rooms are **hidden by default**
  from the rooms list and only shown when the caller passes
  `include_archived=true` or filters explicitly on `status=archived`.
- All status changes go through one controlled service path
  (`change_room_status`) inside a transaction, which validates the note, writes
  a `RoomStatusLog` row, and stamps `status_changed_at` / `status_changed_by`.

## 4. Business rules

- **Tenant isolation:** every query is scoped to the resolved hotel. A room's
  `floor` and `room_type` **must belong to the same hotel** — a cross-tenant
  reference returns `400 cross_tenant_reference`.
- **Uniqueness:** room number unique per hotel; room-type code unique per hotel.
- **Capacity validation:** `base_capacity` and `max_capacity` must both be
  positive and `max_capacity >= base_capacity`.
- **Deletion guards:** a floor or room type that still has rooms **cannot be
  deleted** (`409 resource_in_use`) — deactivate it (`is_active=false`) instead.
  This is enforced by `ensure_deletable_floor` / `ensure_deletable_room_type`
  and backed by `PROTECT` on the room FKs.
- **Suspended hotel:** view is allowed; every write (create/update/delete and
  status change) is blocked with `403 hotel_suspended` and a clear message.

## 5. Permissions

Registered in `apps/rbac/registry.py` under the `rooms` section:
`rooms.view`, `rooms.create`, `rooms.update`, `rooms.delete`,
`rooms.status_update`.

Every endpoint enforces the matching permission on the **backend** via
`HasHotelPermission("rooms.<op>")` (JWT + active membership + `X-Hotel-ID` +
the permission). The hotel manager holds all permissions; staff need explicit
grants. Hiding buttons in the UI is never the security boundary.

## 6. API surface (`/api/v1/hotel/`)

| Method | Path | Permission |
|---|---|---|
| GET / POST | `floors/` | view / create |
| GET / PATCH / DELETE | `floors/{id}/` | view / update / delete |
| GET / POST | `room-types/` | view / create |
| GET / PATCH / DELETE | `room-types/{id}/` | view / update / delete |
| GET / POST | `rooms/` | view / create |
| GET / PATCH / DELETE | `rooms/{id}/` | view / update / delete |
| POST / PATCH | `rooms/{id}/status/` | status_update |

Rooms list supports filters: `status`, `floor`, `room_type`, `is_active`,
`search` (number/display name), and `include_archived`. Floors/room-types and
rooms are paginated; the frontend reads `.results`.

Errors use the unified envelope. New codes introduced in Phase 5:
`resource_in_use` (409), `cross_tenant_reference` (400),
`status_note_required` (400).

## 7. Frontend

A **Rooms** entry is added to the hotel AppShell sidebar. `/hotel/rooms` is a
tabbed console:

- **Overview** — status summary cards (total / available / needs cleaning /
  cleaning / maintenance / out of service).
- **Floors** — table + create/edit/delete with confirm dialogs.
- **Room types** — table + create/edit/delete, capacity and amenities.
- **Rooms** — a card grid with per-status colour accents and badges, filters
  (floor / type / status / search + show-archived), CRUD, and a status-change
  dialog (note field surfaced for note-required statuses).

All screens use the central design system (tokens, central UI components, the
single lucide-react icon system), full **ar/en/tr** translations with automatic
RTL/LTR, unified loading/empty/error/success states, and real responsiveness.

## 8. What is deferred (out of scope, on purpose)

No reservations, availability engine, guests, check-in/check-out, payments,
expenses, folio, invoices, restaurant, housekeeping workflows, maintenance
tickets, shifts, daily close, reports, public website, or public booking. No
`reserved`/`occupied` statuses. Phase 6 has not started.
