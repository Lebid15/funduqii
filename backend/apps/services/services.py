"""Service-order domain services (Phase 9 + restaurant/café final closure) —
the single write path.

Views never mutate orders or tables directly. Money math reuses the finance
``money()`` rounding so an order's totals and its financial documents always
agree to the cent. The financial exits are exactly TWO and mutually exclusive
(XOR, enforced here and by a DB check constraint):

- ``post_order_to_folio`` — one FolioCharge on the IN-HOUSE stay's folio,
  once, ever (through ``apps.finance.services``).
- ``settle_order_direct`` — the transient-folio cycle: create folio, post one
  charge, record the full payment (it joins the actor's open shift drawer),
  close the folio at zero — all in ONE transaction. The closed transient
  folio is final (PR #29 rules are absolute); later corrections belong to
  the Finance section, never to this module.

Operational status (draft → … → delivered) is deliberately SEPARATE from the
settlement state: "delivered" is not "paid".
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.common.exceptions import (
    CancellationReasonRequired,
    CrossTenantReference,
    FolioClosed,
    FolioCurrencyMismatch,
    IdempotencyKeyConflict,
    InsufficientCashReceived,
    InvalidAmount,
    InvalidOrderComposition,
    InvalidOrderStatusTransition,
    InvalidReturnComposition,
    LastActiveItemNotCancellable,
    OrderAlreadyPosted,
    OrderAlreadySettled,
    OrderItemsRequired,
    OrderNotEditable,
    OrderNotPostable,
    OrderNotReturnable,
    OutletDisabled,
    OutletMismatch,
    ReturnReasonRequired,
    ServiceCurrencyMismatch,
    ServiceItemUnavailable,
    StatusNoteRequired,
    StayNotInHouse,
    TableHasOpenOrder,
    TableOccupied,
    TableOutOfService,
)
from apps.finance import services as finance_services
from apps.finance.constants import ChargeSource
from apps.finance.models import ChargeType, Folio, FolioStatus, PaymentMethod
from apps.finance.services import money

from .models import (
    OrderSettlement,
    OrderStatus,
    OrderType,
    Outlet,
    RestaurantTable,
    ReturnKind,
    ServiceItem,
    ServiceNumberSequence,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderReturn,
    ServiceOrderReturnItem,
    ServiceOrderStatusLog,
    TableStatus,
)

#: The free-text ``FolioCharge.source`` markers for money that a return/exchange
#: moves. NOT bound to ``finance.constants.ChargeSource`` (finance is untouched);
#: the source column already accepts free text. Deliberately OUTSIDE
#: ``SERVICE_LINE_SOURCES`` so a return never inflates a stay's service-line sums.
RETURN_CHARGE_SOURCE = "order_return"
EXCHANGE_CHARGE_SOURCE = "order_exchange"

#: The three exchange kinds (a replacement leg + a net delta).
EXCHANGE_KINDS = frozenset(
    {ReturnKind.EXCHANGE_SAME, ReturnKind.EXCHANGE_HIGHER, ReturnKind.EXCHANGE_LOWER}
)

ZERO = Decimal("0.00")

#: Forward-only workflow. Staff may skip steps (e.g. a café order can go
#: submitted → delivered directly); cancellation has its own entry point.
ALLOWED_TRANSITIONS = {
    OrderStatus.DRAFT: {OrderStatus.SUBMITTED},
    OrderStatus.SUBMITTED: {OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.DELIVERED},
    OrderStatus.READY: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}

#: Statuses whose items may still be replaced (only a draft is re-editable).
ITEM_EDITABLE_STATUSES = {OrderStatus.DRAFT}
#: Statuses whose notes/metadata may still be edited.
META_EDITABLE_STATUSES = {
    OrderStatus.DRAFT,
    OrderStatus.SUBMITTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
}


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def next_order_number(hotel) -> str:
    """Allocate the next per-hotel ORD number (row-locked; needs a txn)."""
    seq, _ = ServiceNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel, kind="order"
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"ORD{seq.last_number:05d}"


def next_return_number(hotel) -> str:
    """Allocate the next per-hotel RET number (row-locked; needs a txn). Uses a
    NEW ``ServiceNumberSequence`` kind ``"return"`` — separate from order/other
    numbering, so returns never mix into the order sequence."""
    seq, _ = ServiceNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel, kind="return"
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"RET{seq.last_number:05d}"


def _base_currency(hotel) -> str:
    """The hotel BASE currency (D1a) — the single currency of every service order.
    Mirrors finance's default-currency resolution (``default_currency`` or USD),
    upper-cased for a safe comparison."""
    settings_obj = getattr(hotel, "settings", None)
    cur = (getattr(settings_obj, "default_currency", "") or "").strip().upper()
    return cur or "USD"


def _business_date(hotel):
    # Daily-close serialization: read the operational date UNDER a HotelSettings
    # row lock (callers run inside a transaction) so an order posting/settlement
    # and the daily close never straddle a business-date roll.
    from apps.shifts.services import lock_business_date

    return lock_business_date(hotel)


def outlet_enabled(hotel, outlet: str) -> bool:
    settings_obj = getattr(hotel, "settings", None)
    if settings_obj is None:
        return True
    if outlet == Outlet.CAFE:
        return bool(getattr(settings_obj, "cafe_enabled", True))
    return bool(getattr(settings_obj, "restaurant_enabled", True))


def _ensure_outlet_enabled(hotel, outlet: str) -> None:
    """Disabled outlet = no NEW orders/tables/catalog rows (existing data
    stays readable and reportable — nothing is deactivated retroactively)."""
    if not outlet_enabled(hotel, outlet):
        raise OutletDisabled({"outlet": outlet})


def compute_item_totals(quantity, unit_price, tax_rate):
    """Per-line money math (same rounding as finance charges)."""
    quantity = Decimal(quantity)
    unit_price = money(unit_price)
    if quantity <= ZERO:
        raise InvalidAmount({"field": "quantity", "reason": "must_be_positive"})
    if unit_price < ZERO:
        raise InvalidAmount({"field": "unit_price", "reason": "must_not_be_negative"})
    amount = money(quantity * unit_price)
    tax_amount = money(amount * Decimal(tax_rate) / Decimal("100"))
    total = money(amount + tax_amount)
    return amount, tax_amount, total


def order_totals(order: ServiceOrder) -> dict:
    """Re-derive an order's totals from its ACTIVE line snapshots (cancelled
    lines keep their snapshot but never count)."""
    lines = [l for l in order.items.all() if l.cancelled_at is None]
    subtotal = money(sum((l.amount for l in lines), ZERO))
    tax_total = money(sum((l.tax_amount for l in lines), ZERO))
    total = money(sum((l.total_amount for l in lines), ZERO))
    return {"subtotal": subtotal, "tax_total": tax_total, "total": total}


def _log(order, previous, new, user, note=""):
    ServiceOrderStatusLog.objects.create(
        hotel=order.hotel,
        order=order,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


def _record(hotel, *, event_type, severity, title, message="", user=None, obj=None):
    # Phase 14 activity system (lazy import keeps app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type=event_type,
        category="service",
        severity=severity,
        title=title,
        message=message,
        actor=user,
        related_object=obj,
        related_url="/hotel/services",
    )


def _build_items(order: ServiceOrder, items_data: list) -> None:
    """Snapshot catalog items onto the order (name/price/tax/currency frozen).
    Every item must belong to the ORDER's outlet (via its category) and share the
    hotel BASE currency (D1a)."""
    if not items_data:
        raise OrderItemsRequired()
    base = _base_currency(order.hotel)
    for entry in items_data:
        item: ServiceItem = entry["service_item"]
        if item.hotel_id != order.hotel_id:
            raise CrossTenantReference({"field": "service_item"})
        if item.category.outlet != order.outlet:
            raise OutletMismatch({"item": item.id, "outlet": order.outlet})
        if not (item.is_active and item.is_available):
            raise ServiceItemUnavailable({"item": item.id, "name": item.name})
        # D1a — activate the previously-dead ``ServiceItem.currency``: an item
        # explicitly saved in a NON-base currency is refused (no FX); an EMPTY
        # currency is treated as "unset" and normalized to the base, which is
        # snapshotted onto the frozen line.
        item_cur = (item.currency or "").strip().upper()
        if item_cur and item_cur != base:
            raise ServiceCurrencyMismatch(
                {"item": item.id, "item_currency": item_cur, "base_currency": base}
            )
        amount, tax_amount, total = compute_item_totals(
            entry["quantity"], item.unit_price, item.tax_rate
        )
        ServiceOrderItem.objects.create(
            hotel=order.hotel,
            order=order,
            service_item=item,
            item_name=item.name,
            quantity=money(entry["quantity"]),
            unit_price=money(item.unit_price),
            currency=base,
            tax_rate=Decimal(item.tax_rate),
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total,
            notes=entry.get("notes", "") or "",
        )


def _require_stay_in_house(hotel, stay, *, lock: bool):
    """The P0 guard: new operational-financial relations need an IN-HOUSE
    stay. ``lock=True`` re-reads under a row lock (settlement-time check)."""
    from apps.stays.models import Stay, StayStatus

    if stay.hotel_id != hotel.id:
        raise CrossTenantReference({"field": "stay"})
    if lock:
        stay = Stay.objects.select_for_update().get(pk=stay.pk)
    if stay.status != StayStatus.IN_HOUSE:
        raise StayNotInHouse({"stay": stay.pk, "status": stay.status})
    return stay


def _table_has_open_order(table: RestaurantTable) -> bool:
    return (
        ServiceOrder.objects.filter(table=table, settled_at__isnull=True)
        .exclude(status=OrderStatus.CANCELLED)
        .exists()
    )


# --- Orders -------------------------------------------------------------------


@transaction.atomic
def create_order(hotel, *, user=None, order_type, outlet, stay=None, table=None,
                 customer_name="", status=OrderStatus.SUBMITTED,
                 requested_delivery_time=None, notes="", internal_notes="",
                 items_data) -> ServiceOrder:
    """Open an order of one of the two fixed shapes. ``order_type``/``outlet``
    /``table``/``stay`` are IMMUTABLE afterwards; the business date is stamped
    from the hotel — the caller never chooses it."""
    _ensure_outlet_enabled(hotel, outlet)
    room = None
    if order_type == OrderType.ROOM:
        if table is not None:
            raise InvalidOrderComposition({"reason": "table_not_allowed"})
        if stay is None:
            raise InvalidOrderComposition({"reason": "stay_required"})
        stay = _require_stay_in_house(hotel, stay, lock=False)
        room = stay.room
    elif order_type == OrderType.TABLE:
        if table is None:
            raise InvalidOrderComposition({"reason": "table_required"})
        # Row lock: two concurrent orders for the same table serialize here;
        # the partial unique constraint is the DB backstop.
        table = RestaurantTable.objects.select_for_update().get(pk=table.pk)
        if table.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "table"})
        if table.outlet != outlet:
            raise InvalidOrderComposition({"reason": "table_outlet_mismatch"})
        if table.status == TableStatus.OUT_OF_SERVICE:
            raise TableOutOfService({"table": table.id})
        if _table_has_open_order(table):
            raise TableOccupied({"table": table.id})
        if stay is not None:
            stay = _require_stay_in_house(hotel, stay, lock=False)
            room = stay.room
    elif order_type == OrderType.DIRECT:
        # A walk-in DIRECT customer: no table, no stay, no room. It settles by
        # direct payment only — folio posting requires a stay, so it is naturally
        # barred from ever posting to a folio.
        if table is not None:
            raise InvalidOrderComposition({"reason": "table_not_allowed"})
        if stay is not None:
            raise InvalidOrderComposition({"reason": "stay_not_allowed"})
    else:
        raise InvalidOrderComposition({"reason": "unknown_order_type"})

    actor = _actor(user)
    try:
        order = ServiceOrder.objects.create(
            hotel=hotel,
            order_number=next_order_number(hotel),
            # Legacy column kept coherent for old readers only (deprecated).
            source="room_service" if order_type == OrderType.ROOM else outlet,
            order_type=order_type,
            outlet=outlet,
            # D1a — the order's single settlement currency = the hotel base.
            currency=_base_currency(hotel),
            table=table,
            customer_name=(customer_name or "").strip(),
            business_date=_business_date(hotel),
            stay=stay,
            room=room,
            status=status,
            ordered_at=timezone.now(),
            requested_delivery_time=requested_delivery_time,
            notes=notes or "",
            internal_notes=internal_notes or "",
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError:
        # Lost the table race despite the lock (or a stale check) — the
        # partial unique constraint speaks.
        raise TableOccupied({"table": table.pk if table else None})
    _build_items(order, items_data)
    _log(order, "", order.status, user)
    where = (
        f"room {room.number}" if (room and order_type == OrderType.ROOM)
        else f"table {table.number}" if table
        else f"direct: {order.customer_name}" if order_type == OrderType.DIRECT and order.customer_name
        else "direct customer" if order_type == OrderType.DIRECT
        else "—"
    )
    _record(
        hotel,
        event_type="service_order.created",
        severity="info",
        title=f"Order {order.order_number} created",
        message=f"{order.outlet} · {order.order_type} · {where}",
        user=user,
        obj=order,
    )
    return order


@transaction.atomic
def update_order(order: ServiceOrder, *, user=None, items_data=None, **meta) -> ServiceOrder:
    """Edit an order. Items only while draft; notes/time until delivered.
    The shape (type/outlet/table/stay) and the legacy ``source`` are never
    editable."""
    if order.is_posted or order.settlement != OrderSettlement.UNSETTLED:
        raise OrderNotEditable({"status": order.status, "settlement": order.settlement})
    if order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        raise OrderNotEditable({"status": order.status, "posted": order.is_posted})
    if items_data is not None:
        if order.status not in ITEM_EDITABLE_STATUSES:
            raise OrderNotEditable({"status": order.status, "reason": "items_locked"})
        order.items.all().delete()
        _build_items(order, items_data)
        _record(
            order.hotel,
            event_type="service_order.items_updated",
            severity="info",
            title=f"Order {order.order_number} items updated",
            message=f"{order.items.count()} items",
            user=user,
            obj=order,
        )
    if order.status not in META_EDITABLE_STATUSES:
        raise OrderNotEditable({"status": order.status})
    for field in ("notes", "internal_notes", "requested_delivery_time"):
        if field in meta:
            setattr(order, field, meta[field])
    order.updated_by = _actor(user)
    order.save()
    return order


@transaction.atomic
def change_status(order: ServiceOrder, *, new_status, user=None, note="") -> ServiceOrder:
    if new_status == OrderStatus.CANCELLED:
        # Cancellation has its own entry point (a reason is mandatory).
        raise InvalidOrderStatusTransition({"reason": "use_cancel_endpoint"})
    if new_status not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise InvalidOrderStatusTransition(
            {"from": order.status, "to": new_status}
        )
    if new_status != OrderStatus.DRAFT and not order.items.exists():
        raise OrderItemsRequired()
    previous = order.status
    order.status = new_status
    if new_status == OrderStatus.DELIVERED:
        order.delivered_at = timezone.now()
    order.updated_by = _actor(user)
    order.save(update_fields=["status", "delivered_at", "updated_by", "updated_at"])
    _log(order, previous, new_status, user, note)
    _record(
        order.hotel,
        event_type="service_order.status_changed",
        severity="info",
        title=f"Order {order.order_number}: {previous} → {new_status}",
        message=note or "",
        user=user,
        obj=order,
    )
    return order


@transaction.atomic
def cancel_order(order: ServiceOrder, *, reason, user=None) -> ServiceOrder:
    """Cancel an UNSETTLED order (reason mandatory, terminal). Cancelling
    derives the table free again. A settled order is never cancelled here —
    corrections are finance-side only."""
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    if order.is_posted or order.settlement != OrderSettlement.UNSETTLED:
        # A settled order's money already lives in finance; corrections are
        # finance-side — never a service-side cancellation.
        raise OrderNotEditable({"reason": "settled", "settlement": order.settlement})
    if order.status == OrderStatus.DELIVERED:
        # C3 (owner decision) — cancellation is a PRE-DELIVERY action only. A
        # delivered order is never cancelled, even when still unsettled; any
        # correction after delivery goes through settle + RETURN, never a cancel.
        raise OrderNotEditable({"reason": "already_delivered", "status": order.status})
    if order.status == OrderStatus.CANCELLED:
        raise OrderNotEditable({"reason": "already_cancelled"})
    previous = order.status
    order.status = OrderStatus.CANCELLED
    order.cancellation_reason = reason.strip()
    order.cancelled_at = timezone.now()
    order.cancelled_by = _actor(user)
    order.updated_by = _actor(user)
    order.save()
    _log(order, previous, OrderStatus.CANCELLED, user, reason.strip())
    _record(
        order.hotel,
        event_type="service_order.cancelled",
        severity="warning",
        title=f"Order {order.order_number} cancelled",
        message=reason.strip(),
        user=user,
        obj=order,
    )
    return order


@transaction.atomic
def cancel_order_item(item: ServiceOrderItem, *, reason, user=None) -> ServiceOrderItem:
    """Cancel ONE whole line before settlement: the row is never deleted, the
    snapshot stays, totals exclude it. No partial-quantity cancellation."""
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    order = ServiceOrder.objects.select_for_update().get(pk=item.order_id)
    if order.is_posted or order.settlement != OrderSettlement.UNSETTLED:
        raise OrderAlreadySettled({"order": order.id})
    if order.status == OrderStatus.DELIVERED:
        # C3 (owner decision) — no line cancellation after delivery either; the
        # sanctioned post-delivery correction is a RETURN, not a cancel.
        raise OrderNotEditable({"reason": "already_delivered", "status": order.status})
    if order.status == OrderStatus.CANCELLED:
        raise OrderNotEditable({"reason": "already_cancelled"})
    item = ServiceOrderItem.objects.select_for_update().get(pk=item.pk)
    if item.cancelled_at is not None:
        raise OrderNotEditable({"reason": "item_already_cancelled"})
    active = order.items.filter(cancelled_at__isnull=True).exclude(pk=item.pk).count()
    if active == 0:
        raise LastActiveItemNotCancellable({"order": order.id})
    item.cancelled_at = timezone.now()
    item.cancelled_by = _actor(user)
    item.cancel_reason = reason.strip()
    item.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason", "updated_at"])
    _record(
        order.hotel,
        event_type="service_order.item_cancelled",
        severity="warning",
        title=f"Order {order.order_number}: item cancelled",
        message=f"{item.item_name} ×{item.quantity} · {reason.strip()}",
        user=user,
        obj=order,
    )
    return item


# --- Tables ---------------------------------------------------------------------


@transaction.atomic
def create_table(hotel, *, outlet, number, name="", capacity=2, user=None) -> RestaurantTable:
    _ensure_outlet_enabled(hotel, outlet)
    actor = _actor(user)
    try:
        return RestaurantTable.objects.create(
            hotel=hotel,
            outlet=outlet,
            number=(number or "").strip(),
            name=(name or "").strip(),
            capacity=capacity,
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError:
        raise InvalidOrderComposition({"reason": "duplicate_table_number"})


@transaction.atomic
def update_table(table: RestaurantTable, *, user=None, **fields) -> RestaurantTable:
    """Edit number/name/capacity. The outlet is IMMUTABLE; status changes go
    through ``set_table_status``."""
    editable = ("number", "name", "capacity")
    for field in fields:
        if field not in editable:
            raise InvalidOrderComposition({"reason": "field_not_editable", "field": field})
    for field, value in fields.items():
        setattr(table, field, value.strip() if isinstance(value, str) else value)
    table.updated_by = _actor(user)
    try:
        table.save()
    except IntegrityError:
        raise InvalidOrderComposition({"reason": "duplicate_table_number"})
    return table


@transaction.atomic
def set_table_status(table: RestaurantTable, *, status, note="", user=None) -> RestaurantTable:
    """Available ⇄ out-of-service (manual states only — ``occupied`` is always
    derived). Leaving service needs a reason and refuses an open order."""
    table = RestaurantTable.objects.select_for_update().get(pk=table.pk)
    if status == table.status and (note or "") == table.status_note:
        return table
    if status == TableStatus.OUT_OF_SERVICE:
        if not (note or "").strip():
            raise StatusNoteRequired({"status": status})
        if _table_has_open_order(table):
            raise TableHasOpenOrder({"table": table.id})
    table.status = status
    table.status_note = (note or "").strip()
    table.updated_by = _actor(user)
    table.save(update_fields=["status", "status_note", "updated_by", "updated_at"])
    _record(
        table.hotel,
        event_type=(
            "table.out_of_service"
            if status == TableStatus.OUT_OF_SERVICE
            else "table.back_in_service"
        ),
        severity="warning" if status == TableStatus.OUT_OF_SERVICE else "info",
        title=f"Table {table.number} ({table.outlet}): {status}",
        message=table.status_note,
        user=user,
        obj=table,
    )
    return table


# --- Idempotency (D5) -------------------------------------------------------------


def build_settlement_fingerprint(*, order_id, method, amount_received=None,
                                 reference="") -> str:
    """A stable sha256 hex over ONLY the salient DIRECT-settlement request fields
    (D5) — order, method, the tendered amount (normalized), and the electronic
    reference. It EXCLUDES every server-derived value (the total, change, receipt
    number, timestamps), so an identical request always yields the same
    fingerprint and a materially different one differs."""
    payload = {
        "order": order_id,
        "method": (method or ""),
        "amount_received": (
            str(money(amount_received)) if amount_received is not None else None
        ),
        "reference": (reference or "").strip(),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_folio_post_fingerprint(*, order_id) -> str:
    """A stable sha256 for the folio-post settlement (D5). The only salient field
    is the order identity — the folio and the amount are fully server-derived."""
    canonical = json.dumps(
        {"order": order_id, "settlement": "folio"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_return_fingerprint(*, order_id, kind, items, reason) -> str:
    """A stable sha256 over the salient return/exchange request fields (D5):
    order, kind, reason (trimmed + case-folded), and the sorted set of returned
    lines ``(original_item, quantity, replacement_item, replacement_quantity)``.
    ``items`` carries raw client ids (the view builds the fingerprint BEFORE
    resolving instances), matching the guest_services pattern."""
    lines = sorted(
        (
            int(e["original_item"]),
            str(money(e["quantity"])),
            (int(e["replacement_item"]) if e.get("replacement_item") else None),
            (
                str(money(e["replacement_quantity"]))
                if e.get("replacement_quantity") is not None
                else None
            ),
        )
        for e in items
    )
    payload = {
        "order": order_id,
        "kind": (kind or ""),
        "reason": (reason or "").strip().casefold(),
        "lines": lines,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_same_settlement(order: ServiceOrder, fingerprint: str) -> None:
    """Reject a replayed settlement key whose fingerprint differs from the stored
    one (a stored/incoming empty fingerprint is treated as unknown and never
    conflicts — the reservations/guest_services idempotency rule)."""
    stored = order.settlement_fingerprint or ""
    if stored and fingerprint and stored != fingerprint:
        raise IdempotencyKeyConflict()


def _assert_same_return(ret: ServiceOrderReturn, fingerprint: str) -> None:
    stored = ret.request_fingerprint or ""
    if stored and fingerprint and stored != fingerprint:
        raise IdempotencyKeyConflict()


# --- Settlement (XOR) -------------------------------------------------------------


def _require_settleable(order: ServiceOrder) -> dict:
    """Common settlement guards under the caller's row lock. Returns totals."""
    if order.settlement != OrderSettlement.UNSETTLED:
        if order.settlement == OrderSettlement.FOLIO or order.is_posted:
            raise OrderAlreadyPosted({"order": order.id})
        raise OrderAlreadySettled({"order": order.id})
    if order.status == OrderStatus.CANCELLED:
        raise OrderNotPostable({"reason": "cancelled"})
    if order.status != OrderStatus.DELIVERED:
        raise OrderNotPostable({"reason": "not_delivered", "status": order.status})
    totals = order_totals(order)
    if totals["total"] <= ZERO:
        raise OrderNotPostable({"reason": "zero_total"})
    return totals


def _effective_rate(totals) -> Decimal:
    # Informational effective rate; the exact tax sum is passed explicitly so
    # the charge's amount/tax/total equal the order's to the cent.
    return (
        money(totals["tax_total"] / totals["subtotal"] * Decimal("100"))
        if totals["subtotal"] > ZERO
        else ZERO
    )


def _resolve_folio(order: ServiceOrder, *, user=None) -> Folio:
    """The folio the order posts to: its own, or the stay's ONE open folio
    through the central get-or-create."""
    if order.folio is not None:
        if order.folio.hotel_id != order.hotel_id:
            raise CrossTenantReference({"field": "folio"})
        return order.folio
    if order.stay is not None:
        # Folio closure round: the ONE central get-or-create (stay row lock +
        # unique-open-folio constraint) — no local duplicate-folio logic.
        return finance_services.ensure_stay_folio(order.stay, user=user)
    raise OrderNotPostable({"reason": "no_folio"})


@transaction.atomic
def post_order_to_folio(order: ServiceOrder, *, user=None, settlement_key="",
                        settlement_fingerprint="") -> ServiceOrder:
    """Post a delivered order to the IN-HOUSE stay's folio as ONE finance
    charge, exactly once (XOR with direct payment). Idempotent (D5) on a
    non-blank ``settlement_key``."""
    key = (settlement_key or "").strip()
    # (D5) fast-path replay — a settlement already recorded under this key returns
    # it (no second charge); a different fingerprint is a 409 with no side effect.
    if key:
        existing = ServiceOrder.objects.filter(
            hotel=order.hotel, settlement_key=key
        ).first()
        if existing is not None:
            _assert_same_settlement(existing, settlement_fingerprint)
            return existing
    # Re-read with a row lock so two concurrent settlements cannot both pass.
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    # (D5) authoritative re-check under the order row lock.
    if key and (order.settlement_key or "") == key:
        _assert_same_settlement(order, settlement_fingerprint)
        return order
    if order.settlement == OrderSettlement.DIRECT:
        raise OrderAlreadySettled({"order": order.id})
    if order.is_posted or order.posted_charge_id is not None:
        raise OrderAlreadyPosted({"order": order.id})
    totals = _require_settleable(order)

    # Phase 12: posting happens "now" — a closed business day refuses it
    # (imported lazily to avoid app-load cycles).
    from apps.shifts.services import ensure_business_day_open, get_business_date

    ensure_business_day_open(order.hotel, get_business_date(order.hotel))

    # Restaurant closure (P0): folio posting requires the stay to STILL be
    # in-house — final check under the stay row lock (a concurrent check-out
    # serializes against this).
    if order.stay is None:
        raise OrderNotPostable({"reason": "no_folio"})
    _require_stay_in_house(order.hotel, order.stay, lock=True)

    folio = _resolve_folio(order, user=user)
    if folio.status != FolioStatus.OPEN:
        raise FolioClosed({"folio": folio.id, "status": folio.status})

    # D1a — close the audited silent-FX gap: the order's currency must equal the
    # folio's (the folio may carry the booking's AGREED currency, not the current
    # base). No FX conversion — a mismatch is rejected, never silently posted.
    order_currency = (order.currency or _base_currency(order.hotel)).strip().upper()
    if order_currency != (folio.currency or "").strip().upper():
        raise FolioCurrencyMismatch(
            {
                "reason": "order_folio_currency_mismatch",
                "order_currency": order_currency,
                "folio_currency": folio.currency,
            }
        )

    try:
        # Savepoint: a cross-order reuse of ``settlement_key`` collides on the
        # partial unique constraint at ``order.save`` — roll the charge back and
        # surface a clean 409 (no orphan charge, no second money move).
        with transaction.atomic():
            charge = finance_services.add_charge(
                folio,
                charge_type=ChargeType.SERVICE,
                description=f"Service order {order.order_number}",
                quantity=Decimal("1"),
                unit_amount=totals["subtotal"],
                tax_rate=_effective_rate(totals),
                tax_amount=totals["tax_total"],
                source=ChargeSource.SERVICE_ORDER,
                user=user,
            )
            now = timezone.now()
            order.folio = folio
            order.posted_charge = charge
            order.posted_at = now
            order.posted_by = _actor(user)
            order.settlement = OrderSettlement.FOLIO
            order.settled_at = now
            order.settled_by = _actor(user)
            order.settlement_key = key
            order.settlement_fingerprint = settlement_fingerprint or ""
            order.updated_by = _actor(user)
            order.save(
                update_fields=[
                    "folio", "posted_charge", "posted_at", "posted_by",
                    "settlement", "settled_at", "settled_by",
                    "settlement_key", "settlement_fingerprint",
                    "updated_by", "updated_at",
                ]
            )
    except IntegrityError:
        raise IdempotencyKeyConflict()
    _record(
        order.hotel,
        event_type="service_order.posted_to_folio",
        severity="success",
        title=f"Order {order.order_number} posted to folio",
        message=f"{totals['total']} → {folio.folio_number}",
        user=user,
        obj=order,
    )
    return order


@transaction.atomic
def settle_order_direct(order: ServiceOrder, *, method, user=None,
                        amount_received=None, settlement_reference="",
                        settlement_key="", settlement_fingerprint="") -> ServiceOrder:
    """Settle a delivered order by DIRECT payment through the transient-folio
    cycle — central finance services only, one atomic transaction:
    folio → one charge → full payment (joins the actor's open shift drawer)
    → zero balance → folio closed → order linked and marked ``direct``.
    Any failure rolls the whole thing back. The closed transient folio is
    FINAL: corrections belong to the Finance section (a RETURN is the sanctioned
    money-back path — see ``return_order``).

    D2a — the OPTIONAL ``amount_received`` (a cash tender) and ``settlement_
    reference`` (an electronic reference) are captured on the ORDER only; the
    finance Payment still records the exact base-currency total. A cash tender
    below the total is refused; ``change_given`` is server-computed. D5 — the
    settlement is idempotent on a non-blank ``settlement_key``."""
    key = (settlement_key or "").strip()
    # (D5) fast-path replay — no second payment for a replayed key.
    if key:
        existing = ServiceOrder.objects.filter(
            hotel=order.hotel, settlement_key=key
        ).first()
        if existing is not None:
            _assert_same_settlement(existing, settlement_fingerprint)
            return existing
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    # (D5) authoritative re-check under the order row lock.
    if key and (order.settlement_key or "") == key:
        _assert_same_settlement(order, settlement_fingerprint)
        return order
    totals = _require_settleable(order)
    total = totals["total"]

    # C1 (owner decision) — symmetric currency guard. The transient folio is
    # minted in the hotel's CURRENT base currency; the order carries its
    # creation-time currency snapshot. A base-currency change between creation
    # and direct settlement must be rejected, never settled/printed under a
    # mismatched label (no silent FX) — mirrors the guard on post_order_to_folio.
    order_currency = (order.currency or _base_currency(order.hotel)).strip().upper()
    base_currency = (_base_currency(order.hotel) or "").strip().upper()
    if order_currency != base_currency:
        raise FolioCurrencyMismatch(
            {
                "reason": "order_folio_currency_mismatch",
                "order_currency": order_currency,
                "folio_currency": base_currency,
            }
        )

    received = money(amount_received) if amount_received is not None else None
    change = None
    if received is not None:
        # D2a — a cash tender must cover the total; change is server-computed.
        if received < total:
            raise InsufficientCashReceived(
                {"received": str(received), "total": str(total)}
            )
        change = money(received - total)

    payer = (
        order.customer_name
        or (order.stay.primary_guest.full_name if order.stay else "")
        or f"Order {order.order_number}"
    )
    reference = (settlement_reference or "").strip()
    try:
        # Savepoint: a cross-order reuse of ``settlement_key`` collides at
        # ``order.save`` — the whole transient cycle rolls back (no orphan folio /
        # charge / payment) and a clean 409 surfaces.
        with transaction.atomic():
            folio = finance_services.create_folio(
                order.hotel,
                customer_name=payer,
                notes=f"Direct payment for order {order.order_number}",
                user=user,
                origin="order_direct",
            )
            charge = finance_services.add_charge(
                folio,
                charge_type=ChargeType.SERVICE,
                description=f"Service order {order.order_number}",
                quantity=Decimal("1"),
                unit_amount=totals["subtotal"],
                tax_rate=_effective_rate(totals),
                tax_amount=totals["tax_total"],
                source=ChargeSource.SERVICE_ORDER,
                user=user,
            )
            payment = finance_services.record_payment(
                folio,
                amount=total,
                method=method,
                payer_name=payer,
                # The electronic reference (when given) is passed through to the
                # receipt; otherwise the order number, exactly as before.
                reference=(reference or order.order_number),
                user=user,
            )
            if finance_services.folio_balance(folio)["balance"] != ZERO:
                # Structural safety net — charge and payment are built from the
                # same totals, so this can only fire on a genuine defect.
                raise InvalidAmount(
                    {"field": "balance", "reason": "not_zero_after_payment"}
                )
            folio = finance_services.close_folio(folio, user=user)

            now = timezone.now()
            order.folio = folio
            order.posted_charge = charge
            order.settlement = OrderSettlement.DIRECT
            order.settlement_payment = payment
            order.settled_at = now
            order.settled_by = _actor(user)
            order.settlement_method = method
            order.amount_received = received
            order.change_given = change
            order.settlement_reference = reference
            order.settlement_key = key
            order.settlement_fingerprint = settlement_fingerprint or ""
            order.updated_by = _actor(user)
            order.save(
                update_fields=[
                    "folio", "posted_charge", "settlement", "settlement_payment",
                    "settled_at", "settled_by", "settlement_method",
                    "amount_received", "change_given", "settlement_reference",
                    "settlement_key", "settlement_fingerprint",
                    "updated_by", "updated_at",
                ]
            )
    except IntegrityError:
        raise IdempotencyKeyConflict()
    _record(
        order.hotel,
        event_type="service_order.paid_direct",
        severity="success",
        title=f"Order {order.order_number} paid directly",
        message=f"{total} {folio.currency} · {method} · {payment.receipt_number}",
        user=user,
        obj=order,
    )
    return order


# --- Returns & exchanges (money-back / delta, all through finance) ----------------


def _returned_quantity(item: ServiceOrderItem) -> Decimal:
    """The total quantity already returned for ONE order line across the append-only
    return history (both pure returns and exchange return legs count)."""
    agg = ServiceOrderReturnItem.objects.filter(original_item=item).aggregate(
        q=Sum("quantity")
    )
    return money(agg["q"]) if agg["q"] is not None else ZERO


def outlet_refunds(hotel, business_date, outlet, *, gross: bool = True) -> Decimal:
    """C8 — total money REFUNDED to customers for one outlet on a business date:
    the sum of RETURN line totals plus each exchange_lower's (absolute) refunded
    delta. Money OUT only — exchange_higher COLLECTIONS are not refunds and
    exchange_same moves nothing. ``gross=True`` sums tax-inclusive line totals
    (the daily-close ``restaurant_sales`` basis); ``gross=False`` sums tax-
    exclusive amounts (the analytics net-of-tax basis). Reported so a reader can
    read gross sales and refunds separately and derive net = gross − refunds."""
    base = "total_amount" if gross else "amount"
    rep = "replacement_total_amount" if gross else "replacement_amount"
    items = ServiceOrderReturnItem.objects.filter(
        hotel=hotel,
        service_return__business_date=business_date,
        service_return__order__outlet=outlet,
    )
    # A plain RETURN refunds the full returned line value.
    ret_total = items.filter(
        service_return__kind=ReturnKind.RETURN
    ).aggregate(t=Sum(base))["t"] or ZERO
    # An EXCHANGE_LOWER refunds only the (absolute) delta = returned − replacement.
    lower = items.filter(service_return__kind=ReturnKind.EXCHANGE_LOWER)
    lower_ret = lower.aggregate(t=Sum(base))["t"] or ZERO
    lower_rep = lower.aggregate(t=Sum(rep))["t"] or ZERO
    return money(ret_total + (lower_ret - lower_rep))


def _reusable_open_folio(order: ServiceOrder):
    """The guest's OPEN folio (re-read + locked) that a FOLIO return can
    counter-post to, or ``None`` when it is closed / unavailable.

    Owner ruling: a ROOM return on a checked-out guest whose folio is CLOSED must
    NOT be refused — instead it refunds via a NEW transient refund folio, exactly
    like a DIRECT-sale return. So the money helpers branch on "is there a reusable
    OPEN folio?" (this returns it) rather than on ``order.settlement``: a DIRECT
    sale's closed transient folio and a checked-out guest's closed folio both
    return ``None`` here and take the transient path."""
    folio = order.folio
    if folio is None:
        return None
    if folio.hotel_id != order.hotel_id:
        raise CrossTenantReference({"field": "folio"})
    folio = Folio.objects.select_for_update().get(pk=folio.pk)
    if folio.status != FolioStatus.OPEN:
        return None
    return folio


def _refund_amount(order, *, amount, reason, payer, user, method=None,
                   field_charge="reversal_charge", field_payment="refund_payment",
                   field_folio="refund_folio") -> dict:
    """Return money to the customer for ``amount`` (tax-inclusive) — reusing
    finance only. A FOLIO order counter-posts a CREDIT on the guest's OPEN folio
    (``add_charge`` in finance's own reversal shape: the whole amount in
    ``unit_amount`` with ``tax_rate`` 0 — exactly like ``adjust_charge``). A DIRECT
    order — whose transient folio is CLOSED and NEVER reopened (D3a) — opens a NEW
    transient refund folio, credits it, refunds via a NEGATIVE payment
    (``refund_folio_credit``), and closes it at zero. Returns the finance links."""
    amount = money(amount)
    if amount <= ZERO:
        raise InvalidReturnComposition({"reason": "zero_refund"})
    folio = _reusable_open_folio(order)
    if folio is not None:
        credit = finance_services.add_charge(
            folio,
            charge_type=ChargeType.ADJUSTMENT,
            description=f"Return {order.order_number}: {reason}"[:255],
            quantity=Decimal("1"),
            unit_amount=-amount,
            tax_rate=ZERO,
            source=RETURN_CHARGE_SOURCE,
            user=user,
        )
        return {field_charge: credit}
    # No reusable OPEN folio — a DIRECT sale's closed transient folio OR a
    # checked-out guest's CLOSED folio (owner ruling): a NEW transient refund
    # folio (never reopen or alter the original).
    rfolio = finance_services.create_folio(
        order.hotel,
        customer_name=payer,
        notes=f"Return refund for order {order.order_number}"[:255],
        user=user,
        origin="order_return",
    )
    credit = finance_services.add_charge(
        rfolio,
        charge_type=ChargeType.ADJUSTMENT,
        description=f"Return {order.order_number}: {reason}"[:255],
        quantity=Decimal("1"),
        unit_amount=-amount,
        tax_rate=ZERO,
        source=RETURN_CHARGE_SOURCE,
        user=user,
    )
    refund_pay = finance_services.refund_folio_credit(
        rfolio, amount=amount, reason=reason, method=(method or PaymentMethod.CASH),
        user=user,
    )
    finance_services.close_folio(rfolio, user=user)
    return {field_charge: credit, field_payment: refund_pay, field_folio: rfolio}


def _collect_amount(order, *, amount, reason, payer, user, method=None,
                    reference="", amount_received=None) -> dict:
    """Collect an exchange UPGRADE delta from the customer — reusing finance only.
    A FOLIO order adds a SERVICE charge to the guest's OPEN folio (``delta_charge``,
    the customer now owes more — no tender/change there). A DIRECT order (or a
    checked-out guest's closed folio) runs a small transient settlement (folio →
    charge → full payment → close), linking ``delta_charge`` / ``delta_payment`` /
    the transient ``refund_folio``.

    D2a consistency — on the transient (cash) COLLECT path only, an optional
    ``amount_received`` tender is captured: a short tender (received < delta) is
    refused (``InsufficientCashReceived``); ``change`` is server-computed; the
    finance Payment still records the EXACT delta. The captured tender/change are
    returned so the caller persists them on the ServiceOrderReturn."""
    amount = money(amount)
    if amount <= ZERO:
        raise InvalidReturnComposition({"reason": "zero_delta"})
    folio = _reusable_open_folio(order)
    if folio is not None:
        # Guest-folio collect: the delta is a charge on the open folio — no tender.
        charge = finance_services.add_charge(
            folio,
            charge_type=ChargeType.SERVICE,
            description=f"Exchange {order.order_number}: {reason}"[:255],
            quantity=Decimal("1"),
            unit_amount=amount,
            tax_rate=ZERO,
            source=EXCHANGE_CHARGE_SOURCE,
            user=user,
        )
        return {"delta_charge": charge}
    # No reusable OPEN folio (DIRECT sale, or a checked-out guest's CLOSED folio):
    # a small transient settlement collects the delta. D2a — capture the tender.
    received = money(amount_received) if amount_received is not None else None
    change = None
    if received is not None:
        # A cash tender must cover the delta; change is server-computed. Checked
        # BEFORE any finance write, so a short tender creates NO folio/charge/payment.
        if received < amount:
            raise InsufficientCashReceived(
                {"received": str(received), "total": str(amount)}
            )
        change = money(received - amount)
    cfolio = finance_services.create_folio(
        order.hotel,
        customer_name=payer,
        notes=f"Exchange collection for order {order.order_number}"[:255],
        user=user,
        origin="order_exchange",
    )
    charge = finance_services.add_charge(
        cfolio,
        charge_type=ChargeType.SERVICE,
        description=f"Exchange {order.order_number}: {reason}"[:255],
        quantity=Decimal("1"),
        unit_amount=amount,
        tax_rate=ZERO,
        source=EXCHANGE_CHARGE_SOURCE,
        user=user,
    )
    payment = finance_services.record_payment(
        cfolio, amount=amount, method=(method or PaymentMethod.CASH),
        payer_name=payer, reference=(reference or order.order_number), user=user,
    )
    if finance_services.folio_balance(cfolio)["balance"] != ZERO:
        raise InvalidAmount({"field": "balance", "reason": "not_zero_after_payment"})
    finance_services.close_folio(cfolio, user=user)
    links = {"delta_charge": charge, "delta_payment": payment, "refund_folio": cfolio}
    if received is not None:
        links["amount_received"] = received
        links["change_given"] = change
    return links


@transaction.atomic
def return_order(order: ServiceOrder, *, kind, items, reason, user=None,
                 idempotency_key="", request_fingerprint="", method=None,
                 amount_received=None, settlement_reference="") -> ServiceOrderReturn:
    """Return or exchange a DELIVERED, SETTLED order (append-only, void-not-delete,
    idempotent, permission-gated at the view). ``items`` is a list of resolved
    dicts ``{original_item: ServiceOrderItem, quantity, replacement_item:
    ServiceItem|None, replacement_quantity}``.

    Money — ALWAYS through finance, never a direct FolioCharge/Payment write:
    - kind ``return`` → refund the returned total to the customer.
    - kind ``exchange_same`` → no money moves (net delta 0).
    - kind ``exchange_higher`` → collect the positive delta.
    - kind ``exchange_lower`` → refund the (absolute) negative delta.
    A ROOM (FOLIO) order moves money on the guest's OPEN folio; a DIRECT order uses
    a NEW transient refund/collect folio (the original closed folio is untouched).
    The recorded kind is server-verified against the computed delta sign."""
    reason = (reason or "").strip()
    if not reason:
        raise ReturnReasonRequired()
    if kind not in ReturnKind.values:
        raise InvalidReturnComposition({"reason": "unknown_kind", "kind": kind})
    key = (idempotency_key or "").strip()
    # (D5) fast-path replay.
    if key:
        existing = ServiceOrderReturn.objects.filter(
            hotel=order.hotel, idempotency_key=key
        ).first()
        if existing is not None:
            _assert_same_return(existing, request_fingerprint)
            return existing
    # Lock the ORDER row: corrections after settlement serialize here.
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    # (D5) authoritative re-check under the order row lock.
    if key:
        existing = ServiceOrderReturn.objects.filter(
            hotel=order.hotel, idempotency_key=key
        ).first()
        if existing is not None:
            _assert_same_return(existing, request_fingerprint)
            return existing

    if order.status != OrderStatus.DELIVERED:
        raise OrderNotReturnable({"reason": "not_delivered", "status": order.status})
    if order.settlement not in (OrderSettlement.DIRECT, OrderSettlement.FOLIO):
        raise OrderNotReturnable({"reason": "not_settled", "settlement": order.settlement})
    if not items:
        raise InvalidReturnComposition({"reason": "no_items"})

    base = _base_currency(order.hotel)
    is_exchange = kind in EXCHANGE_KINDS
    ret_subtotal = ret_tax = ZERO
    rep_subtotal = rep_tax = ZERO
    rows = []
    for entry in items:
        orig = entry["original_item"]
        if orig.order_id != order.id:
            raise InvalidReturnComposition({"reason": "item_not_on_order", "item": orig.id})
        if orig.cancelled_at is not None:
            raise InvalidReturnComposition({"reason": "item_cancelled", "item": orig.id})
        q = money(entry["quantity"])
        if q <= ZERO:
            raise InvalidReturnComposition(
                {"reason": "quantity_must_be_positive", "item": orig.id}
            )
        already = _returned_quantity(orig)
        remaining = money(orig.quantity) - already
        if q > remaining:
            raise InvalidReturnComposition(
                {"reason": "exceeds_remaining", "item": orig.id, "remaining": str(remaining)}
            )
        amt = money(q * orig.unit_price)
        tax = money(amt * Decimal(orig.tax_rate) / Decimal("100"))
        tot = money(amt + tax)
        ret_subtotal += amt
        ret_tax += tax
        rep = entry.get("replacement_item")
        rep_snap = None
        if rep is not None:
            if not is_exchange:
                raise InvalidReturnComposition({"reason": "replacement_not_allowed", "item": orig.id})
            if rep.hotel_id != order.hotel_id:
                raise CrossTenantReference({"field": "replacement_item"})
            if rep.category.outlet != order.outlet:
                raise OutletMismatch({"item": rep.id, "outlet": order.outlet})
            if not (rep.is_active and rep.is_available):
                raise ServiceItemUnavailable({"item": rep.id, "name": rep.name})
            rep_cur = (rep.currency or "").strip().upper()
            if rep_cur and rep_cur != base:
                raise ServiceCurrencyMismatch(
                    {"item": rep.id, "item_currency": rep_cur, "base_currency": base}
                )
            rq = money(
                entry["replacement_quantity"]
                if entry.get("replacement_quantity") is not None
                else q
            )
            if rq <= ZERO:
                raise InvalidReturnComposition(
                    {"reason": "replacement_quantity_must_be_positive", "item": rep.id}
                )
            r_amt = money(rq * rep.unit_price)
            r_tax = money(r_amt * Decimal(rep.tax_rate) / Decimal("100"))
            r_tot = money(r_amt + r_tax)
            rep_subtotal += r_amt
            rep_tax += r_tax
            rep_snap = dict(
                item=rep, name=rep.name, quantity=rq,
                unit_price=money(rep.unit_price), currency=base,
                tax_rate=Decimal(rep.tax_rate), amount=r_amt,
                tax_amount=r_tax, total=r_tot,
            )
        rows.append(
            dict(
                orig=orig, quantity=q, unit_price=money(orig.unit_price),
                currency=(orig.currency or base), tax_rate=Decimal(orig.tax_rate),
                amount=amt, tax_amount=tax, total=tot, rep=rep_snap,
            )
        )

    ret_total = money(ret_subtotal + ret_tax)
    rep_total = money(rep_subtotal + rep_tax)
    delta_total = money(rep_total - ret_total)
    if ret_total <= ZERO:
        raise InvalidReturnComposition({"reason": "zero_return_total"})

    # kind ↔ money reconciliation (server authoritative; the client hint is verified).
    has_replacement = any(r["rep"] is not None for r in rows)
    if is_exchange and not has_replacement:
        raise InvalidReturnComposition({"reason": "replacement_required"})
    if not is_exchange and has_replacement:
        raise InvalidReturnComposition({"reason": "replacement_not_allowed"})
    if kind == ReturnKind.EXCHANGE_SAME and delta_total != ZERO:
        raise InvalidReturnComposition({"reason": "exchange_kind_mismatch", "delta": str(delta_total)})
    if kind == ReturnKind.EXCHANGE_HIGHER and delta_total <= ZERO:
        raise InvalidReturnComposition({"reason": "exchange_kind_mismatch", "delta": str(delta_total)})
    if kind == ReturnKind.EXCHANGE_LOWER and delta_total >= ZERO:
        raise InvalidReturnComposition({"reason": "exchange_kind_mismatch", "delta": str(delta_total)})

    payer = (
        order.customer_name
        or (order.stay.primary_guest.full_name if order.stay else "")
        or f"Order {order.order_number}"
    )

    # Move the money (finance only) BEFORE recording the return.
    if kind == ReturnKind.RETURN:
        links = _refund_amount(
            order, amount=ret_total, reason=reason, payer=payer, user=user,
            method=method,
        )
    elif kind == ReturnKind.EXCHANGE_SAME:
        links = {}
    elif kind == ReturnKind.EXCHANGE_HIGHER:
        links = _collect_amount(
            order, amount=delta_total, reason=reason, payer=payer, user=user,
            method=method, reference=settlement_reference,
            amount_received=amount_received,
        )
    else:  # EXCHANGE_LOWER — refund the absolute delta.
        links = _refund_amount(
            order, amount=-delta_total, reason=reason, payer=payer, user=user,
            method=method, field_charge="delta_charge", field_payment="delta_payment",
        )

    try:
        # Savepoint: a cross-request reuse of ``idempotency_key`` collides on the
        # partial unique constraint — the whole return (and its finance legs, via
        # the outer atomic) rolls back and a clean 409 surfaces.
        with transaction.atomic():
            ret = ServiceOrderReturn.objects.create(
                hotel=order.hotel,
                order=order,
                return_number=next_return_number(order.hotel),
                kind=kind,
                reason=reason,
                business_date=_business_date(order.hotel),
                idempotency_key=key,
                request_fingerprint=request_fingerprint or "",
                created_by=_actor(user),
                **links,
            )
            for r in rows:
                rep = r["rep"] or {}
                ServiceOrderReturnItem.objects.create(
                    hotel=order.hotel,
                    service_return=ret,
                    original_item=r["orig"],
                    quantity=r["quantity"],
                    item_name=r["orig"].item_name,
                    unit_price=r["unit_price"],
                    currency=r["currency"],
                    tax_rate=r["tax_rate"],
                    amount=r["amount"],
                    tax_amount=r["tax_amount"],
                    total_amount=r["total"],
                    replacement_item=rep.get("item"),
                    replacement_name=rep.get("name", ""),
                    replacement_quantity=rep.get("quantity"),
                    replacement_unit_price=rep.get("unit_price"),
                    replacement_currency=rep.get("currency", ""),
                    replacement_tax_rate=rep.get("tax_rate"),
                    replacement_amount=rep.get("amount"),
                    replacement_tax_amount=rep.get("tax_amount"),
                    replacement_total_amount=rep.get("total"),
                )
    except IntegrityError:
        raise IdempotencyKeyConflict()
    _record(
        order.hotel,
        event_type="service_order.returned",
        severity="warning",
        title=f"Order {order.order_number} {kind}",
        message=f"{ret.return_number} · {reason}",
        user=user,
        obj=order,
    )
    return ret
