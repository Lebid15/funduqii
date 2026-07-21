"""Report aggregation services (Phase 13) — READ-ONLY, backend-computed.

Deliberate boundaries:
- Nothing here writes anything, ever — no operational or financial mutation.
- Every aggregate is hotel-scoped (tenant isolation at the queryset root).
- Money is Decimal-only via the finance ``money()`` rounding and serialized
  as strings; no float ever touches an amount.
- **Occupancy is derived from stays** (an in-house interval covers a day),
  never from ``Room.status`` — there is no `occupied` room status.
- ``net_cashflow_simple`` = POSTED payments − POSTED expenses for the range.
  It is an OPERATIONAL movement figure, deliberately NOT called profit —
  this is not an accounting P&L (no accruals, no COGS, no depreciation).
- VOIDED financial records are excluded from every total and reported
  separately as counts (documented rule).
- The DailyClose snapshot is displayed as stored documentation; live report
  numbers are always recomputed from the source records.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.db.models import Avg, Count, DateField, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate

from apps.finance.models import (
    ChargeType,
    Expense,
    Folio,
    FolioCharge,
    FolioStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PostingStatus,
)
from apps.finance.services import money
from apps.guests.models import Guest
from apps.operations.models import (
    HousekeepingStatus,
    HousekeepingTask,
    LostFoundItem,
    LostFoundStatus,
    MaintenanceRequest,
    MaintenanceStatus,
    OperationPriority,
)
from apps.reservations.models import Reservation, ReservationStatus
from apps.rooms.models import Room, RoomStatus
from apps.services.models import (
    OrderSettlement,
    OrderStatus,
    Outlet,
    ServiceOrder,
    ServiceOrderItem,
)
from apps.shifts.models import (
    DailyClose,
    DailyCloseStatus,
    Shift,
    ShiftHandover,
    ShiftStatus,
)
from apps.shifts.services import get_business_date, unassigned_movements
from apps.stays.models import Stay, StayStatus

ZERO = Decimal("0.00")

#: Maximum report range (documented performance guard).
MAX_RANGE_DAYS = 366

#: Open/active statuses reused across reports.
OPEN_MT = (MaintenanceStatus.OPEN, MaintenanceStatus.ASSIGNED, MaintenanceStatus.IN_PROGRESS)
ACTIVE_HK = (HousekeepingStatus.PENDING, HousekeepingStatus.ASSIGNED, HousekeepingStatus.IN_PROGRESS)
OPEN_LF = (LostFoundStatus.FOUND, LostFoundStatus.STORED)


def default_range(hotel) -> tuple[datetime.date, datetime.date]:
    """Default reporting window: the current month (hotel business date)."""
    today = get_business_date(hotel)
    return today.replace(day=1), today


def _amount(qs) -> Decimal:
    return money(qs.aggregate(t=Sum("amount"))["t"] or 0)


def _by(qs, field, amount=False) -> list[dict]:
    rows = qs.values(field).annotate(n=Count("id"), total=Sum("amount") if amount else Count("id"))
    out = []
    for row in rows.order_by(field):
        item = {"key": row[field], "count": row["n"]}
        if amount:
            item["total"] = str(money(row["total"] or 0))
        out.append(item)
    return out


def _capacity_rooms(hotel):
    """Rooms counted as sellable capacity: active, not archived, and NOT
    blocked from sale (maintenance / out_of_service). Uses the shared
    ``_sellable_capacity`` definition — no separate rule inside reports."""
    return _sellable_capacity(hotel)


def occupied_counts_by_day(hotel, date_from, date_to) -> dict[str, int]:
    """Occupancy per date, derived from STAY intervals (never Room.status):
    a stay covers day D when it checked in on/before D and checked out
    AFTER D (or is still in-house). Cancelled stays never count."""
    stays = (
        Stay.objects.filter(hotel=hotel)
        .exclude(status=StayStatus.CANCELLED)
        .filter(actual_check_in_at__date__lte=date_to)
        .filter(
            Q(actual_check_out_at__isnull=True)
            | Q(actual_check_out_at__date__gt=date_from)
        )
        .values_list("actual_check_in_at", "actual_check_out_at")
    )
    intervals = [
        (ci.date(), co.date() if co else None) for ci, co in stays if ci is not None
    ]
    days: dict[str, int] = {}
    day = date_from
    while day <= date_to:
        days[str(day)] = sum(
            1 for ci, co in intervals if ci <= day and (co is None or co > day)
        )
        day += datetime.timedelta(days=1)
    return days


def occupancy_rate(hotel, date_from, date_to) -> tuple[str, dict[str, int]]:
    by_day = occupied_counts_by_day(hotel, date_from, date_to)
    rooms_total = _capacity_rooms(hotel).count()
    num_days = (date_to - date_from).days + 1
    capacity = rooms_total * num_days
    occupied = sum(by_day.values())
    rate = (
        money(Decimal(occupied) / Decimal(capacity) * Decimal("100"))
        if capacity
        else ZERO
    )
    return str(rate), by_day


# --- Overview -----------------------------------------------------------------------


def overview_report(hotel, date_from, date_to) -> dict:
    reservations = Reservation.objects.filter(
        hotel=hotel, created_at__date__range=(date_from, date_to)
    )
    arrivals = Stay.objects.filter(
        hotel=hotel, actual_check_in_at__date__range=(date_from, date_to)
    ).count()
    departures = Stay.objects.filter(
        hotel=hotel, actual_check_out_at__date__range=(date_from, date_to)
    ).count()
    rooms = Room.objects.filter(hotel=hotel, is_active=True)
    orders = ServiceOrder.objects.filter(
        hotel=hotel, ordered_at__date__range=(date_from, date_to)
    )
    # Financial totals are deliberately NOT exposed here: reports.view is
    # operational-only. Money lives in ``finance_overview`` behind
    # reports.finance (leak fix, final closure).
    rate, _by_day = occupancy_rate(hotel, date_from, date_to)
    return {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "reservations_count": reservations.count(),
        "confirmed_reservations_count": reservations.filter(
            status=ReservationStatus.CONFIRMED
        ).count(),
        "cancelled_reservations_count": reservations.filter(
            status=ReservationStatus.CANCELLED
        ).count(),
        # There is no no-show status in the reservation model (documented);
        # expired holds are the closest operational signal.
        "expired_reservations_count": reservations.filter(
            status=ReservationStatus.EXPIRED
        ).count(),
        "arrivals_count": arrivals,
        "departures_count": departures,
        # Current in-house right now (documented: point-in-time, not ranged).
        "in_house_count": Stay.objects.filter(
            hotel=hotel, status=StayStatus.IN_HOUSE
        ).count(),
        "occupancy_rate": rate,
        "rooms_total": rooms.count(),
        "rooms_available": rooms.filter(status=RoomStatus.AVAILABLE).count(),
        "rooms_dirty": rooms.filter(status=RoomStatus.DIRTY).count(),
        "rooms_maintenance": rooms.filter(
            status__in=[RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE]
        ).count(),
        "service_orders_total": orders.count(),
        "open_housekeeping_tasks": HousekeepingTask.objects.filter(
            hotel=hotel, status__in=ACTIVE_HK
        ).count(),
        "open_maintenance_requests": MaintenanceRequest.objects.filter(
            hotel=hotel, status__in=OPEN_MT
        ).count(),
        "open_lost_found_items": LostFoundItem.objects.filter(
            hotel=hotel, status__in=OPEN_LF
        ).count(),
        "open_shifts_count": Shift.objects.filter(
            hotel=hotel, status=ShiftStatus.OPEN
        ).count(),
        "closed_days_count": DailyClose.objects.filter(
            hotel=hotel,
            status=DailyCloseStatus.CLOSED,
            business_date__range=(date_from, date_to),
        ).count(),
    }


# --- Reservations ---------------------------------------------------------------------


def reservations_report(hotel, date_from, date_to, *, page=1, page_size=25) -> dict:
    qs = Reservation.objects.filter(
        hotel=hotel, created_at__date__range=(date_from, date_to)
    )
    nights_avg = qs.annotate(
        n=F("check_out_date") - F("check_in_date")
    ).aggregate(avg=Avg("n"))["avg"]
    avg_nights = (
        str(money(Decimal(nights_avg.days) if hasattr(nights_avg, "days") else Decimal(nights_avg)))
        if nights_avg is not None
        else "0.00"
    )
    by_room_type = [
        {"key": row["lines__room_type__name"] or "-", "count": row["n"]}
        for row in qs.values("lines__room_type__name").annotate(n=Count("id", distinct=True)).order_by("-n")
        if row["lines__room_type__name"] is not None
    ]
    arrivals_by_day = {
        str(row["d"]): row["n"]
        for row in Stay.objects.filter(
            hotel=hotel, actual_check_in_at__date__range=(date_from, date_to)
        )
        .annotate(d=F("actual_check_in_at__date"))
        .values("d")
        .annotate(n=Count("id"))
        .order_by("d")
    }
    departures_by_day = {
        str(row["d"]): row["n"]
        for row in Stay.objects.filter(
            hotel=hotel, actual_check_out_at__date__range=(date_from, date_to)
        )
        .annotate(d=F("actual_check_out_at__date"))
        .values("d")
        .annotate(n=Count("id"))
        .order_by("d")
    }
    total = qs.count()
    start = (page - 1) * page_size
    rows = [
        {
            "id": r.id,
            "reservation_number": r.reservation_number,
            "guest_name": r.primary_guest_name,
            "status": r.status,
            "source": r.source,
            "booking_kind": r.booking_kind,
            "check_in_date": str(r.check_in_date),
            "check_out_date": str(r.check_out_date),
            "nights": r.nights,
        }
        for r in qs.order_by("-created_at")[start : start + page_size]
    ]
    return {
        "by_status": _by(qs, "status"),
        "by_source": _by(qs, "source"),
        "by_booking_kind": _by(qs, "booking_kind"),
        "average_nights": avg_nights,
        "by_room_type": by_room_type,
        "arrivals_by_day": arrivals_by_day,
        "departures_by_day": departures_by_day,
        "list": {"count": total, "page": page, "page_size": page_size, "results": rows},
    }


# --- Occupancy --------------------------------------------------------------------------


def occupancy_report(hotel, date_from, date_to) -> dict:
    rate, by_day = occupancy_rate(hotel, date_from, date_to)
    rooms = Room.objects.filter(hotel=hotel, is_active=True)
    capacity = _capacity_rooms(hotel).count()
    by_room_type = [
        {"key": row["room__room_type__name"] or "-", "count": row["n"]}
        for row in Stay.objects.filter(hotel=hotel)
        .exclude(status=StayStatus.CANCELLED)
        .filter(actual_check_in_at__date__range=(date_from, date_to))
        .values("room__room_type__name")
        .annotate(n=Count("id"))
        .order_by("-n")
    ]
    return {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "occupancy_rate": rate,
        "rooms_capacity": capacity,
        "occupied_by_day": by_day,
        "in_house_now": Stay.objects.filter(
            hotel=hotel, status=StayStatus.IN_HOUSE
        ).count(),
        "room_status_now": {
            "available": rooms.filter(status=RoomStatus.AVAILABLE).count(),
            "dirty": rooms.filter(status=RoomStatus.DIRTY).count(),
            "cleaning": rooms.filter(status=RoomStatus.CLEANING).count(),
            "maintenance": rooms.filter(status=RoomStatus.MAINTENANCE).count(),
            "out_of_service": rooms.filter(status=RoomStatus.OUT_OF_SERVICE).count(),
        },
        "stays_by_room_type": by_room_type,
    }


# --- Guests -----------------------------------------------------------------------------


def guests_report(hotel, date_from, date_to, *, page=1, page_size=25) -> dict:
    new_guests = Guest.objects.filter(
        hotel=hotel, created_at__date__range=(date_from, date_to)
    )
    by_nationality = [
        {"key": row["nationality"] or "-", "count": row["n"]}
        for row in new_guests.values("nationality").annotate(n=Count("id")).order_by("-n")[:10]
    ]
    repeat_guests = (
        Guest.objects.filter(hotel=hotel)
        .annotate(stay_count=Count("primary_stays"))
        .filter(stay_count__gte=2)
        .count()
    )
    checked_out = Stay.objects.filter(
        hotel=hotel,
        status=StayStatus.CHECKED_OUT,
        actual_check_out_at__date__range=(date_from, date_to),
    ).count()
    total = new_guests.count()
    start = (page - 1) * page_size
    rows = [
        {
            "id": g.id,
            "full_name": g.full_name,
            "nationality": g.nationality,
            "phone": g.phone,
            "created_at": str(g.created_at.date()),
        }
        for g in new_guests.order_by("-created_at")[start : start + page_size]
    ]
    return {
        "new_guests_count": total,
        "by_nationality": by_nationality,
        "repeat_guests_count": repeat_guests,
        "current_residents_count": Stay.objects.filter(
            hotel=hotel, status=StayStatus.IN_HOUSE
        ).count(),
        "checked_out_count": checked_out,
        "list": {"count": total, "page": page, "page_size": page_size, "results": rows},
    }


# --- Finance ----------------------------------------------------------------------------


def _per_day(qs, date_field) -> list[dict]:
    rows = (
        qs.annotate(d=F(f"{date_field}__date"))
        .values("d")
        .annotate(n=Count("id"), total=Sum("amount"))
        .order_by("d")
    )
    return [
        {"date": str(row["d"]), "count": row["n"], "total": str(money(row["total"] or 0))}
        for row in rows
    ]


def finance_report(hotel, date_from, date_to) -> dict:
    payments = Payment.objects.filter(
        _pay_bd_range(date_from, date_to),
        hotel=hotel, status=PostingStatus.POSTED,
    )
    expenses = Expense.objects.filter(
        _pay_bd_range(date_from, date_to),
        hotel=hotel, status=PostingStatus.POSTED,
    )
    invoices = Invoice.objects.filter(
        hotel=hotel, status=InvoiceStatus.ISSUED,
        issued_at__date__range=(date_from, date_to),
    )
    total_payments = _amount(payments)
    total_expenses = _amount(expenses)
    voided = {
        "payments": Payment.objects.filter(
            hotel=hotel, status=PostingStatus.VOIDED,
            voided_at__date__range=(date_from, date_to),
        ).count(),
        "expenses": Expense.objects.filter(
            hotel=hotel, status=PostingStatus.VOIDED,
            voided_at__date__range=(date_from, date_to),
        ).count(),
        "charges": FolioCharge.objects.filter(
            hotel=hotel, status=PostingStatus.VOIDED,
            voided_at__date__range=(date_from, date_to),
        ).count(),
    }
    return {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "payments_by_method": _by(payments, "method", amount=True),
        "payments_by_day": _per_day_bd(payments),
        "expenses_by_category": _by(expenses, "category", amount=True),
        "expenses_by_day": _per_day_bd(expenses),
        "total_payments": str(total_payments),
        "total_expenses": str(total_expenses),
        # Deliberately named "cashflow", NEVER "profit" — this is operational
        # movement, not an accounting P&L (documented).
        "net_cashflow_simple": str(money(total_payments - total_expenses)),
        "invoices_issued_count": invoices.count(),
        "invoices_issued_total": str(
            money(invoices.aggregate(t=Sum("total"))["t"] or 0)
        ),
        "open_folios_count": Folio.objects.filter(
            hotel=hotel, status=FolioStatus.OPEN
        ).count(),
        "folios_closed_in_range": Folio.objects.filter(
            hotel=hotel, status=FolioStatus.CLOSED,
            closed_at__date__range=(date_from, date_to),
        ).count(),
        # Voided records are EXCLUDED from all totals and reported here.
        "voided": voided,
    }


# --- Services ----------------------------------------------------------------------------


def services_report(hotel, date_from, date_to) -> dict:
    orders = ServiceOrder.objects.filter(
        hotel=hotel, ordered_at__date__range=(date_from, date_to)
    )
    delivered = orders.filter(status=OrderStatus.DELIVERED)
    posted_orders = ServiceOrder.objects.filter(
        hotel=hotel, posted_at__date__range=(date_from, date_to)
    ).select_related("posted_charge")
    posted_total = money(
        sum(
            (money(o.posted_charge.total_amount) for o in posted_orders if o.posted_charge),
            ZERO,
        )
    )
    top_items = [
        {
            "key": row["item_name"],
            "count": row["n"],
            "quantity": str(money(row["qty"] or 0)),
            "total": str(money(row["total"] or 0)),
        }
        for row in ServiceOrderItem.objects.filter(
            hotel=hotel, order__ordered_at__date__range=(date_from, date_to)
        )
        .exclude(order__status=OrderStatus.CANCELLED)
        .values("item_name")
        .annotate(n=Count("id"), qty=Sum("quantity"), total=Sum("total_amount"))
        .order_by("-total")[:10]
    ]
    return {
        "orders_count": orders.count(),
        "by_status": _by(orders, "status"),
        "by_source": _by(orders, "source"),
        "delivered_posted": delivered.filter(posted_at__isnull=False).count(),
        "delivered_unposted": delivered.filter(posted_at__isnull=True).count(),
        "posted_to_folio_total": str(posted_total),
        "top_items": top_items,
        "cancelled_count": orders.filter(status=OrderStatus.CANCELLED).count(),
    }


# --- Operations --------------------------------------------------------------------------


def operations_report(hotel, date_from, date_to) -> dict:
    hk = HousekeepingTask.objects.filter(
        hotel=hotel, requested_at__date__range=(date_from, date_to)
    )
    mt = MaintenanceRequest.objects.filter(
        hotel=hotel, reported_at__date__range=(date_from, date_to)
    )
    lf = LostFoundItem.objects.filter(
        hotel=hotel, found_at__date__range=(date_from, date_to)
    )
    rooms = Room.objects.filter(hotel=hotel, is_active=True)
    return {
        "housekeeping_by_status": _by(hk, "status"),
        "cleaning_completed_count": hk.filter(
            status=HousekeepingStatus.COMPLETED
        ).count(),
        "maintenance_by_status": _by(mt, "status"),
        "maintenance_by_category": _by(mt, "category"),
        "maintenance_by_priority": _by(mt, "priority"),
        "rooms_under_maintenance_now": rooms.filter(
            status__in=[RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE]
        ).count(),
        "lost_found_by_status": _by(lf, "status"),
        "lost_found_by_category": _by(lf, "category"),
        "urgent_open_count": (
            hk.filter(priority=OperationPriority.URGENT, status__in=ACTIVE_HK).count()
            + mt.filter(priority=OperationPriority.URGENT, status__in=OPEN_MT).count()
        ),
    }


# --- Shifts & daily close -------------------------------------------------------------------


def shifts_report(hotel, date_from, date_to) -> dict:
    shifts = Shift.objects.filter(
        hotel=hotel, business_date__range=(date_from, date_to)
    )
    closed = shifts.filter(status=ShiftStatus.CLOSED)
    handovers = ShiftHandover.objects.filter(
        hotel=hotel, created_at__date__range=(date_from, date_to)
    )
    total_expected = money(closed.aggregate(t=Sum("expected_cash_amount"))["t"] or 0)
    total_actual = money(closed.aggregate(t=Sum("actual_cash_amount"))["t"] or 0)
    total_difference = money(closed.aggregate(t=Sum("cash_difference"))["t"] or 0)
    # Unassigned POSTED movements dated inside the range (never hidden).
    unassigned_payments = Payment.objects.filter(
        hotel=hotel, shift__isnull=True, status=PostingStatus.POSTED,
        paid_at__date__range=(date_from, date_to),
    )
    unassigned_expenses = Expense.objects.filter(
        hotel=hotel, shift__isnull=True, status=PostingStatus.POSTED,
        paid_at__date__range=(date_from, date_to),
    )
    shifts_rows = [
        {
            "shift_number": s.shift_number,
            "business_date": str(s.business_date),
            "status": s.status,
            "responsible": s.responsible_user.full_name,
            "opening_cash": str(money(s.opening_cash_amount)),
            "expected_cash": str(money(s.expected_cash_amount)),
            "actual_cash": (
                str(money(s.actual_cash_amount)) if s.actual_cash_amount is not None else None
            ),
            "cash_difference": str(money(s.cash_difference)),
            "difference_reason": s.difference_reason,
        }
        for s in shifts.select_related("responsible_user").order_by("-opened_at")[:100]
    ]
    return {
        "shifts_by_status": _by(shifts, "status"),
        "closed_shifts_count": closed.count(),
        "shifts_with_difference": closed.exclude(cash_difference=ZERO).count(),
        "total_expected_cash": str(total_expected),
        "total_actual_cash": str(total_actual),
        "total_cash_difference": str(total_difference),
        "handovers_by_status": _by(handovers, "status"),
        "unassigned_movements": {
            "payments_count": unassigned_payments.count(),
            "payments_total": str(_amount(unassigned_payments)),
            "expenses_count": unassigned_expenses.count(),
            "expenses_total": str(_amount(unassigned_expenses)),
        },
        "closed_days_count": DailyClose.objects.filter(
            hotel=hotel, status=DailyCloseStatus.CLOSED,
            business_date__range=(date_from, date_to),
        ).count(),
        "shifts": shifts_rows,
        "today_unassigned": unassigned_movements(hotel, get_business_date(hotel)),
    }


def daily_close_list(hotel, date_from, date_to, *, page=1, page_size=25) -> dict:
    qs = DailyClose.objects.filter(
        hotel=hotel, business_date__range=(date_from, date_to)
    ).select_related("closed_by").order_by("-business_date")
    total = qs.count()
    start = (page - 1) * page_size
    rows = [
        {
            "id": c.id,
            "close_number": c.close_number,
            "business_date": str(c.business_date),
            "status": c.status,
            "closed_by": c.closed_by.full_name if c.closed_by else "",
            "closed_at": c.closed_at.isoformat() if c.closed_at else None,
            "totals": c.totals_json,
        }
        for c in qs[start : start + page_size]
    ]
    return {"count": total, "page": page, "page_size": page_size, "results": rows}


# ============================================================================
# Unified financial engine (Finance & Reports final closure)
# ----------------------------------------------------------------------------
# ONE read-only computation of a business date's financial figures, keyed by
# business_date. The OPEN day is computed LIVE; CLOSED days are read from the
# frozen ``DailyClose`` snapshot (existing sections + the new ``reporting``
# block); period reports SUM the per-day blocks, adding the open day ONCE.
# No writes, no third store — reports never touch a live record for a day that
# is already closed.
# ============================================================================

BLOCKED_ROOM_STATUSES = (
    RoomStatus.ARCHIVED, RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE,
)


def _sellable_capacity(hotel):
    """Sellable physical rooms: active, not archived, and NOT blocked from sale
    (maintenance / out_of_service). Mirrors the central RoomStatus semantics —
    no new availability definition is introduced inside reports."""
    return Room.objects.filter(hotel=hotel, is_active=True).exclude(
        status__in=BLOCKED_ROOM_STATUSES
    )


def _D(x):
    return money(Decimal(str(x)) if x is not None else 0)


def _pay_bd(d):
    """A dated finance record belongs to business date ``d`` by its stored
    business_date; legacy rows without one fall back to paid_at (documented)."""
    return Q(business_date=d) | Q(business_date__isnull=True, paid_at__date=d)


def _pay_bd_range(date_from, date_to):
    return Q(business_date__range=(date_from, date_to)) | Q(
        business_date__isnull=True, paid_at__date__range=(date_from, date_to)
    )


def _per_day_bd(qs):
    """Per-BUSINESS-date money series (legacy rows fall back to paid_at)."""
    rows = (
        qs.annotate(
            d=Coalesce("business_date", TruncDate("paid_at"), output_field=DateField())
        )
        .values("d")
        .annotate(n=Count("id"), total=Sum("amount"))
        .order_by("d")
    )
    return [
        {"date": str(r["d"]), "count": r["n"], "total": str(money(r["total"] or 0))}
        for r in rows
    ]


def _settled_orders_on(hotel, d):
    """Service orders whose revenue lands on business date ``d`` — folio-posted
    by the charge's business date, direct by the settlement payment's."""
    return (
        ServiceOrder.objects.filter(hotel=hotel)
        .filter(
            Q(settlement=OrderSettlement.FOLIO, posted_charge__charge_date=d)
            | Q(settlement=OrderSettlement.DIRECT, settlement_payment__business_date=d)
        )
        .exclude(status=OrderStatus.CANCELLED)
    )


def _outlet_net(hotel, d, outlet):
    ids = list(_settled_orders_on(hotel, d).filter(outlet=outlet).values_list("id", flat=True))
    if not ids:
        return ZERO
    return money(
        ServiceOrderItem.objects.filter(order_id__in=ids).aggregate(t=Sum("amount"))["t"] or 0
    )


def _revenue_day(hotel, d):
    """Revenue by category for ONE business date, from POSTED FolioCharge ONLY
    (the single financial revenue source). ``amount`` is net of tax; tax is the
    stored ``tax_amount`` (never recomputed). POS is split by outlet from the
    linked orders (operational refinement of the single ``service`` total, so
    nothing is double-counted). Room revenue is manual ChargeType.ROOM only."""
    charges = FolioCharge.objects.filter(
        hotel=hotel, charge_date=d, status=PostingStatus.POSTED
    )

    def s(qs):
        return money(qs.aggregate(t=Sum("amount"))["t"] or 0)

    room = s(charges.filter(type=ChargeType.ROOM))
    service = s(charges.filter(type=ChargeType.SERVICE))
    other = s(charges.filter(type=ChargeType.OTHER))
    adjustments = s(charges.filter(type=ChargeType.ADJUSTMENT))
    discounts = s(charges.filter(type=ChargeType.DISCOUNT))
    taxes = money(charges.aggregate(t=Sum("tax_amount"))["t"] or 0)
    restaurant = _outlet_net(hotel, d, Outlet.RESTAURANT)
    cafe = _outlet_net(hotel, d, Outlet.CAFE)
    services_manual = money(service - restaurant - cafe)
    total = money(room + service + other + adjustments + discounts)
    return {
        "room": room, "restaurant": restaurant, "cafe": cafe,
        "services": services_manual, "other": other,
        "adjustments": adjustments, "discounts": discounts,
        "taxes": taxes, "total": total,
    }


def _occupancy_day(hotel, d):
    sold = occupied_counts_by_day(hotel, d, d).get(str(d), 0)
    return {"sold_rooms": sold, "available_rooms": _sellable_capacity(hotel).count()}


def compute_day_reporting(hotel, business_date) -> dict:
    """The NEW snapshot ``reporting`` block: the figures the finance reports
    need that the Phase-12 snapshot did not already carry — revenue-by-category,
    taxes, room revenue and occupancy components. JSON-ready (strings/ints).
    Frozen at daily close; computed live for the open day. Everything else
    (payments/expenses/restaurant/folios) is read from the existing snapshot
    sections."""
    rev = _revenue_day(hotel, business_date)
    occ = _occupancy_day(hotel, business_date)
    return {
        "revenue": {k: str(money(v)) for k, v in rev.items()},
        "room_revenue": str(money(rev["room"])),
        "occupancy": occ,
        "data_quality": {
            "has_room_charges": rev["room"] != ZERO,
            "room_revenue_source": "manual_charges_only",
        },
    }


# --- Live movement/restaurant/folio blocks (SAME shape as the snapshot) -------


def _mv_live(model, hotel, d, *, with_category=False):
    posted = model.objects.filter(_pay_bd(d), hotel=hotel, status=PostingStatus.POSTED)
    originals = posted.filter(reverses__isnull=True)
    reversals = posted.filter(reverses__isnull=False)
    voided = model.objects.filter(_pay_bd(d), hotel=hotel, status=PostingStatus.VOIDED)

    def s(qs):
        return money(qs.aggregate(t=Sum("amount"))["t"] or 0)

    block = {
        "cash_total": s(originals.filter(method=PaymentMethod.CASH)),
        "non_cash_total": s(originals.exclude(method=PaymentMethod.CASH)),
        "gross_total": s(originals),
        "voided_count": voided.count(),
        "voided_total": s(voided),
        "reversals_count": reversals.count(),
        "reversals_total": s(reversals),
        "cash_reversals_total": s(reversals.filter(method=PaymentMethod.CASH)),
        "non_cash_reversals_total": s(reversals.exclude(method=PaymentMethod.CASH)),
        "by_method": {
            r["method"]: money(r["t"] or 0)
            for r in originals.values("method").annotate(t=Sum("amount"))
        },
    }
    if with_category:
        block["by_category"] = {
            r["category"]: money(r["t"] or 0)
            for r in originals.values("category").annotate(t=Sum("amount"))
        }
    return block


def _restaurant_live(hotel, d):
    settled = _settled_orders_on(hotel, d)
    direct = settled.filter(settlement=OrderSettlement.DIRECT)
    folio = settled.filter(settlement=OrderSettlement.FOLIO)

    def total(qs):
        ids = list(qs.values_list("id", flat=True))
        if not ids:
            return ZERO
        return money(
            ServiceOrderItem.objects.filter(order_id__in=ids).aggregate(t=Sum("total_amount"))["t"] or 0
        )

    # C8 — refunds on the SAME tax-exclusive basis as _outlet_net, so
    # net = gross − refunds is coherent for this analytics engine.
    from apps.services.services import outlet_refunds

    rest_sales = _outlet_net(hotel, d, Outlet.RESTAURANT)
    cafe_sales = _outlet_net(hotel, d, Outlet.CAFE)
    rest_refunds = outlet_refunds(hotel, d, Outlet.RESTAURANT, gross=False)
    cafe_refunds = outlet_refunds(hotel, d, Outlet.CAFE, gross=False)
    return {
        "restaurant_sales": rest_sales,
        "cafe_sales": cafe_sales,
        "restaurant_refunds": rest_refunds,
        "cafe_refunds": cafe_refunds,
        "restaurant_net": money(rest_sales - rest_refunds),
        "cafe_net": money(cafe_sales - cafe_refunds),
        "direct_count": direct.count(),
        "direct_total": total(direct),
        "folio_count": folio.count(),
        "folio_total": total(folio),
        "open_orders": ServiceOrder.objects.filter(
            hotel=hotel, settlement=OrderSettlement.UNSETTLED, ordered_at__date=d
        ).exclude(status=OrderStatus.CANCELLED).count(),
        "cancelled_orders": ServiceOrder.objects.filter(
            hotel=hotel, status=OrderStatus.CANCELLED, ordered_at__date=d
        ).count(),
    }


def folio_balances_now(hotel, date_from=None, date_to=None) -> dict:
    """Current open-folio balances (a point-in-time report; balances are a
    'now' concept and are never summed across days). Foreign-currency folios
    are reported separately and NEVER mixed into the hotel-currency totals."""
    from apps.finance.services import _hotel_currency, folio_balance

    hotel_ccy = _hotel_currency(hotel)
    pos_c = neg_c = zero_c = 0
    pos_a = neg_a = total = ZERO
    foreign = {}
    for f in Folio.objects.filter(hotel=hotel, status=FolioStatus.OPEN):
        bal = folio_balance(f)["balance"]
        if f.currency and f.currency != hotel_ccy:
            e = foreign.setdefault(f.currency, {"count": 0, "balance": ZERO})
            e["count"] += 1
            e["balance"] += bal
            continue
        total += bal
        if bal > ZERO:
            pos_c += 1
            pos_a += bal
        elif bal < ZERO:
            neg_c += 1
            neg_a += bal
        else:
            zero_c += 1
    closed_in_range = 0
    if date_from is not None:
        closed_in_range = Folio.objects.filter(
            hotel=hotel, status=FolioStatus.CLOSED,
            closed_at__date__range=(date_from, date_to),
        ).count()
    return {
        "currency": hotel_ccy,
        "open_folios_count": pos_c + neg_c + zero_c,
        "total_balance": str(money(total)),
        "positive_balance_count": pos_c,
        "positive_balance_amount": str(money(pos_a)),
        "negative_balance_count": neg_c,
        "negative_balance_amount": str(money(neg_a)),
        "zero_balance_count": zero_c,
        "closed_in_range": closed_in_range,
        "foreign_currency_folios": [
            {"currency": c, "count": v["count"], "balance": str(money(v["balance"]))}
            for c, v in sorted(foreign.items())
        ],
    }


# --- Day block (live open day OR frozen closed day) --------------------------


def _snap_mv(section):
    """Parse a snapshot payments/expenses section into Decimal-typed figures."""
    section = section or {}
    out = {
        "cash_total": _D(section.get("cash_total")),
        "non_cash_total": _D(section.get("non_cash_total")),
        "gross_total": _D(section.get("cash_total")) + _D(section.get("non_cash_total")),
        "voided_count": section.get("voided_count", 0) or 0,
        "voided_total": _D(section.get("voided_total")),
        "reversals_count": section.get("reversals_count", 0) or 0,
        "reversals_total": _D(section.get("reversals_total")),
        "cash_reversals_total": _D(section.get("cash_reversals_total")),
        "non_cash_reversals_total": _D(section.get("non_cash_reversals_total")),
        "by_method": {
            m: _D(v.get("total")) for m, v in (section.get("posted_by_method") or {}).items()
        },
    }
    if "posted_by_category" in section:
        out["by_category"] = {
            m: _D(v.get("total")) for m, v in (section.get("posted_by_category") or {}).items()
        }
    return out


def _snap_restaurant(section):
    section = section or {}
    return {
        "restaurant_sales": _D(section.get("restaurant_sales")),
        "cafe_sales": _D(section.get("cafe_sales")),
        # C8 — refunds/net from the stored snapshot; old snapshots without them
        # fall back to 0 refunds and net = gross.
        "restaurant_refunds": _D(section.get("restaurant_refunds")),
        "cafe_refunds": _D(section.get("cafe_refunds")),
        "restaurant_net": _D(section.get("restaurant_net", section.get("restaurant_sales"))),
        "cafe_net": _D(section.get("cafe_net", section.get("cafe_sales"))),
        "direct_count": (section.get("direct_settlements") or {}).get("count", 0) or 0,
        "direct_total": _D((section.get("direct_settlements") or {}).get("total")),
        "folio_count": (section.get("folio_postings") or {}).get("count", 0) or 0,
        "folio_total": _D((section.get("folio_postings") or {}).get("total")),
        "open_orders": section.get("open_orders_count", 0) or 0,
        "cancelled_orders": section.get("cancelled_orders_count", 0) or 0,
    }


def _empty_reporting():
    zero = str(ZERO)
    return {
        "revenue": {k: zero for k in (
            "room", "restaurant", "cafe", "services", "other",
            "adjustments", "discounts", "taxes", "total")},
        "room_revenue": zero,
        "occupancy": {"sold_rooms": 0, "available_rooms": 0},
        "data_quality": {"has_room_charges": False, "room_revenue_source": "manual_charges_only"},
    }


def _day_block(hotel, d, current_bd):
    """Normalized financial block for one business date. Returns Decimals/ints
    plus a ``source`` marker. The open day is LIVE; a closed day is read from
    its frozen snapshot; anything else is flagged and contributes nothing."""
    if d == current_bd:
        rep = compute_day_reporting(hotel, d)
        return {
            "source": "live",
            "reporting_available": True,
            "reporting": rep,
            "payments": _mv_live(Payment, hotel, d),
            "expenses": _mv_live(Expense, hotel, d, with_category=True),
            "restaurant": _restaurant_live(hotel, d),
        }
    close = DailyClose.objects.filter(
        hotel=hotel, business_date=d, status=DailyCloseStatus.CLOSED
    ).first()
    if close is None:
        return {"source": "not_closed", "reporting_available": False}
    snap = close.snapshot_json or {}
    return {
        "source": "snapshot",
        "reporting_available": "reporting" in snap,
        "reporting": snap.get("reporting") or _empty_reporting(),
        "payments": _snap_mv(snap.get("payments")),
        "expenses": _snap_mv(snap.get("expenses")),
        "restaurant": _snap_restaurant(snap.get("restaurant")),
    }


def _parse_reporting(rep):
    r = rep.get("revenue") or {}
    return {
        "revenue": {k: _D(r.get(k)) for k in (
            "room", "restaurant", "cafe", "services", "other",
            "adjustments", "discounts", "taxes", "total")},
        "room_revenue": _D(rep.get("room_revenue")),
        "sold_rooms": (rep.get("occupancy") or {}).get("sold_rooms", 0) or 0,
        "available_rooms": (rep.get("occupancy") or {}).get("available_rooms", 0) or 0,
        "has_room_charges": bool((rep.get("data_quality") or {}).get("has_room_charges")),
    }


def period_financials(hotel, date_from, date_to) -> dict:
    """Aggregate the range: closed days from snapshots, the open day LIVE once.
    Returns Decimal aggregates plus source_status, days_missing_close and
    data_availability (days closed WITHOUT a reporting block)."""
    current_bd = get_business_date(hotel)
    rev = {k: ZERO for k in (
        "room", "restaurant", "cafe", "services", "other",
        "adjustments", "discounts", "taxes", "total")}
    room_nights = 0
    available_room_days = 0
    has_room_charges = False
    reporting_missing_days = []
    pay = _mv_zero()
    exp = _mv_zero(with_category=True)
    rest = _rest_zero()
    sources = set()
    days_missing_close = []

    d = date_from
    while d <= date_to:
        if d > current_bd:
            days_missing_close.append(str(d))
            d += datetime.timedelta(days=1)
            continue
        block = _day_block(hotel, d, current_bd)
        if block["source"] == "not_closed":
            days_missing_close.append(str(d))
            d += datetime.timedelta(days=1)
            continue
        sources.add(block["source"])
        if not block["reporting_available"]:
            reporting_missing_days.append(str(d))
        pr = _parse_reporting(block["reporting"])
        for k in rev:
            rev[k] = money(rev[k] + pr["revenue"][k])
        room_nights += pr["sold_rooms"]
        available_room_days += pr["available_rooms"]
        has_room_charges = has_room_charges or pr["has_room_charges"]
        _mv_add(pay, block["payments"])
        _mv_add(exp, block["expenses"], with_category=True)
        _rest_add(rest, block["restaurant"])
        d += datetime.timedelta(days=1)

    source_status = (
        "mixed" if len(sources) > 1 else (next(iter(sources)) if sources else "none")
    )
    return {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "source_status": source_status,
        "days_missing_close": days_missing_close,
        "reporting_missing_days": reporting_missing_days,
        "revenue": rev,
        "room_revenue": rev["room"],
        "room_nights": room_nights,
        "available_room_days": available_room_days,
        "has_room_charges": has_room_charges,
        "payments": pay,
        "expenses": exp,
        "restaurant": rest,
    }


def _mv_zero(*, with_category=False):
    z = {
        "cash_total": ZERO, "non_cash_total": ZERO, "gross_total": ZERO,
        "voided_count": 0, "voided_total": ZERO,
        "reversals_count": 0, "reversals_total": ZERO,
        "cash_reversals_total": ZERO, "non_cash_reversals_total": ZERO,
        "by_method": {},
    }
    if with_category:
        z["by_category"] = {}
    return z


def _rest_zero():
    return {
        "restaurant_sales": ZERO, "cafe_sales": ZERO,
        # C8 — refunds/net accumulate alongside gross.
        "restaurant_refunds": ZERO, "cafe_refunds": ZERO,
        "restaurant_net": ZERO, "cafe_net": ZERO,
        "direct_count": 0, "direct_total": ZERO,
        "folio_count": 0, "folio_total": ZERO,
        "open_orders": 0, "cancelled_orders": 0,
    }


def _mv_add(acc, block, *, with_category=False):
    for k in ("cash_total", "non_cash_total", "gross_total", "voided_total",
              "reversals_total", "cash_reversals_total", "non_cash_reversals_total"):
        acc[k] = money(acc[k] + block[k])
    for k in ("voided_count", "reversals_count"):
        acc[k] += block[k]
    for m, v in block["by_method"].items():
        acc["by_method"][m] = money(acc["by_method"].get(m, ZERO) + v)
    if with_category:
        for cat, v in block.get("by_category", {}).items():
            acc["by_category"][cat] = money(acc["by_category"].get(cat, ZERO) + v)


def _rest_add(acc, block):
    for k in ("restaurant_sales", "cafe_sales", "restaurant_refunds",
              "cafe_refunds", "restaurant_net", "cafe_net",
              "direct_total", "folio_total"):
        acc[k] = money(acc[k] + block[k])
    for k in ("direct_count", "folio_count", "open_orders", "cancelled_orders"):
        acc[k] += block[k]


# --- KPIs (single central definition, used by overview and period) ----------


def _kpis(agg):
    room_rev = agg["room_revenue"]
    sold = agg["room_nights"]
    avail = agg["available_room_days"]
    adr = money(room_rev / Decimal(sold)) if sold else ZERO
    revpar = money(room_rev / Decimal(avail)) if avail else ZERO
    occ = money(Decimal(sold) / Decimal(avail) * Decimal("100")) if avail else ZERO
    net_pay = agg["payments"]["net"] if "net" in agg["payments"] else money(
        agg["payments"]["gross_total"] + agg["payments"]["reversals_total"]
    )
    net_exp = money(agg["expenses"]["gross_total"] + agg["expenses"]["reversals_total"])
    return {
        "occupancy_rate": str(occ),
        "adr": str(adr),
        "revpar": str(revpar),
        "total_revenue": str(agg["revenue"]["total"]),
        "room_revenue": str(room_rev),
        "restaurant_revenue": str(agg["revenue"]["restaurant"]),
        "cafe_revenue": str(agg["revenue"]["cafe"]),
        "expenses": str(net_exp),
        "net_cashflow": str(money(net_pay - net_exp)),
        "open_folio_balance": None,  # filled by the caller from folio_balances_now
    }


def _mv_out(mv):
    net = money(mv["gross_total"] + mv["reversals_total"])
    return {
        "gross": str(mv["gross_total"]),
        "cash": str(mv["cash_total"]),
        "non_cash": str(mv["non_cash_total"]),
        "by_method": {m: str(v) for m, v in sorted(mv["by_method"].items())},
        "reversals": {
            "count": mv["reversals_count"],
            "amount": str(mv["reversals_total"]),
            "cash": str(mv["cash_reversals_total"]),
            "non_cash": str(mv["non_cash_reversals_total"]),
        },
        "voided": {"count": mv["voided_count"], "amount": str(mv["voided_total"])},
        "net": str(net),
        "by_category": {c: str(v) for c, v in sorted(mv.get("by_category", {}).items())} if "by_category" in mv else None,
    }


def _revenue_out(rev):
    return {k: str(v) for k, v in rev.items()}


# --- Public report shapers ---------------------------------------------------


def finance_overview(hotel, date_from, date_to) -> dict:
    agg = period_financials(hotel, date_from, date_to)
    fol = folio_balances_now(hotel, date_from, date_to)
    kpis = _kpis(agg)
    kpis["open_folio_balance"] = fol["total_balance"]
    pay, exp = agg["payments"], agg["expenses"]
    return {
        "current_business_date": str(get_business_date(hotel)),
        "date_from": agg["date_from"], "date_to": agg["date_to"],
        "source_status": agg["source_status"],
        "days_missing_close": agg["days_missing_close"],
        "reporting_missing_days": agg["reporting_missing_days"],
        "revenue": _revenue_out(agg["revenue"]),
        "taxes": str(agg["revenue"]["taxes"]),
        "gross_payments": str(pay["gross_total"]),
        "payment_reversals": str(pay["reversals_total"]),
        "net_payments": str(money(pay["gross_total"] + pay["reversals_total"])),
        "gross_expenses": str(exp["gross_total"]),
        "expense_reversals": str(exp["reversals_total"]),
        "net_expenses": str(money(exp["gross_total"] + exp["reversals_total"])),
        "net_cashflow": kpis["net_cashflow"],
        "open_folio_balance": fol["total_balance"],
        "occupancy": kpis["occupancy_rate"],
        "adr": kpis["adr"],
        "revpar": kpis["revpar"],
        "kpis": kpis,
        "data_quality": {
            "has_room_charges": agg["has_room_charges"],
            "room_revenue_source": "manual_charges_only",
        },
    }


def revenue_report(hotel, date_from, date_to) -> dict:
    agg = period_financials(hotel, date_from, date_to)
    rev = agg["revenue"]
    net_revenue = money(rev["total"])  # net of tax; service counted once
    return {
        "date_from": agg["date_from"], "date_to": agg["date_to"],
        "source_status": agg["source_status"],
        "days_missing_close": agg["days_missing_close"],
        "reporting_missing_days": agg["reporting_missing_days"],
        "by_category": _revenue_out(rev),
        "gross_revenue": str(net_revenue),
        "adjustments": str(rev["adjustments"]),
        "discounts": str(rev["discounts"]),
        "taxes": str(rev["taxes"]),
        "net_revenue": str(net_revenue),
        "data_quality": {
            "has_room_charges": agg["has_room_charges"],
            "room_revenue_source": "manual_charges_only",
        },
    }


def payments_report(hotel, date_from, date_to) -> dict:
    agg = period_financials(hotel, date_from, date_to)
    unassigned = unassigned_movements(hotel, get_business_date(hotel))
    return {
        "date_from": agg["date_from"], "date_to": agg["date_to"],
        "source_status": agg["source_status"],
        "payments": _mv_out(agg["payments"]),
        "unassigned_movements": unassigned,
    }


def expenses_report(hotel, date_from, date_to) -> dict:
    agg = period_financials(hotel, date_from, date_to)
    return {
        "date_from": agg["date_from"], "date_to": agg["date_to"],
        "source_status": agg["source_status"],
        "expenses": _mv_out(agg["expenses"]),
    }


def tax_report(hotel, date_from, date_to) -> dict:
    agg = period_financials(hotel, date_from, date_to)
    rev = agg["revenue"]
    return {
        "date_from": agg["date_from"], "date_to": agg["date_to"],
        "source_status": agg["source_status"],
        "reporting_missing_days": agg["reporting_missing_days"],
        "total_tax": str(rev["taxes"]),
        "net_revenue_ex_tax": str(rev["total"]),
        "by_category_revenue": _revenue_out(rev),
    }


def restaurant_cafe_report(hotel, date_from, date_to) -> dict:
    agg = period_financials(hotel, date_from, date_to)
    r = agg["restaurant"]
    return {
        "date_from": agg["date_from"], "date_to": agg["date_to"],
        "source_status": agg["source_status"],
        "restaurant_sales": str(r["restaurant_sales"]),
        "cafe_sales": str(r["cafe_sales"]),
        # C8 — gross sales above; refunds and net = gross − refunds, labeled.
        "restaurant_refunds": str(r["restaurant_refunds"]),
        "cafe_refunds": str(r["cafe_refunds"]),
        "restaurant_net": str(r["restaurant_net"]),
        "cafe_net": str(r["cafe_net"]),
        "direct_settlements": {"count": r["direct_count"], "total": str(r["direct_total"])},
        "folio_postings": {"count": r["folio_count"], "total": str(r["folio_total"])},
        "open_orders_count": r["open_orders"],
        "cancelled_orders_count": r["cancelled_orders"],
    }


def folio_balances_report(hotel, date_from, date_to) -> dict:
    return folio_balances_now(hotel, date_from, date_to)


def _compare_range(hotel, cur_from, cur_to, prev_from, prev_to):
    cur = period_financials(hotel, cur_from, cur_to)
    prev = period_financials(hotel, prev_from, prev_to)

    def delta(a, b):
        a, b = money(a), money(b)
        d = money(a - b)
        pct = str(money(d / b * Decimal("100"))) if b != ZERO else None
        return {"current": str(a), "previous": str(b), "delta": str(d), "delta_pct": pct}

    return {
        "revenue_total": delta(cur["revenue"]["total"], prev["revenue"]["total"]),
        "net_payments": delta(
            money(cur["payments"]["gross_total"] + cur["payments"]["reversals_total"]),
            money(prev["payments"]["gross_total"] + prev["payments"]["reversals_total"]),
        ),
        "net_expenses": delta(
            money(cur["expenses"]["gross_total"] + cur["expenses"]["reversals_total"]),
            money(prev["expenses"]["gross_total"] + prev["expenses"]["reversals_total"]),
        ),
        "taxes": delta(cur["revenue"]["taxes"], prev["revenue"]["taxes"]),
    }


def comparisons_report(hotel) -> dict:
    """The minimal approved comparisons: current business day vs the previous
    day, and current MTD vs the same elapsed range of the previous month."""
    today = get_business_date(hotel)
    yday = today - datetime.timedelta(days=1)
    day_cmp = _compare_range(hotel, today, today, yday, yday)

    mtd_from = today.replace(day=1)
    if mtd_from.month == 1:
        prev_first = mtd_from.replace(year=mtd_from.year - 1, month=12)
    else:
        prev_first = mtd_from.replace(month=mtd_from.month - 1)
    elapsed = (today - mtd_from).days
    prev_to = prev_first + datetime.timedelta(days=elapsed)
    mtd_cmp = _compare_range(hotel, mtd_from, today, prev_first, prev_to)
    return {
        "current_business_date": str(today),
        "day_vs_previous": {"current_date": str(today), "previous_date": str(yday), **day_cmp},
        "mtd_vs_previous_month": {
            "current_range": [str(mtd_from), str(today)],
            "previous_range": [str(prev_first), str(prev_to)],
            **mtd_cmp,
        },
    }
