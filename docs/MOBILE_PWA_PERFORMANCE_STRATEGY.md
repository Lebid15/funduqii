# Mobile / PWA / Offline / Performance Strategy (Phase 17)

> Status: implemented (Phase 17). What was polished for mobile, what the PWA
> foundation includes, where the safe-offline line is drawn, and which
> performance improvements were applied — with zero product-scope change.

## 1. Goal

Make Funduqii professionally usable on phones, tablets and desktops, add a
safe and minimal PWA foundation (installability + offline fallback), and
apply clear, contract-preserving performance improvements. **No new business
features**: no payment gateway, no customer accounts, no external messaging,
no Phase 18.

## 2. Mobile & tablet responsiveness

The design system already had strong bones (off-canvas sidebar drawer at
≤900px, `.table-scroll` horizontal scrolling for every DataTable, wrapping
page headers/filter bars, 90dvh modals, form grids stacking at ≤560px,
auto-fill stat/detail grids, public grids collapsing at 1000/640px).
Phase 17 adds a CENTRAL polish layer only — no page builds its own layout:

- **Overflow guards**: stat/detail grids use `minmax(min(100%, 14rem), 1fr)`
  so cards can never force horizontal scrolling on narrow phones;
  detail values use `overflow-wrap: anywhere`.
- **Touch targets** (`@media (pointer: coarse)`): buttons, inputs, selects,
  the language switcher, tabs and pagination get ≥2.5–2.75rem (44px-class)
  tap heights.
- **≤640px block**: smaller page/hero titles; modals read as sheets (tight
  edge padding, relaxed inner padding, wrapping footers); denser table
  cells (the wrapper still scrolls); wrapping section headers and mini-list
  rows; single-column filter bars with full-width action buttons; public
  hero/header/footer/booking-dates adjustments; toasts constrained to the
  viewport.
- **Tablet (641–900px)**: the public hotel page stacks the booking panel
  under the content instead of a squeezed sticky aside.
- Everything is token-only, RTL/LTR-safe (logical properties), and applies
  to both consoles and the public site through the shared primitives.

## 3. PWA foundation

- `app/manifest.ts` (Next manifest route): name "Funduqii — فندقي",
  short_name, description, `display: standalone`, `start_url: "/"`,
  theme/background colors mirroring the design tokens, and generated brand
  icons (192/512 + maskable 192/512 + apple-touch 180) under
  `public/icons/`.
- Root layout: `viewport` export (device-width, initial scale, theme color)
  and Apple install metadata.
- Installability: manifest + icons + service worker + HTTPS (deployment
  concern) satisfy the install criteria.
- Deliberately NOT included: push notifications, background sync, offline
  data, shortcuts/share targets — outside the phase scope.

## 4. Safe offline fallback — and the security line

Implemented (allowed):

- `public/sw.js` — a MINIMAL service worker that pre-caches exactly three
  public static assets (the offline page + two icons) and intercepts ONLY
  failed **navigation** requests, answering with `public/offline.html`.
- `public/offline.html` — a static, self-contained, trilingual (ar/en/tr)
  "you are offline" page with a retry button. It is static because no app
  dictionary exists offline; all three languages are shown.
- Registration via a tiny client component; failure is silent — nothing in
  the app depends on the worker.

Deliberately refused (security/privacy — documented decisions):

- **No API response caching, no page caching**: hotel, guest, finance,
  reservation and permission data never enter any cache, so nothing can be
  served to a different user/tenant and no stale sensitive data can appear
  after a user/hotel switch.
- **No tokens/JWT in the worker or its cache** (sessions stay in HttpOnly
  cookies, untouched).
- **No offline writes of any kind**: no offline booking/check-in/payments/
  invoices/operations, no write queue, no local operational database,
  no background sync. A full offline mode would require an auth-aware,
  tenant-partitioned cache — documented here as out of scope rather than
  half-built unsafely.
- Tenant isolation, route guards, `IsPlatformOwner`, Phase 11 permissions
  and Phase 16 subscription enforcement are untouched (full suite green).

## 5. Performance improvements

Backend (small, contract-preserving, each covered by tests):

- **Public hotel list N+1 removed** (PR #15 review note): the subscription
  answer for up to 60 cards now comes from ONE batch
  (`subscription_blocked_hotel_ids`, two queries total) instead of two
  queries per hotel, and hotel media comes via ONE `prefetch_related`
  instead of one query per card. `booking_open` keeps the identical rule —
  a parity test asserts batch == per-hotel for every subscription
  situation (no history / active / open-ended / trial-ended / expired).
- **Platform hotels list**: `select_related("settings", "status_changed_by")`
  — one JOIN instead of two extra queries per row (PR #15 review note).
- **`HotelSubscription (hotel, status)` index**: the Phase 16 enforcement
  consults this pair on EVERY important write request; the lookup is now
  indexed (migration `subscriptions.0003`).

Frontend:

- Public images stay `loading="lazy"`; skeleton/loading/empty/error states
  were already centralized (LoadingState/ErrorState/EmptyState/Skeleton) —
  no duplication introduced.
- No architecture changes, no new heavy libraries, no API contract changes.

## 6. What was checked

- Backend: `manage.py check`, `makemigrations --check`, `migrate`, and the
  FULL test suite (auth, permissions, reservations, check-in/out, payments,
  services, housekeeping, staff, shifts, reports, notifications, public
  booking, subscription enforcement) + the new batch-parity test.
- Frontend: `lint`, `tsc --noEmit`, production `build`.
- Live: manifest/service worker/offline page served; public + console pages
  render; PWA install criteria present.

## 7. Deferred (documented, needs its own decision/phase)

Full offline mode with tenant-partitioned caches · push notifications ·
background sync · per-page mobile redesigns beyond the central system ·
image CDN/optimization pipeline for user-uploaded hotel media · virtualized
tables for very large datasets.
