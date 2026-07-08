"""Service-order domain services (Phase 9) — the single write path.

Views never mutate orders directly. Money math reuses the finance ``money()``
rounding so an order's totals and its posted FolioCharge always agree to the
cent. The ONLY financial write is ``post_order_to_folio``, and it goes through
``apps.finance.services`` (one charge per order, once, ever).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    CancellationReasonRequired,
    CrossTenantReference,
    FolioClosed,
    InvalidAmount,
    InvalidOrderStatusTransition,
    OrderAlreadyPosted,
    OrderItemsRequired,
    OrderNotEditable,
    OrderNotPostable,
    ServiceItemUnavailable,
)
from apps.finance import services as finance_services
from apps.finance.models import ChargeType, Folio, FolioStatus
from apps.finance.services import money

from .models import (
    OrderStatus,
    ServiceItem,
    ServiceNumberSequence,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatusLog,
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
    """Re-derive an order's totals from its line snapshots."""
    lines = list(order.items.all())
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


def _build_items(order: ServiceOrder, items_data: list) -> None:
    """Snapshot catalog items onto the order (name/price/tax frozen)."""
    if not items_data:
        raise OrderItemsRequired()
    for entry in items_data:
        item: ServiceItem = entry["service_item"]
        if item.hotel_id != order.hotel_id:
            raise CrossTenantReference({"field": "service_item"})
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


@transaction.atomic
def create_order(hotel, *, user=None, source, stay=None, room=None,
                 status=OrderStatus.SUBMITTED, requested_delivery_time=None,
                 notes="", internal_notes="", items_data) -> ServiceOrder:
    if stay is not None and stay.hotel_id != hotel.id:
        raise CrossTenantReference({"field": "stay"})
    if room is not None and room.hotel_id != hotel.id:
        raise CrossTenantReference({"field": "room"})
    # A stay implies its physical room when none was picked explicitly.
    if room is None and stay is not None:
        room = stay.room
    actor = _actor(user)
    order = ServiceOrder.objects.create(
        hotel=hotel,
        order_number=next_order_number(hotel),
        source=source,
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
    _build_items(order, items_data)
    _log(order, "", order.status, user)
    return order


@transaction.atomic
def update_order(order: ServiceOrder, *, user=None, items_data=None, **meta) -> ServiceOrder:
    """Edit an order. Items only while draft; metadata until delivered."""
    if order.is_posted or order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        raise OrderNotEditable({"status": order.status, "posted": order.is_posted})
    if items_data is not None:
        if order.status not in ITEM_EDITABLE_STATUSES:
            raise OrderNotEditable({"status": order.status, "reason": "items_locked"})
        order.items.all().delete()
        _build_items(order, items_data)
    if order.status not in META_EDITABLE_STATUSES:
        raise OrderNotEditable({"status": order.status})
    for field in ("notes", "internal_notes", "requested_delivery_time", "source"):
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
    return order


@transaction.atomic
def cancel_order(order: ServiceOrder, *, reason, user=None) -> ServiceOrder:
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    if order.is_posted:
        # A posted order's money already lives on the folio; corrections are a
        # finance-side charge void — never a service-side cancellation.
        raise OrderNotEditable({"reason": "posted"})
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
    return order


def _resolve_folio(order: ServiceOrder, *, user=None) -> Folio:
    """The folio the order posts to: its own, the stay's open one, or a new
    folio created through finance for the stay."""
    if order.folio is not None:
        if order.folio.hotel_id != order.hotel_id:
            raise CrossTenantReference({"field": "folio"})
        return order.folio
    if order.stay is not None:
        existing = Folio.objects.filter(
            hotel=order.hotel, stay=order.stay, status=FolioStatus.OPEN
        ).first()
        if existing:
            return existing
        return finance_services.create_folio(
            order.hotel,
            reservation=order.stay.reservation,
            stay=order.stay,
            guest=order.stay.primary_guest,
            user=user,
        )
    raise OrderNotPostable({"reason": "no_folio"})


@transaction.atomic
def post_order_to_folio(order: ServiceOrder, *, user=None) -> ServiceOrder:
    """Post a delivered order to a folio as ONE service charge, exactly once."""
    # Re-read with a row lock so two concurrent posts cannot both pass.
    order = ServiceOrder.objects.select_for_update().get(pk=order.pk)
    if order.is_posted or order.posted_charge_id is not None:
        raise OrderAlreadyPosted({"order": order.id})
    if order.status == OrderStatus.CANCELLED:
        raise OrderNotPostable({"reason": "cancelled"})
    if order.status != OrderStatus.DELIVERED:
        raise OrderNotPostable({"reason": "not_delivered", "status": order.status})
    totals = order_totals(order)
    if totals["total"] <= ZERO:
        raise OrderNotPostable({"reason": "zero_total"})

    # Phase 12: posting happens "now" — a closed business day refuses it
    # (imported lazily to avoid app-load cycles).
    from apps.shifts.services import ensure_business_day_open, get_business_date

    ensure_business_day_open(order.hotel, get_business_date(order.hotel))

    folio = _resolve_folio(order, user=user)
    if folio.status != FolioStatus.OPEN:
        raise FolioClosed({"folio": folio.id, "status": folio.status})

    # Informational effective rate; the exact tax sum is passed explicitly so
    # the charge's amount/tax/total equal the order's to the cent.
    effective_rate = (
        money(totals["tax_total"] / totals["subtotal"] * Decimal("100"))
        if totals["subtotal"] > ZERO
        else ZERO
    )
    charge = finance_services.add_charge(
        folio,
        charge_type=ChargeType.SERVICE,
        description=f"Service order {order.order_number}",
        quantity=Decimal("1"),
        unit_amount=totals["subtotal"],
        tax_rate=effective_rate,
        tax_amount=totals["tax_total"],
        source="service_order",
        user=user,
    )
    order.folio = folio
    order.posted_charge = charge
    order.posted_at = timezone.now()
    order.posted_by = _actor(user)
    order.updated_by = _actor(user)
    order.save(
        update_fields=[
            "folio", "posted_charge", "posted_at", "posted_by",
            "updated_by", "updated_at",
        ]
    )
    # Phase 14: activity + notifications (lazy import).
    from apps.notifications.services import record_activity

    record_activity(
        order.hotel,
        event_type="service_order.posted_to_folio",
        category="service",
        severity="success",
        title=f"Order {order.order_number} posted to folio",
        message=f"{totals['total']} → {folio.folio_number}",
        actor=user,
        related_object=order,
        related_url="/hotel/services",
    )
    return order
