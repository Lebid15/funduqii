# Funduqii — Finance (Folio · Payments · Invoices · Expenses) Strategy

> **Status:** Implemented in **Phase 8 — Payments + Expenses + Folio + Invoices**.
> **Scope:** the hotel's **internal money layer** — a `Folio` per reservation/stay
> that accumulates `FolioCharge`s, `Payment`s recorded against it (receipts), an
> `Invoice` issued from it as an immutable snapshot, and standalone `Expense`
> vouchers. All money is **Decimal**; posted records are **never hard-deleted**
> (void with a reason); every balance is **re-derived** from posted line items.
> **Deliberately NOT in scope:** no real payment gateway (Stripe/PayPal/online
> payment), no bank reconciliation, no government e-invoicing integration, no
> advanced accounting ledger / journal, no payroll, no daily close, no shifts,
> no restaurant POS, no stock, no housekeeping/maintenance workflows, no public
> booking payments, no advanced financial reports. Phase 9 has not started.

---

## 1. App & layering

A single focused app — **`apps/finance`** — sits on top of the earlier phases
(tenancy, reservations, rooms, stays, guests). It is an **internal accounting
layer only**. Every mutation of money goes through **one service module**
(`apps/finance/services.py`); views never write money fields directly. This keeps
numbering, balance math, tax computation, and lifecycle transitions in a single
audited place, and makes the "no external gateway" boundary a property of the
code, not a convention.

## 2. Models (`apps/finance/models.py`)

### `FinancialNumberSequence` (`finance_number_sequences`)
A per-hotel, per-`kind` monotonic counter (`folio` · `receipt` · `invoice` ·
`expense` · `charge`). Unique on `(hotel, kind)`. Numbers are allocated inside a
transaction with `select_for_update` (see §7) so two concurrent allocations for
the same hotel+kind can never collide.

### `Folio` (`folios`)
The financial account of a reservation or stay. Links (all nullable,
`SET_NULL`): `reservation`, `stay`, `guest`; plus a free-text `customer_name`
fallback. `folio_number` is **unique per hotel**. `status` ∈
`open` / `closed` / `voided`. Carries `currency`, `notes`, `opened_at`,
`closed_at`/`closed_by`, and the void triple `void_reason`/`voided_at`/`voided_by`,
plus `created_by`/`updated_by` audit stamps. **No stored balance** — the balance
is always computed (see §6).

### `FolioCharge` (`folio_charges`)
A single amount owed on a folio. `folio` is **`PROTECT`** (a folio with charges
can never be hard-deleted). `charge_number`, `type` (`room`/`service`/`tax`/
`adjustment`/`discount`/`other`), `description`, `quantity`, `unit_amount`,
`amount`, `tax_rate` (percent), `tax_amount`, `total_amount`, `charge_date`,
`source`, and `status` ∈ `posted`/`voided` with the void triple. `discount` and
`adjustment` are the only **credit** types allowed to carry a negative total.

### `Payment` (`payments`)
A **receipt** — money received against a folio. `folio` is **`PROTECT`**.
`receipt_number` is **unique per hotel**. `amount`, `currency`, `method`
(`cash`/`card`/`bank_transfer`/`electronic`/`other`), `status` ∈ `posted`/`voided`,
`paid_at`, `payer_name`, `reference`, `notes`, void triple. **Internal record
only:** `card`/`electronic` here do **not** process a real transaction — no
gateway is ever contacted.

### `Invoice` (`invoices`) + `InvoiceLine` (`invoice_lines`)
An invoice issued from a folio. `folio` is **`PROTECT`**. `status` ∈
`draft`/`issued`/`voided`. A draft has **no number and no lines**; issuing
allocates `invoice_number` (**unique per hotel among non-blank numbers** via a
partial constraint) and freezes `subtotal`, `tax_total`, `total`,
`balance_at_issue`, the customer snapshot, and `issued_at`. Each `InvoiceLine`
is a **frozen copy** of a posted charge at issue time (`description`, `quantity`,
`unit_amount`, `tax_rate`, `tax_amount`, `total_amount`, and a nullable
`source_charge` back-reference that `SET_NULL`s if the charge is ever voided —
the snapshot line survives regardless).

### `Expense` (`expenses`)
A standalone expense / payment voucher (not tied to a folio). `expense_number`
**unique per hotel**, `category` (`operations`/`maintenance`/`supplies`/
`marketing`/`salary`/`utilities`/`other`), `amount`, `currency`, `method`,
`paid_at`, `vendor_name`, `reference`, `notes`, `status` ∈ `posted`/`voided` with
the void triple. Internal record only — **no payroll, no ledger, no bank
reconciliation.**

## 3. Money rules (enforced, not just documented)

- **Decimal only.** `MONEY_KW = dict(max_digits=12, decimal_places=2)`; a single
  `money()` helper quantizes every amount to `0.01` with `ROUND_HALF_UP`. No
  float ever touches a money value.
- **No hard delete of posted records.** Charges, payments, invoices, and
  expenses are **voided** (status → `voided` + `void_reason` + `voided_at` +
  `voided_by`), never deleted. `FolioCharge`/`Payment`/`Invoice` all hold their
  `folio` with `on_delete=PROTECT`, so a folio with history cannot be erased.
- **A void always requires a reason.** An empty/blank reason raises
  `422 void_reason_required`; re-voiding an already-voided record raises
  `409 invalid_finance_operation`.
- **Balances are computed, never trusted.** No `balance` column exists; every
  read re-derives it from **posted** line items (see §6).

## 4. Charges & tax

`compute_charge_totals(quantity, unit_amount, tax_rate, type)`:
`amount = money(quantity × unit_amount)`, `tax_amount = money(amount × rate/100)`,
`total = money(amount + tax_amount)`. Tax is a simple **per-line percentage**
(e.g. `15.00`) held on the charge — deliberately not a tax-engine, tax-group, or
jurisdiction table. Non-credit charges must have a **positive amount**
(`422 invalid_amount`), and no charge may total exactly zero. A charge can only
be added to an **open** folio (`409 folio_closed` otherwise).

## 5. Payments (receipts)

`record_payment` requires an **open** folio and a strictly **positive** amount
(`422 invalid_amount` otherwise), allocates a per-hotel `receipt_number`, and
records the method/`paid_at`/payer. Over-payment is not blocked at the model
level — a folio balance can go negative (a credit owed back to the customer),
which is surfaced in the UI rather than silently prevented. Voiding a payment
removes it from the balance immediately (it is no longer `posted`).

## 6. Balance calculation & folio closing

`folio_balance(folio)` returns
`{total_charges, total_payments, balance}` where
`total_charges = Σ posted charge.total_amount`,
`total_payments = Σ posted payment.amount`, and
`balance = total_charges − total_payments`. **Voided** charges/payments are
excluded, so voiding is the correction mechanism.

**A folio cannot be closed with a non-zero balance** — `close_folio` recomputes
the balance and raises `409 folio_not_balanced` unless it is exactly `0.00`.
Closing stamps `closed_at`/`closed_by`. A folio can also be **voided** (with a
reason) to cancel it entirely. Charges and payments may only be added while the
folio is `open`.

## 7. Invoice snapshot (immutability)

An invoice is created as a **draft** (no number, no lines) and later **issued**:

1. It must be a draft (`409 invalid_finance_operation: not_draft` otherwise).
2. It must have **≥1 posted charge** on its folio (`… : no_charges` otherwise).
3. Each posted charge is copied into an `InvoiceLine` (a frozen snapshot).
4. `subtotal`/`tax_total`/`total` are frozen from those lines and
   `balance_at_issue` from the folio balance at that instant.
5. `invoice_number` is allocated and `status` → `issued`, `issued_at` stamped.

Once issued, the invoice's number, lines, customer, and totals are an
**immutable snapshot** — later charges or payments on the folio, or voiding a
`source_charge`, do **not** alter an issued invoice. Correcting an issued invoice
means **voiding it** (with a reason) and issuing a new one — never editing the
snapshot. This is why `subtotal`/`tax_total`/`total` are stored on the invoice
even though live folio totals are always computed.

## 8. Numbering

`next_number(hotel, kind)` locks the sequence row (`select_for_update`),
increments it, and returns `f"{PREFIX}{n:05d}"` with prefixes
`FOL`/`RCP`/`INV`/`EXP`/`CHG`. Numbers are **per hotel** (two hotels both start at
`00001`) and gap-free within a kind. Because a draft invoice holds no number,
invoice numbers are only spent on **issue**, so the issued sequence has no gaps
from abandoned drafts.

## 9. Early-checkout financial policy (documented decision)

Check-out (Phase 7) remains **operational only** and creates/settles no money.
Phase 8's policy for an early departure is deliberately **manual, not
automatic**:

- Checking out early does **not** auto-refund, auto-void, or auto-recompute any
  charge. Nothing financial happens on check-out.
- If nights already posted should be reduced, a staff member **voids** the
  affected charge (with a reason) or posts an `adjustment`/`discount` credit
  charge, then settles and closes the folio. Every step is an explicit, audited
  action with a `void_reason`/description.
- No automatic penalty or no-show fee is computed — any such fee is entered as a
  normal charge. This keeps the money trail explicit and reversible, matching
  the "no silent money movement" principle. (Revisited in a future
  reservations/finance operations pass if automation is ever wanted.)

## 10. Permissions & tenant isolation

Registry sections (`apps/rbac/registry.py`):
`finance.view/create/update/close/void/charge_create/charge_void/payment_create/
payment_void/invoice_create/invoice_issue/invoice_void` and
`expenses.view/create/update/void`. Every endpoint enforces its matching
permission on the **backend** via `HasHotelPermission`; a manager holds all,
staff need explicit grants. Reads require `finance.view` / `expenses.view`.
A user of hotel A can never see or touch hotel B's finance data (all querysets
are hotel-scoped via the `X-Hotel-ID` context); a platform owner is not a hotel
member unless explicitly added; unauthenticated is rejected. A **suspended
hotel is read-only** — every write (create/charge/payment/close/void/issue/
expense) returns `403 hotel_suspended`, while reads still work.

At most **one open folio per stay** is allowed — a second open-folio attempt for
the same stay returns `409 invalid_finance_operation: open_folio_exists_for_stay`.

## 11. API surface (`/api/v1/hotel/finance/`)

| Method | Path | Permission |
|---|---|---|
| GET | `overview/` | finance.view |
| GET / POST | `folios/` | finance.view / finance.create |
| GET / PATCH | `folios/{id}/` (PATCH = notes only) | finance.view / finance.update |
| POST | `folios/{id}/close/` | finance.close |
| POST | `folios/{id}/void/` | finance.void |
| POST | `folios/{id}/charges/` | finance.charge_create |
| POST | `folios/{id}/payments/` | finance.payment_create |
| POST | `folios/{id}/invoices/` | finance.invoice_create |
| POST | `charges/{id}/void/` | finance.charge_void |
| GET | `payments/` | finance.view |
| POST | `payments/{id}/void/` | finance.payment_void |
| GET | `payments/{id}/receipt/` | finance.view |
| GET | `invoices/` | finance.view |
| GET | `invoices/{id}/` | finance.view |
| POST | `invoices/{id}/issue/` | finance.invoice_issue |
| POST | `invoices/{id}/void/` | finance.invoice_void |
| GET | `invoices/{id}/print/` | finance.view |
| GET / POST | `expenses/` | expenses.view / expenses.create |
| GET / PATCH | `expenses/{id}/` (PATCH only while posted) | expenses.view / expenses.update |
| POST | `expenses/{id}/void/` | expenses.void |
| GET | `expenses/{id}/voucher/` | expenses.view |

New error codes: `folio_closed` (409), `folio_not_balanced` (409),
`void_reason_required` (422), `invalid_finance_operation` (409),
`invalid_amount` (422). All flow through the unified error envelope
(`apps/common/exceptions.py`).

The `receipt`, `print` (invoice), and `voucher` (expense) endpoints return a
print-friendly document payload (`{document, hotel:{name,currency,phone,address},
…}`) that the frontend renders and prints — **no PDF/server rendering**, no
external service.

## 12. Frontend (`/hotel/finance`)

One sidebar entry — **Finance** — opens a tabbed console
(`components/hotel/finance/`):

- **Overview** — stat cards: open folios, outstanding balance, payments today,
  expenses today, net today, issued invoices.
- **Folios** — list + create; a detail modal shows charges/payments and the
  live balance, with add-charge / record-payment / create-invoice (create +
  issue) / close / void actions and a printable receipt.
- **Payments** — all receipts with void and printable receipt.
- **Invoices** — draft/issued/voided list with issue / void / printable invoice.
- **Expenses** — list + create + void with a printable voucher.

Printing is done client-side via `window.print()` against a print-only document
(`@media print` in `globals.css`), so a receipt/invoice/voucher prints cleanly
without any backend rendering. Money is formatted with `Intl.NumberFormat`
(currency) in `lib/format.ts`. The console uses the central design system, the
single lucide icon set, unified loading/empty/error/success states, real
responsiveness, and full **ar/en/tr** with automatic RTL/LTR. No hardcoded text;
no token/JWT in `localStorage` (auth stays in HttpOnly cookies via the BFF).

## 13. Deferred to later phases

- **Real payment processing** — Stripe/PayPal, online/hosted payment pages, card
  tokenization, 3-D Secure, refunds through a gateway. (Never in this internal
  layer.)
- **Bank reconciliation, e-invoicing / government tax integration, an advanced
  double-entry accounting ledger, payroll.**
- **Daily close & shifts** (Phase 11), **restaurant/cafeteria POS charges**
  (Phase 9), **stock/inventory**, full **housekeeping/maintenance** workflows
  (Phase 10), **public booking payments** (Phase 12), and **advanced financial
  reports** (Phase 13).
- **Multi-currency conversion** (each record stores its own currency; no FX
  conversion is performed), **partial-payment plans/schedules**, and
  **automatic early-checkout proration** (kept manual — see §9).
- A broader PostgreSQL + large-dataset performance/concurrency pass is planned
  before production.

## 14. Phase 8.1 patch (current-scope real-hotel alignment)

- **Invoice snapshot additions** (migration `finance.0002`): `customer_email`
  and `customer_document_number`, filled from the folio's guest at issue time
  like the existing `customer_name`/`customer_phone` — simple, safe snapshots.
- **Reservation reference on prints** is a **safe relation read**
  (`folio.reservation.reservation_number`, exposed by the serializers) —
  reservation numbers never change, so no snapshot is stored. Stay dates and
  room numbers are deliberately **not** stored on the invoice (not
  simple/safe to freeze; may come in a later phase).
- **Richer print layouts** via the central `PrintDocumentLayout`: invoice
  (hotel header, customer contact/document, folio & reservation reference,
  lines, subtotal/tax/total/balance-at-issue, notes), receipt (payer, amount,
  method, reference, received-by, signature) and expense voucher (vendor,
  category, description, created-by, signature).
- **Mixed payments**: still **no payment-split model** — multiple `Payment`s
  on one folio remain the mechanism; the payment form now shows a hint and a
  "Save & add another payment" action.

See `docs/REAL_HOTEL_CURRENT_SCOPE_ALIGNMENT.md`.
