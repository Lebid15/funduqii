# Funduqii — Database Index Strategy

> **Status:** rules established in **Phase 1.5**. This is a **rules document**,
> not schema work. **No business models are created here.** When later phases
> add large tables, they must apply these rules and justify each index.

---

## 1. Principles

- **Index for real query patterns, not guesses.** Every index must correspond to
  an actual filter/sort/join the application performs.
- **No random indexes.** Indexes cost write performance and storage; add them
  with a stated reason, remove ones that aren't used.
- **Review query plans** (`EXPLAIN ANALYZE`) once tables grow large, and adjust.
- **Tenant-first.** Because all hotel data is scoped by `hotel_id`, most indexes
  on hotel-owned tables should **lead with `hotel_id`** (often as a composite
  index) so tenant-scoped queries stay fast.

## 2. Columns that typically need indexing

For large, hotel-owned tables, consider indexes on:

- `hotel_id` — the tenant scope (almost always part of the index).
- `created_at`, `updated_at` — time-ordered lists and recency filters.
- `status` — status filters (reservations, rooms, tasks, tickets, closures…).
- **date fields** and **date ranges** — check-in/check-out, payment date,
  expense date, daily-close date.
- **foreign keys used in filters/joins** — `room_id`, `reservation_id`,
  `guest_id`, `shift_id`, etc.
- `room_id` — availability and room-status queries.
- **reservation date ranges** — `(hotel_id, check_in, check_out)` style for
  overlap/availability checks.
- `payment_date` — financial reporting and daily close.
- `shift_id` — shift-scoped operations and cash reconciliation.
- `daily_close_date` — daily-close lookups (one per hotel per day).

## 3. Composite indexes

- Build **composite indexes to match multi-column filters/sorts**, in the order
  the query uses them (equality columns first, then range/sort). Examples to
  apply later:
  - `(hotel_id, status, created_at)` for tenant-scoped, status-filtered,
    time-sorted lists.
  - `(hotel_id, check_in, check_out)` for availability/overlap queries.
  - `(hotel_id, payment_date)` for financial reports.

## 4. Partial indexes

- Use **partial indexes** where queries target a small subset (e.g. only
  `active`/open rows), to keep the index small and fast. Example (later):
  an index on open maintenance tickets only.

## 5. Unique constraints

- Use **unique constraints** to enforce invariants and prevent duplicates/
  overlaps per phase. Examples already in place (Phase 2):
  - one membership per `(user, hotel)`;
  - one primary manager per hotel (partial unique).
- Later phases add, e.g., one daily closure per `(hotel, date)`, and guards
  against overlapping reservations on the same room.

## 6. Process rules

- Every new large table's migration must state **which indexes it adds and why**.
- Indexes are **reviewed in code review**, not generated blindly.
- Re-evaluate indexes when access patterns change or tables grow; drop unused
  ones.

## 7. Out of scope for Phase 1.5

No business models or migrations are created here. This document governs how
indexes are chosen when those tables are actually built in their phases (rooms,
reservations, payments, shifts, daily close, etc.).
