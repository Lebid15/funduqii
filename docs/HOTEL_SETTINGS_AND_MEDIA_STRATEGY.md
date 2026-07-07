# Funduqii — Hotel Settings & Media Strategy

> **Status:** Implemented in **Phase 4 — Hotels + Hotel Settings**.
> **Scope:** the hotel's OWN configuration (identity, contact, location,
> policies, operational defaults) and its visual media (logo/cover/gallery).
> This is **not** hotel operations — no floors, rooms, reservations, guests,
> money, restaurant, housekeeping, etc. Those are later phases.

---

## 1. Why settings live in `apps/hotels` (not `tenancy`)

`tenancy.Hotel` stays a **minimal tenant entity** (name, slug, status) — the
unit of isolation. All the rich, evolving hotel configuration lives in a
separate app, `apps/hotels`, so the tenant model stays small and stable while
settings/media grow. Two models:

- **`HotelSettings`** — OneToOne with `tenancy.Hotel`. One record per hotel,
  auto-created on first read.
- **`HotelMedia`** — many-per-hotel image assets (logo/cover/gallery).

## 2. `HotelSettings` structure

Grouped fields (all optional unless noted):

- **Identity:** `display_name`, `legal_name`, `short_description`,
  `description`, `star_rating` (1–5), `default_language` (ar/en/tr),
  `default_currency`, `timezone`.
- **Contact:** `phone`, `whatsapp_number`, `email`, `website_url`,
  `facebook_url`, `instagram_url`, `social_links` (JSON).
- **Location:** `country`, `city`, `area`, `address_line`, `latitude`,
  `longitude`, `map_url`, `google_place_id`, `location_notes`.
- **Policies:** `check_in_time`, `check_out_time`, `cancellation_policy`,
  `child_policy`, `pet_policy`, `smoking_policy`, `extra_bed_policy`,
  `important_notes`.
- **Operational defaults (future settings only):** `default_booking_status`,
  `allow_public_booking`, `require_guest_phone`, `require_guest_document`.
  These are **stored preferences** for later phases — Phase 4 does **not** build
  reservations or a public website because of them.
- **Metadata:** `created_at`, `updated_at`.

### Maps / WhatsApp fields are values only

`whatsapp_number`, `map_url`, `latitude`, `longitude`, `google_place_id` are
**stored values**. Phase 4 makes **no** external calls: no WhatsApp send, no
Google Maps API, no geocoding, no autocomplete, no map rendering.

## 3. `HotelMedia` structure

`hotel`, `kind` (logo/cover/gallery), `file`, `alt_text`, `sort_order`,
`is_active`, `uploaded_by`, `created_at`, `updated_at`.

- **Files live in storage** (the configured media/storage backend), never in the
  database and never as base64.
- **API responses carry only URL + metadata.**
- DB partial-unique constraints enforce **at most one active logo** and **one
  active cover** per hotel.

## 4. Image rules

- **Allowed types:** `jpg`, `jpeg`, `png`, `webp`. **SVG is rejected** (security).
- **Validation is defense-in-depth:** extension **and** declared content-type
  **and** magic-byte signature are all checked (no Pillow dependency). A spoofed
  or markup file never passes.
- **Size limits** (overridable via env, see `config/settings/base.py`):
  - logo ≤ **1 MB**, cover ≤ **5 MB**, gallery image ≤ **5 MB**.
  - gallery active count ≤ **10**.
- **Safe replace:** uploading a new logo/cover validates first, then — inside one
  transaction — deactivates the previous active one and creates the new active
  one. The old file is never removed before the new one is stored.
- **Gallery:** upload (capped), reorder (`sort_order`), deactivate (`is_active`),
  delete (removes the row and its file).

## 5. Text and media are strictly separate

This is a hard rule (a known failure mode of the legacy project):

- Settings and media have **separate endpoints**.
- The settings serializer has **no file/image fields** — a `PATCH` to text
  settings (name, phone, policies, …) **cannot touch, re-upload, or re-validate**
  any existing image.
- Media operations (upload/replace/reorder/delete) are their own requests.

Endpoints (all under `/api/v1/hotel/`, trailing-slash):

| Method & path | Purpose |
|---|---|
| `GET/PATCH /settings/` | Read / update text settings (auto-created) |
| `GET /profile/` | Compact current-hotel view (tenant + settings + active logo/cover + gallery count) |
| `GET/POST /media/` | List media / upload one image (multipart) |
| `PATCH/DELETE /media/{id}/` | Update metadata (alt/order/active) / delete |

## 6. Tenant isolation & permissions

Every hotel endpoint requires, on the backend:

- JWT auth + an **active** user,
- the **X-Hotel-ID** hotel context (resolved by the tenancy context resolver),
- an **active membership** in that hotel,
- the specific permission: **`settings.view`** (read) or **`settings.update`**
  (write). These already exist in the RBAC registry.

Rules:

- A **manager** holds all permissions of their hotel (view + update).
- **Staff** need an explicit `settings.view` / `settings.update` grant; staff
  without it are denied.
- A user of hotel **A** cannot access hotel **B** (context resolution rejects it).
- A **platform owner is not** a hotel member unless they hold an explicit
  membership.
- **Unauthenticated** requests are rejected.
- **Suspended hotel:** settings/media are **read-only** — writes return
  `403 hotel_suspended`; reads are allowed.

Hiding buttons is never the protection — the backend enforces all of the above.

## 7. Frontend (hotel console)

- A dedicated **hotel-side AppShell** (same central design system as the platform
  console) with a single `/hotel/settings` page; `/hotel` redirects to it.
- Login routes by account: platform owners → `/platform`, hotel users with an
  active membership → `/hotel` (their current hotel id is kept in an **HttpOnly**
  cookie and attached as `X-Hotel-ID` by a same-origin BFF proxy — no tokens or
  hotel ids in JS).
- Settings sections: Identity, Contact, Location, Policies, Operational defaults,
  and Visual identity (media). Text is one form; media is managed separately with
  its own upload/replace/reorder/delete controls. Full ar/en/tr + RTL/LTR,
  responsive, unified loading/empty/error/success states.

## 8. Deferred (Phase 5 / 12 / later)

Floors, room types, rooms, reservations, availability, guests, check-in/out,
payments/expenses/folio/invoices, restaurant, housekeeping, maintenance,
shifts, daily close, reports, the public website & public booking, and **real**
maps/WhatsApp/search integrations. Phase 4 ships hotel settings & media only.
