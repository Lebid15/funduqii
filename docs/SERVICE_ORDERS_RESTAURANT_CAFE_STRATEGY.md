# Funduqii — Service Orders (Restaurant / Café / Room Service) Strategy

> **Status:** implemented in **Phase 9**. Internal service orders only — an
> order pad for staff whose ONLY financial exit is a folio charge created
> through the Phase 8 finance services.

---

## 1. Why Phase 9 is NOT a full POS

A hotel restaurant needs a simple, reliable way to record what a guest ordered
and put it on their bill. It does **not** need — at this stage — cash drawers,
table maps, kitchen printers, or stock control. Phase 9 deliberately builds the
smallest correct cycle: **catalog → order → prepare → deliver → post to folio**.
Everything else (POS, inventory, tables, public ordering, payments) is deferred
so the money model stays exactly the Phase 8 one: folios are the single bill,
charges are the single financial write, and settlement stays in Finance.

## 2. Data model (apps/services)

- **ServiceCategory** — a catalog section (restaurant / café / room service…),
  hotel-scoped, with an optional per-hotel-unique `code`. A category with items
  cannot be hard-deleted (`409 resource_in_use`) — deactivate it instead.
- **ServiceItem** — a sellable item: category (same hotel enforced), type
  (`restaurant|cafe|room_service|other`), **Decimal** `unit_price` (≥ 0;
  zero-price allowed for complimentary items — a fully-zero order still cannot
  be posted), `tax_rate` %, availability + active flags. Items used on orders
  cannot be hard-deleted — deactivate instead.
- **ServiceOrder** — one order: per-hotel-unique `order_number` (ORD00001…),
  source, optional `stay` / `room` / `folio` links (all tenant-checked; a stay
  implies its room), status, notes, and the posting stamp
  (`posted_charge` OneToOne → finance.FolioCharge, `posted_at`, `posted_by`).
- **ServiceOrderItem** — a line **snapshot**: `item_name`, `unit_price`,
  `tax_rate` are copied at order time, so later catalog edits never rewrite
  history. `amount/tax_amount/total_amount` are computed server-side with the
  same `money()` rounding finance uses.
- **ServiceOrderStatusLog** — a lightweight per-order status history (who,
  from → to, note, when). NOT a general audit log.
- **ServiceNumberSequence** — a per-hotel, row-locked counter mirroring the
  finance sequence but kept separate so non-financial numbering never mixes
  into financial numbering.

## 3. Status workflow

`draft → submitted → preparing → ready → delivered` (forward-only; staff may
skip steps, e.g. submitted → delivered for a café counter). `cancelled` is its
own entry point and **requires a reason**. Rules:

- Items are editable only while **draft**; notes/metadata until delivered.
- `delivered` / `cancelled` / posted orders are frozen (`409 order_not_editable`).
- Every change is written to the status log.
- Orders are never hard-deleted (no DELETE route) — history is preserved.

## 4. Posting to the folio (the only money exit)

`POST /orders/{id}/post-to-folio/` — guarded by `service_orders.post_to_folio`:

1. The order must be **delivered** (`409 order_not_postable` otherwise),
   not cancelled, with a non-zero total, and **never posted before**
   (`409 order_already_posted`; enforced with a row lock so two concurrent
   posts cannot both pass).
2. Folio resolution: the order's own folio if open → else the stay's open
   folio → else a **new folio is created through finance.create_folio** for
   the stay (with its reservation + primary guest). No stay and no folio →
   `409 order_not_postable`.
3. **One FolioCharge** is created via `finance.services.add_charge` with
   `type=service`, `source="service_order"`, description
   `Service order ORD00001`, `unit_amount` = the order's subtotal and the
   order's **exact tax sum passed explicitly** (a small, documented extension
   of `add_charge` — `tax_amount` override — so the charge's
   amount/tax/total equal the order's to the cent even when lines mix tax
   rates; the stored `tax_rate` is the informational effective rate).
4. The order records `posted_charge/posted_at/posted_by`. It can no longer be
   cancelled; **any correction is a finance-side charge void** (Phase 8
   void-with-reason), never an un-post.

No Payment, no Invoice, no Expense is ever created from a service order.

## 5. Permissions & tenancy

- Catalog: `services.view|create|update|delete` · Orders:
  `service_orders.view|create|update|cancel|status_update|post_to_folio` —
  all enforced on the backend per endpoint; managers hold everything by
  default, staff need explicit grants.
- Full tenant isolation: every query is hotel-scoped; stay/room/item/folio
  references are validated against the caller's hotel
  (`404` on foreign lookups, `400 cross_tenant_reference` on mismatches).
- **Suspended hotel = read-only**: every write (create/update/status/cancel/
  post, catalog writes) returns `403 hotel_suspended`.

## 6. API surface (under `/api/v1/hotel/services/`)

`overview/` · `categories/` (+`{id}/`) · `items/` (+`{id}/`) ·
`orders/` (+`{id}/`, `status/`, `cancel/`, `post-to-folio/`, `ticket/`).
Lists are paginated with search/filter/ordering (items: category/type/
availability; orders: status/source/stay/room/date/posted).

## 7. Print ticket

`GET /orders/{id}/ticket/` returns a print-friendly payload (hotel header,
order meta, line snapshots, totals) rendered by the central
`PrintDocumentLayout` inside the shared print modal — direction follows the
locale (`<html dir>`), printing is client-side `window.print()`, no server PDF.

## 8. Frontend

`/hotel/services` with four tabs — **Overview** (workflow cards: today's
orders, kitchen, ready, delivered, delivered-not-posted, posted-today, active
items) · **Catalog** (categories + items CRUD) · **Orders** (create with
stay/walk-in + line editor, details with backend totals + status log, status
buttons, cancel-with-reason, post-to-folio with confirm, printable ticket) ·
**Preparation board** (four status columns with explicit buttons — no
drag/drop; the backend validates every transition). Totals are always the
backend's; the create form shows no client-computed sums. Central components,
design tokens, lucide icons, ar/en/tr with RTL/LTR, unified states, responsive.

## 9. Deferred (deliberately out of scope)

Inventory/stock · purchases & suppliers · table management/reservations ·
advanced kitchen display & printers · full POS/cashier · barcode ·
public/QR ordering · delivery & WhatsApp orders · direct/standalone payment or
gateway · advanced sales reports · shifts/daily close · payroll. These belong
to later phases (or deliberate non-goals) per the blueprint.
