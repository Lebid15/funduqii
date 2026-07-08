# Public Website + Public Booking Strategy (Phase 15)

> Status: implemented (Phase 15). This document records the decisions, the
> security model, and the boundaries of the public-facing side of Funduqii.

## 1. Goal

Visitors (not staff, not platform owners) can:

1. Browse **published** hotels on a public website.
2. See a hotel's public profile and its **publicly visible room types**.
3. Check availability for a date range — through the **same availability
   engine** the hotel console uses.
4. Submit a booking **without a customer account and without payment**.
5. Receive a **booking reference + one-time manage code (token)**.
6. View their booking status and **request** cancellation on a manage page.

The hotel receives the booking in its **existing reservations console** and
confirms/cancels it through the **existing Phase 6 workflow** — no parallel
console was built.

## 2. Explicitly out of scope (forbidden in this phase)

- Payment gateway / Stripe / PayPal / any online payment.
- Customer accounts, customer login, loyalty, coupons.
- Marketplace features, advanced SEO, blog, reviews/ratings.
- OTA / channel manager integrations.
- WhatsApp/Email/SMS/push/chat notifications (Phase 14 stays in-app only).
- Public service orders / QR menu.
- Anything belonging to Phase 16.

## 3. Data model — reuse first (documented decision)

Phase 4's `HotelSettings` already holds the identity/contact/location/policy
fields a public profile needs (display name, descriptions, star rating,
currency, phone/WhatsApp/email/website, country/city/area/address, check-in/
check-out times, cancellation policy) plus the `allow_public_booking` switch,
and `HotelMedia` already holds logo/cover/gallery. **No parallel `public_*`
copies of those were created.** Only what did not exist was added:

### `HotelSettings` (+8)

| Field | Purpose |
| --- | --- |
| `public_is_listed` | master switch: hotel appears on the public site |
| `public_slug` | unique public URL identifier (`/hotels/<slug>`) |
| `public_booking_requires_confirmation` | default **true** → bookings arrive `held` |
| `public_min_nights` / `public_max_nights` | optional public stay bounds |
| `public_terms_text` | terms shown to the visitor before booking |
| `public_sort_order` / `public_featured` | listing order + featured section |

### `RoomType` (+5)

`public_is_visible`, `public_name`, `public_description`,
`public_base_price`, `public_sort_order` — the public name/description/price
fall back to the internal `name`/`description`/`base_rate` when empty.
Capacity is reused (`base_capacity`/`max_capacity`).

### `Reservation` (+4 + one source value)

- `ReservationSource.PUBLIC_WEBSITE` (`public_website`) — new source value.
  It is shown in the console but is **not** offered in the staff create form.
- `public_manage_token_hash` — SHA-256 hex of the manage token (never the
  plaintext).
- `public_manage_token_created_at` — audit timestamp.
- `public_cancel_requested_at` / `public_cancel_reason` — the visitor's
  cancellation REQUEST, surfaced to staff in the reservation details.

## 4. Booking flow

```
visitor → POST /api/v1/public/hotels/<slug>/bookings/
        → validate dates (past / order / ≤366 days ahead / min-max nights)
        → booking_open? (hotel ACTIVE + listed + allow_public_booking)
        → create_reservation(...)     ← the SAME internal engine (Phase 6)
             · availability re-checked inside a transaction
             · overbooking → 409 no_availability (identical to console)
        → status: held (default) | confirmed (only if hotel disabled confirmation)
        → held ⇒ hold_expires_at = now + 72h  (PUBLIC_HOLD_HOURS)
        → booking_kind = future ALWAYS — a public booking NEVER auto checks-in
        → token = secrets.token_urlsafe(32); store sha256(token) only
        → 201 {reference, status, ..., manage_token}   ← plaintext shown ONCE
```

- No `Payment`, `Invoice`, `Folio`, `Stay` or check-in is ever created.
- The Phase 14 `reservation.created` activity hook fires automatically (it is
  inside `create_reservation`), so staff with `reservations.view` are notified
  of public bookings with **zero new notification code**.
- Hard caps: 5 rooms / 20 guests per request, 366 days ahead.

### Hold policy (documented decision)

A `held` public booking blocks inventory for **72 hours**
(`PUBLIC_HOLD_HOURS`). The existing Phase 6 expiry semantics apply: an
unexpired hold blocks availability; once expired it no longer blocks. The
hotel confirms (or cancels) from the reservations console before then.

## 5. Manage page & token security

- The token is 32 bytes of `secrets.token_urlsafe` — returned exactly once in
  the creation response. Only `sha256(token)` is stored.
- Verification uses `hmac.compare_digest` (constant-time).
- A wrong **reference** and a wrong **token** both return the same 404 —
  indistinguishable on purpose (no enumeration oracle).
- The manage payload is visitor-safe: reference, status, hotel name, dates,
  public room-type name, counts, the guest's own contact data,
  `special_requests` and `cancel_requested_at`. **Never**: internal `notes`,
  staff, finance/folio anything, room numbers, other bookings.
- Cancellation is a **request**: it stamps `public_cancel_requested_at` +
  reason (idempotent — first request wins) and never cancels/voids/deletes.
  Staff see it as a warning banner in the reservation details and act through
  the normal cancel workflow.

## 6. Visibility & isolation rules

| Situation | Public behavior |
| --- | --- |
| `public_is_listed=False` | hidden from list AND detail (404) |
| Hotel `suspended` / not ACTIVE | hidden everywhere (404) — bookings impossible |
| `allow_public_booking=False` | profile visible, booking → 403 |
| Room type `public_is_visible=False` or inactive | never listed, booking → 404 |
| Room numbers / internal statuses | never serialized publicly (counts only) |
| Cross-hotel room type on booking | 404 |

## 7. API surface (`/api/v1/public/`, anonymous, throttled)

| Endpoint | Method | Throttle scope |
| --- | --- | --- |
| `hotels/` | GET | `public` (300/min) |
| `hotels/<slug>/` | GET | `public` |
| `hotels/<slug>/availability/` | GET | `public` |
| `hotels/<slug>/bookings/` | POST | `public_booking` (60/hour) |
| `bookings/<reference>/` | GET (token) | `public` |
| `bookings/<reference>/cancel-request/` | POST (token) | `public_booking` |

All views extend one `PublicAPIView` base: `authentication_classes=[]`,
`AllowAny`, `ScopedRateThrottle`. There are **no** payment or customer-auth
endpoints.

## 8. Frontend

- **Pages**: `/` (public home, replaces the old redirect — login and free
  trial links kept), `/hotels`, `/hotels/[slug]` (profile + availability +
  booking form), `/booking/manage`.
- **BFF**: an auth-less passthrough `app/api/public/[...path]/route.ts` →
  Django `/api/v1/public/...` (GET/POST only, no cookies, no tokens).
- **Components**: `components/public/` (`PublicShell`, `PublicHotelCard`,
  `PublicBookingPanel`) built ONLY from the central UI kit + design tokens;
  the new CSS lives in one `globals.css` section.
- **i18n**: new `public` namespace in ar/en/tr with full parity; RTL/LTR
  works on every public page via the existing `I18nProvider`.
- The hotel console gained: a "Public website" settings section, public
  fields in the room-type modal, the `public_website` source label, and a
  cancel-request banner in reservation details.

## 9. What staff see

A public booking appears in the reservations console like any other
reservation with `source=public_website` and
`booking_channel_name="Funduqii Public"`; it is confirmed/cancelled with the
existing Phase 6 actions. The manage-token **hash is never serialized** to
the console. The visitor's cancel request shows as a warning with time and
reason.
