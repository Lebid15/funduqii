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

from django.db.models import Avg, Count, F, Q, Sum

from apps.finance.models import (
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
from apps.services.models import OrderStatus, ServiceOrder, ServiceOrderItem
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
    """Rooms counted as sellable capacity: active and not archived."""
    return Room.objects.filter(hotel=hotel, is_active=True).exclude(
        status=RoomStatus.ARCHIVED
    )


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
    payments = Payment.objects.filter(
        hotel=hotel, status=PostingStatus.POSTED,
        paid_at__date__range=(date_from, date_to),
    )
    expenses = Expense.objects.filter(
        hotel=hotel, status=PostingStatus.POSTED,
        paid_at__date__range=(date_from, date_to),
    )
    total_payments = _amount(payments)
    total_expenses = _amount(expenses)
    orders = ServiceOrder.objects.filter(
        hotel=hotel, ordered_at__date__range=(date_from, date_to)
    )
    posted_orders = ServiceOrder.objects.filter(
        hotel=hotel, posted_at__date__range=(date_from, date_to)
    ).select_related("posted_charge")
    posted_total = money(
        sum(
            (money(o.posted_charge.total_amount) for o in posted_orders if o.posted_charge),
            ZERO,
        )
    )
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
        "total_payments": str(total_payments),
        "total_expenses": str(total_expenses),
        "net_cashflow_simple": str(money(total_payments - total_expenses)),
        "service_orders_total": orders.count(),
        "service_orders_posted_total": str(posted_total),
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
        hotel=hotel, status=PostingStatus.POSTED,
        paid_at__date__range=(date_from, date_to),
    )
    expenses = Expense.objects.filter(
        hotel=hotel, status=PostingStatus.POSTED,
        paid_at__date__range=(date_from, date_to),
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
        "payments_by_day": _per_day(payments, "paid_at"),
        "expenses_by_category": _by(expenses, "category", amount=True),
        "expenses_by_day": _per_day(expenses, "paid_at"),
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
