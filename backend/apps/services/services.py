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

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import (
    CancellationReasonRequired,
    CrossTenantReference,
    FolioClosed,
    InvalidAmount,
    InvalidOrderComposition,
    InvalidOrderStatusTransition,
    LastActiveItemNotCancellable,
    OrderAlreadyPosted,
    OrderAlreadySettled,
    OrderItemsRequired,
    OrderNotEditable,
    OrderNotPostable,
    OutletDisabled,
    OutletMismatch,
    ServiceItemUnavailable,
    StatusNoteRequired,
    StayNotInHouse,
    TableHasOpenOrder,
    TableOccupied,
    TableOutOfService,
)
from apps.finance import services as finance_services
from apps.finance.models import ChargeType, Folio, FolioStatus
from apps.finance.services import money

from .models import (
    OrderSettlement,
    OrderStatus,
    OrderType,
    Outlet,
    RestaurantTable,
    ServiceItem,
    ServiceNumberSequence,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatusLog,
    TableStatus,
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


def _business_date(hotel):
    from apps.shifts.services import get_business_date

    return get_business_date(hotel)


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
    """Snapshot catalog items onto the order (name/price/tax frozen). Every
    item must belong to the ORDER's outlet (via its category)."""
    if not items_data:
        raise OrderItemsRequired()
    for entry in items_data:
        item: ServiceItem = entry["service_item"]
        if item.hotel_id != order.hotel_id:
            raise CrossTenantReference({"field": "service_item"})
        if item.category.outlet != order.outlet:
            raise OutletMismatch({"item": item.id, "outlet": order.outlet})
        if not (item.is_active and item.is_available):
            raise ServiceItemUnavailable({"item": item.id, "name": item.name})
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
def post_order_to_folio(order: ServiceOrder, *, user=None) -> ServiceOrder:
    """Post a delivered order to the IN-HOUSE stay's folio as ONE finance
    charge, exactly once (XOR with direct payment)."""
    # Re-read with a row lock so two concurrent settlements cannot both pass.
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
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

    charge = finance_services.add_charge(
        folio,
        charge_type=ChargeType.SERVICE,
        description=f"Service order {order.order_number}",
        quantity=Decimal("1"),
        unit_amount=totals["subtotal"],
        tax_rate=_effective_rate(totals),
        tax_amount=totals["tax_total"],
        source="service_order",
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
    order.updated_by = _actor(user)
    order.save(
        update_fields=[
            "folio", "posted_charge", "posted_at", "posted_by",
            "settlement", "settled_at", "settled_by",
            "updated_by", "updated_at",
        ]
    )
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
def settle_order_direct(order: ServiceOrder, *, method, user=None) -> ServiceOrder:
    """Settle a delivered order by DIRECT payment through the transient-folio
    cycle — central finance services only, one atomic transaction:
    folio → one charge → full payment (joins the actor's open shift drawer)
    → zero balance → folio closed → order linked and marked ``direct``.
    Any failure rolls the whole thing back. The closed transient folio is
    FINAL: corrections belong to the Finance section."""
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    totals = _require_settleable(order)

    payer = (
        order.customer_name
        or (order.stay.primary_guest.full_name if order.stay else "")
        or f"Order {order.order_number}"
    )
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
        source="service_order",
        user=user,
    )
    payment = finance_services.record_payment(
        folio,
        amount=totals["total"],
        method=method,
        payer_name=payer,
        reference=order.order_number,
        user=user,
    )
    if finance_services.folio_balance(folio)["balance"] != ZERO:
        # Structural safety net — charge and payment are built from the same
        # totals, so this can only fire on a genuine defect.
        raise InvalidAmount({"field": "balance", "reason": "not_zero_after_payment"})
    folio = finance_services.close_folio(folio, user=user)

    now = timezone.now()
    order.folio = folio
    order.posted_charge = charge
    order.settlement = OrderSettlement.DIRECT
    order.settlement_payment = payment
    order.settled_at = now
    order.settled_by = _actor(user)
    order.updated_by = _actor(user)
    order.save(
        update_fields=[
            "folio", "posted_charge", "settlement", "settlement_payment",
            "settled_at", "settled_by", "updated_by", "updated_at",
        ]
    )
    _record(
        order.hotel,
        event_type="service_order.paid_direct",
        severity="success",
        title=f"Order {order.order_number} paid directly",
        message=f"{totals['total']} {folio.currency} · {method} · {payment.receipt_number}",
        user=user,
        obj=order,
    )
    return order
