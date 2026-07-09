# Platform Owner Panel Strategy (Phase 16)

> Status: implemented (Phase 16). The completion of the platform owner's SaaS
> panel: hotels, plans, subscriptions, the one-time trial, manual payments,
> central subscription enforcement, and the public-site admin settings.

## 1. Goal

Turn the Phase 3 foundation into a working admin panel: the platform owner
manages hotels (activate/suspend/unsuspend with audit), plans, the full
subscription lifecycle (trial → paid → renew → cancel/expire, history
preserved), sees a real dashboard, restricts hotel operations when no active
subscription exists, and controls the public website's basic content — all
**without any payment gateway**.

## 2. Explicitly out of scope (deferred, deliberately)

Payment gateway / Stripe / PayPal / local gateways · online subscription
payment · automatic bank reconciliation · advanced tax engine · accounting
ledger · advanced platform invoicing · commission engine · OTA/channel
manager · marketplace advanced · customer accounts · WhatsApp/Email/SMS/push
sending · full CRM · affiliate system · advanced coupons/campaigns · public
reviews · **Phase 17**.

## 3. Platform owner vs hotel user

- Every `/api/v1/platform/` endpoint requires `IsPlatformOwner`; hotel
  staff/managers get 403, anonymous 401.
- A platform owner is **not** a hotel member: without a membership they
  cannot call `/api/v1/hotel/` APIs (verified by test + live).
- Platform permissions and hotel permissions never mix; tenant isolation in
  hotel APIs is untouched.
- Hotel managers cannot change their own hotel's platform state: `status`
  was **removed** from the hotel PATCH — status changes go exclusively
  through the audited actions.

## 4. Hotels management

- `POST hotels/{id}/activate|suspend|unsuspend/` — suspension **requires a
  reason**; the reason, timestamp and acting user are stored on the hotel
  (`suspension_reason`, `status_changed_at`, `status_changed_by`).
- No hard delete exists (DELETE → 405). Suspension deletes nothing: reads
  stay, important writes are refused (`hotel_suspended`), and the hotel
  disappears from the public site (Phase 15 filters on ACTIVE). Unsuspend
  restores operations *according to the subscription state*.
- The owner's hotel payload now includes: trial_used, city/country, contact,
  `public_is_listed`/`public_booking_enabled`, rooms/staff/reservations
  counts, current subscription, and the suspension audit.
- List filters: status, subscription status, public listing, city, search.

## 5. Plans

Phase 3 fields are **reused** (documented mapping: `slug` = plan code,
`price` = price for `billing_cycle`, `room_limit`/`user_limit` = max
rooms/staff, `feature_codes` = features). Phase 16 adds only
`price_yearly`, `is_public`, `max_public_bookings_per_month`, `notes`.
Prices are Decimal — never float. A plan referenced by subscriptions cannot
be hard-deleted (`plan_in_use` 409): `deactivate` is the safe alternative
(existing subscriptions keep working; new activations are refused).
Limit *enforcement* (rooms/staff/bookings caps) stays deferred with the
feature flags — the operational hooks are a later decision, documented here.

## 6. Subscription lifecycle

States (Phase 3 model, reused): `trial` · `active` · `past_due` · `expired`
· `cancelled`, with at most ONE live subscription per hotel (DB constraint).

- **Trial — once only, first subscription only.** Refused when the hotel
  ever had a trial **or any previous subscription** (paid/expired/
  cancelled) — Phase 16 tightened `start_trial` accordingly. Never granted
  automatically, never re-granted after it ends (`trial_already_used`).
- **Paid activation is manual** (`activate-paid`): the owner activates it by
  hand, optionally recording a manual payment (cash/bank transfer +
  reference). No gateway; nothing touches the hotel's finance.
- **Renew** extends `ends_at` from max(now, current end) — explicit action
  only, never automatic, history never rewritten.
- **Cancel / expire** terminate a live subscription; the record is kept
  forever (`subscriptions/history/` per hotel).

## 7. Central subscription enforcement

`apps/subscriptions/enforcement.py` is the ONE chokepoint:

- `ensure_hotel_operational(hotel)` raises `hotel_suspended` (suspension
  wins) or `subscription_inactive`. Every hotel app's `_guard_write` (9
  apps: reservations, stays, guests, finance, services, operations, staff,
  shifts, rooms) calls it, covering: reservations create/update,
  check-in/out, payments, expenses, invoices, service orders + posting,
  housekeeping/maintenance, staff create + permission updates, shift
  open/close, daily close, room/floor management.
- `booking_open()` (Phase 15) additionally consults it → **public booking
  stops** when the subscription is inactive (the hotel may stay listed).
- **Time-aware**: no background job flips statuses, so a live-status
  subscription past its effective end (trial_ends_at / ends_at) blocks too.
- **Documented decision:** a hotel with NO subscription records at all is
  NOT blocked — restriction begins with the billing lifecycle ("after the
  trial ends"), keeping legacy/dev tenants and the pre-Phase-16 behavior
  intact.
- Reads always work: lists, reports, notifications, settings. Nothing is
  ever deleted. The frontend banner/disabled buttons are UX only — the
  backend is the protection.

## 8. Manual platform payments

`PlatformSubscriptionPayment` (built): hotel, optional subscription, Decimal
amount, currency, method (cash/bank_transfer/manual/other), reference, note,
received_at, recorded_by, void audit. **Not** a gateway, **not** hotel
finance (no Folio/Invoice/Payment links — tested), no taxes; void with a
reason instead of delete. Can be recorded standalone or inline with
activate-paid/renew.

## 9. Public site settings

`PlatformPublicSettings` (singleton — deliberately not a CMS): header link/
button visibility + per-locale label **overrides** (`{ar,en,tr}`; empty →
built-in dictionary translation), hero title/subtitle/buttons, platform
contact info, footer text. URL fields accept only internal paths or http(s)
links (javascript: etc. rejected). Owner-only write at
`/api/v1/platform/public-site-settings/`; the public site reads the safe
payload anonymously at `/api/v1/public/site-settings/` and falls back to
dictionary texts when unset — the public site never breaks on missing
configuration.

## 10. Hotel console UX

The hotel profile now returns `subscription_state` (status, effective end,
days left, expiring-soon, expired, suspended, write_blocked + reason). The
shell shows one banner: suspended (error) / expired (error) / expiring soon
(warning); the `subscription_inactive` error code maps to a clear translated
message wherever an action is refused. Old data is never hidden; read-only
reports keep working.

## 11. Notifications integration

Reused Phase 14's `record_activity` (category `system` → the hotel's
managers): `hotel.suspended` / `hotel.unsuspended` /
`subscription.trial_started` / `.activated` / `.renewed` / `.expired` /
`.cancelled`. No new notification system, no external channels. A separate
platform-owner notification center was NOT built (deferred — the dashboard
lists recent events).

## 12. Dashboard

`GET /api/v1/platform/dashboard/`: hotel counts (total/active/setup/
suspended), trial/paid hotels, expired + expiring-soon subscriptions (14-day
window), total plans, publicly listed / booking-enabled hotels, recent
hotels + subscription events, and **estimated monthly recurring revenue**
per currency (Decimal; yearly plans normalized /12; custom cycles excluded
and counted). The figure is an administrative estimate — never "profit",
never a legal financial report.
