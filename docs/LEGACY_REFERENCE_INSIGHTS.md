# Funduqii — Legacy Reference Insights

> **Status:** established in **Phase 1.8**. This document harvests the **useful
> ideas** from the legacy reference (the old MVP summary in `script1.md` and the
> prior product notes) into our official plan. It is **ideas only** — no code,
> models, pages, APIs, or architecture are imported.

---

## 1. How the legacy reference is used

- The legacy file is an **ideas reference**, **not a technical base**.
- **We do NOT adopt its code.** We keep our approved architecture: Django + DRF
  (not Django Ninja), our custom user + JWT, our tenant isolation, and our
  backend-enforced `section.operation` permissions.
- Reasons we don't port the old code: static role-based permissions (we use
  flexible per-membership permissions), auth/JWT flow and client token storage
  not aligned with our model, WebSockets without tenant/permission isolation,
  and committed `.env`/`db.sqlite3`. Porting any of these would undermine the
  security and multi-tenant foundations already approved.
- **Useful ideas are captured here and in the
  [PRODUCT_ENHANCEMENT_BACKLOG.md](PRODUCT_ENHANCEMENT_BACKLOG.md), and linked to
  the phase where they belong.** The current project remains the single source
  of technical truth.

## 2. Adopted / adapted ideas (with target phase)

### A. Search strategy (Meilisearch later) — **Later**
Fast search over hotels, reservations, guests, phone numbers, reservation
codes, cities/areas, and (later) invoices/payments. **Not now.** Documented as a
future strategy for a dedicated Search phase (around Phase 12–13).
**PostgreSQL stays the source of truth; the search engine is a read/search index
only, never authoritative.**

### B. Command Palette (Ctrl/Cmd+K) — **Later**
Quick access inside the panels (jump to a reservation/guest/room/invoice/staff/
setting/report, create reservation, record payment, open a page). **Deferred**
until the core panels are stable — after Phase 5 / once the hotel panel
foundation exists. Every action must respect permissions and feature flags.

### C. Reservation Timeline / Gantt view — **Adopt → Phase 6**
Show reservations as a time axis per room (rooms axis, days axis, reservations as
bars, colors by status, overlap prevention, weekly/monthly views), with **very
careful** drag/drop later. Added officially to **Phase 6 (Reservations +
Availability Engine)**. **No drag/drop before backend validation, transactions,
and double-booking prevention exist.**

### D. Booking management link by token — **Adopt → Phase 12**
After a public booking, the guest gets a private link to review/track the
booking, open the hotel map, contact the hotel, cancel (if policy allows), and
see arrival instructions. Added to **Phase 12 (Public Website + Public
Booking)**. **The token must be secure and access-limited and must not expose
sensitive data.**

### E. Activity Feed — **Adopt → Phase 13**
A chronological view of hotel/platform activity (new reservation, payment,
reservation edit, room status change, check-in/out, cleaning/maintenance
request, permission change, subscription toggled). Added to **Phase 13** with
Audit Log / Notifications; may appear earlier as a read-only feed once events
exist. **The Activity Feed is NOT a replacement for the Audit Log** — the audit
log is for legal retention/traceability; the feed is for quick operational
display.

### F. Optimistic updates — **Adapt → UX strategy (from Phase 3)**
Update the UI before the request completes for perceived speed. **Allowed** for:
filter toggles, simple housekeeping status, UI order/preference, some
non-financial room states. **Forbidden** for: payments, invoices, void payment,
creating a confirmed reservation, check-in/out, or any financial/legal
operation. Must have a **clear rollback UI** on failure. Added to the UX
strategy.

### G. Skeleton loading — **Adopt → design system (from Phase 3)**
Use skeletons instead of blank pages while loading (tables, cards, detail pages,
reports, hotel results, reservation calendar). Added to the central design/UX
rules; starts with the first real panel in **Phase 3**.

### H. Room status interaction model — **Adopt → Phase 5 (+ Phase 10)**
Interactive room cards that clearly show status and allow changing some states
by permission. Proposed states: `available`, `occupied`, `reserved`, `dirty`,
`cleaning`, `maintenance`, `out_of_service`, `archived`. Added to **Phase 5
(Rooms)**, integrating with **Phase 10 (Housekeeping + Maintenance)**. **A room
tied to a reservation/guest cannot change status without clear backend rules.**

### I. Separate operational screens — **Adopt → Phase 7 & 8**
Split big operations into clear screens: Check-in, Folio, Checkout, Reservation
details, Payment. Added to **Phase 7 (Check-in/out)** and **Phase 8 (Payments +
Folio)** to reduce clutter and clarify the operating cycle.

### J. Public hotels map view — **Adopt → Phase 12**
The hotel results page can offer a list + side map with hotel markers, filters
(city/area/price), and opening a hotel's details from the map. Added to **Phase
12**, building on the Phase 1.6 maps strategy.

### K. Uptime Kuma monitoring — **Adapt → Monitoring (optional)**
A simple, early uptime monitor for the public site, API health, WebSocket
health, and the app page, with down alerts. Added to the monitoring strategy as
an **optional, practical option — not mandatory**.

### L. Caddy as reverse proxy — **Reject as primary (optional note)**
Caddy (automatic SSL) is noted as an **optional alternative only**. **Nginx
stays the default** in the Hetzner docs; we do not adopt Caddy now.

### M. Argon2 password hashing — **Later**
Argon2 as a password-hashing improvement. Added to the security checklist as a
**potential later improvement**; not done now until its impact on auth tests and
the environment is evaluated.

### N. UUID / Public ID strategy — **Adopt (design rule, from Phase 4)**
Use a UUID/`public_id` for entities exposed in APIs and public links (hotels,
reservations, guests, payments, invoices, booking public token, staff, messages,
files). Added as a **design rule before operational models are built**. Internal
sequential `id` may exist, but **sequential IDs are not exposed in public URLs or
sensitive public APIs**.

### O. Realtime topics model — **Adapt (re-implement safely)**
Organize WebSocket topics by hotel and event type, e.g.
`hotel.{hotel_id}.reservations`, `hotel.{hotel_id}.rooms`,
`hotel.{hotel_id}.housekeeping`, `hotel.{hotel_id}.notifications`. We take the
idea but **re-implement it safely**: every topic subscription must pass **auth →
hotel membership → permission → tenant isolation**. **We reject any WebSocket
that trusts `hotel_id` alone without verification.**

## 3. Explicitly rejected (do not port)

- Static role-based permission system (we use flexible per-membership
  permissions). · Auth/JWT flow + client token storage as implemented. ·
  WebSockets without tenant/permission isolation. · Any code, Models, pages, or
  APIs. · Committed `.env` / `db.sqlite3`. · Switching DRF → Django Ninja.

## 4. Idea → decision → phase (summary)

| Idea (from legacy reference) | Decision | Target phase |
|---|---|---|
| A. Search / Meilisearch | Later | Search phase (~12–13) |
| B. Command Palette | Later | after Phase 5 (panel foundation) |
| C. Reservation Timeline / Gantt | Adopt | Phase 6 |
| D. Booking management link by token | Adopt | Phase 12 |
| E. Activity Feed | Adopt | Phase 13 |
| F. Optimistic updates | Adapt | UX (from Phase 3), guarded |
| G. Skeleton loading | Adopt | Design system (from Phase 3) |
| H. Room status interaction model | Adopt | Phase 5 (+ Phase 10) |
| I. Separate operational screens | Adopt | Phase 7 & 8 |
| J. Public hotels map view | Adopt | Phase 12 |
| K. Uptime Kuma | Adapt (optional) | Monitoring (ops) |
| L. Caddy alternative | Reject as primary | Hetzner docs (optional note) |
| M. Argon2 hashing | Later | Security (post-eval) |
| N. UUID / Public ID | Adopt (design rule) | from Phase 4 (before op. models) |
| O. Realtime topics model | Adapt (safe rebuild) | Phase 13 / realtime phases |
| Static roles, old auth/JWT, unsafe WS, code/Models/APIs, DRF→Ninja | **Reject** | — |

See [PRODUCT_ENHANCEMENT_BACKLOG.md](PRODUCT_ENHANCEMENT_BACKLOG.md) for the
tracked backlog.
