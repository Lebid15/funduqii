# Funduqii — Real Hotel Current Scope Alignment (Phase 8.1)

> **Status:** Implemented as **Phase 8.1 — Current Scope Real Hotel Data & UX
> Patch**, inside the Phase 8 PR (#7), before Phase 8 approval.
> **Nature:** a correction/polish patch of what exists up to Phase 8 — not a
> full project comparison, not Phase 9, not a rebuild, not a copy of the legacy
> project.

---

## 1. Scope of this comparison

The comparison against real-hotel needs and the legacy project's requirements
is **limited strictly to what has been built up to Phase 8**: reservations,
guests, front desk (check-in/check-out), finance (folio, payments, invoices,
expenses), print views, and the central card/UX layer. Nothing beyond that
scope was compared, designed, or implemented.

## 2. Exactly two booking kinds

The system supports **exactly two** booking kinds, stored on
`Reservation.booking_kind`:

- **`instant`** — the guest is present now or wants to enter immediately; the
  check-in date is forced to **today** (the serializer rejects an instant
  booking with a future check-in date).
- **`future`** — the booking is for a later date.

When a client omits `booking_kind`, the backend derives it from the check-in
date (`today or earlier → instant`, otherwise `future`), so existing clients
keep working.

## 3. No quick/full booking

There is **no** quick booking / full booking, **no** basic mode / advanced
mode, and no other confusing booking split. One `Reservation` model, one form,
two kinds. This is enforced in code comments on the model and by the single
`ReservationModal` component.

## 4. Ease of use comes from organizing the UI, not multiplying forms

Usability is achieved by structuring the **single** reservation form into five
clear sections (kind & dates → guest basics → rooms & availability → source &
notes → review & save) using central `SectionCard` / `StepSummaryCard`
components — never by creating multiple booking forms or modes.

## 5. What was added / confirmed in Reservations

- **New fields** on `Reservation` (migration `reservations.0003`):
  `booking_kind`, `expected_arrival_time`, `primary_guest_nationality`,
  `primary_guest_document_type`, `primary_guest_document_number`,
  `booking_channel_name`, `expected_payment_method` (informational only — not a
  real payment), `no_show_reason`.
- **Confirmed existing:** `special_requests`, `notes` (used as the internal
  notes field and labelled "Internal notes" in the UI), `cancellation_reason`
  (required on cancel), `source`, `hold_expires_at`.
- **Form** reorganized into the five sections above, with live availability
  and per-line conflict messages re-checked by the backend before saving.
- **Details view** now shows booking kind, arrival time, channel, expected
  payment method, nationality/document, and no-show/cancellation reasons.

## 6. What was added / confirmed in the Front Desk

- **Guest model confirmed** to carry `full_name`, `phone`, `email`,
  `nationality`, `document_type`, `document_number`, `date_of_birth`,
  `address`, `notes` — no document uploads, no base64.
- `/hotel/front-desk` gained a **workflow card row** (central `WorkflowCard`):
  arrivals today, current residents, departures today, check-in, check-out —
  each with an icon, title, live count, short description and a clear action.
- Arrival/departure rows use the central `ActionCard`.
- **Check-in UX** kept its logic (no payment, no invoice) — reservation
  confirmation, room confirmation, guest select/quick-create, companions, one
  clear submit button.
- **Check-out dialog** now shows guest name, room number, actual check-in
  date, expected check-out date, a clear notice that **financial settlement is
  handled in the Finance section**, and a confirm button. No payment inside
  check-out.

## 7. What was added / confirmed in Finance & printing

- **Invoice print** (central `PrintDocumentLayout`): hotel header (name,
  address, phone from hotel settings), `invoice_number`, `issued_at`,
  `customer_name`, `customer_phone`, `customer_email`,
  `customer_document_number`, `folio_number`, reservation reference, lines,
  `subtotal`, `tax_total`, `total`, `balance_at_issue`, `notes`.
  - `customer_email` and `customer_document_number` were added as **simple,
    safe snapshot fields** on `Invoice` (filled from the folio's guest at
    issue time, like the existing `customer_name`/`customer_phone`).
  - The **reservation reference** is a **safe relation read**
    (`folio.reservation.reservation_number`) exposed by the serializer for
    printing — reservation numbers never change, so no snapshot is needed.
  - **Stay dates and room numbers are not stored on the invoice** — they are
    deliberately left out of the snapshot (not simple/safe to freeze) and can
    be added in a later phase if needed.
- **Receipt print**: hotel header, `receipt_number`, `paid_at`, `payer_name`,
  amount + currency, method, reference, `folio_number`, reservation reference,
  received-by (`created_by`), notes, and a signature area.
- **Expense voucher print**: hotel header, `expense_number`, `paid_at`,
  `vendor_name`, category, amount + currency, method, reference, description,
  created-by, notes, and a signature area.
- **Mixed payment UX**: **no payment-split model was built.** Multiple
  `Payment`s on the same folio remain the mechanism; the payment form shows the
  hint *"To pay with more than one method, record multiple payments"* and a
  *"Save & add another payment"* action.

## 8. Deferred to later phases (documented only — NOT implemented)

- Public website.
- Public booking.
- Restaurant / POS.
- Housekeeping.
- Maintenance.
- Lost & found.
- Shifts.
- Daily close.
- Reports (advanced).
- Notifications.
- WhatsApp integration.
- Maps integration.
- Platform commission.
- Subscription gating enhancements.

None of these were started in Phase 8.1.

## 9. Why we do not copy the legacy project

The legacy project mixes UI, business rules and storage; it carries patterns
this project explicitly forbids (localStorage as a source of truth, base64
media, hardcoded text, ad-hoc CSS, floating-point money). Copying its code
would import those defects and break the architectural guarantees built in
Phases 1–8 (tenancy isolation, RBAC on every endpoint, Decimal-only money,
void-instead-of-delete, availability decided only by the backend).

## 10. The legacy project is a requirements source only

The old project is used **only** to learn what a real hotel needs — which
fields, flows and documents matter in daily operation (see
`docs/LEGACY_REFERENCE_INSIGHTS.md`). Every feature is re-designed and
re-implemented inside this codebase's architecture, standards and central
design system; no legacy code, markup or styles are transplanted.
