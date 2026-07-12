"""Shifts / handover / daily-close domain services (Phase 12) — the single
write path.

Money boundaries (deliberate):
- Nothing here CREATES or MUTATES finance records. Payments/expenses attach
  to an open shift inside ``apps.finance.services`` at creation time; this
  module only READS them to compute the drawer summary and the day snapshot.
- ``expected_cash`` = opening float + POSTED cash payments − POSTED cash
  expenses attached to the shift. Non-cash methods never touch the drawer but
  appear in the summary. Voided records are excluded everywhere.
- The daily close stores a documenting snapshot; finance records remain the
  only source of financial truth. Closing locks SAFE integrated flows for
  that business date (payment/expense creation, manual charges, service-order
  posting, shift operations). Folio + expenses closure rounds: ALL finance
  VOIDS are bound to the record's own OPEN business date — later corrections
  are linked counter-postings (adjustment / payment reversal / expense
  reversal), never edits or deletes. Daily derivations here run on the
  stamped business_date (legacy rows fall back to paid_at).
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.common.exceptions import (
    BusinessDateMismatch,
    BusinessDayClosed,
    CancellationReasonRequired,
    CashDifferenceReasonRequired,
    CrossTenantReference,
    DayAlreadyClosed,
    HandoverNotRecipient,
    OpenShiftsPreventClose,
    OperationNotEditable,
    RejectionReasonRequired,
    ResourceInUse,
    ShiftAlreadyOpen,
    ShiftNotOpen,
)
from apps.finance.models import Expense, Payment, PaymentMethod, PostingStatus
from apps.finance.services import money
from apps.rbac.services import get_active_membership
from apps.tenancy.models import HotelMembership, MembershipType

from .models import (
    DailyClose,
    DailyCloseStatus,
    DailyCloseStatusLog,
    HandoverStatus,
    Shift,
    ShiftHandover,
    ShiftHandoverStatusLog,
    ShiftStatus,
    ShiftStatusLog,
    ShiftsNumberSequence,
)

ZERO = Decimal("0.00")

NUMBER_PREFIXES = {
    "shift": "SH",
    "handover": "HO",
    "daily_close": "DC",
}


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def _is_manager(user, hotel) -> bool:
    membership = get_active_membership(user, hotel)
    return bool(membership and membership.membership_type == MembershipType.MANAGER)


def next_number(hotel, kind: str) -> str:
    """Allocate the next per-hotel SH/HO/DC number (row-locked; needs a txn)."""
    prefix = NUMBER_PREFIXES[kind]
    seq, _ = ShiftsNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel, kind=kind
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"{prefix}{seq.last_number:05d}"


# --- Business date -----------------------------------------------------------------


def _computed_business_date(hotel):
    """The timezone-derived date — used ONLY for the initial seed, display,
    and the legacy/unset fallback. Never persisted here."""
    tz_name = ""
    hotel_settings = getattr(hotel, "settings", None)
    if hotel_settings is not None:
        tz_name = (hotel_settings.timezone or "").strip()
    if tz_name:
        try:
            return timezone.now().astimezone(ZoneInfo(tz_name)).date()
        except (KeyError, ValueError):
            pass
    return timezone.localdate()


def get_business_date(hotel):
    """The hotel's ONE stored operational date (``HotelSettings.business_date``).

    It is decoupled from the wall clock: the day advances only when the daily
    close rolls it forward. Falls back to the timezone-computed date when the
    stored value is unset (legacy/new hotels before their first close) — a
    PURE read that never persists, so Prepare stays read-only. The backend is
    the only source of the business date; the frontend never decides it.
    """
    hotel_settings = getattr(hotel, "settings", None)
    if hotel_settings is not None and hotel_settings.business_date is not None:
        return hotel_settings.business_date
    return _computed_business_date(hotel)


def lock_business_date(hotel):
    """Read the operational date UNDER a row lock on ``HotelSettings`` — the
    single serialization point between a dated write (payment/expense/order/
    shift) and the daily close. Must run inside a transaction; the caller
    holds the lock until it commits, so a write and a close can never
    interleave on the same date. Falls back to the computed date (no lock)
    only when the hotel has no settings row."""
    from apps.hotels.models import HotelSettings

    row = HotelSettings.objects.select_for_update().filter(hotel=hotel).first()
    if row is None:
        return _computed_business_date(hotel)
    if row.business_date is not None:
        return row.business_date
    return _computed_business_date(hotel)


def _hotel_timezone(hotel):
    settings_obj = getattr(hotel, "settings", None)
    return (getattr(settings_obj, "timezone", "") or "UTC")


def ensure_business_day_open(hotel, on_date) -> None:
    """The Phase 12 lock: refuse SAFE integrated operations on a CLOSED day.

    Called from the central services (finance payment/expense creation,
    service-order posting, and every shifts/daily-close write). It never
    rewrites history — it only refuses NEW dated activity.
    """
    if on_date is None:
        return
    if DailyClose.objects.filter(
        hotel=hotel, business_date=on_date, status=DailyCloseStatus.CLOSED
    ).exists():
        raise BusinessDayClosed({"business_date": str(on_date)})


def get_open_shift_for(user, hotel) -> Shift | None:
    """The user's open shift in this hotel, if any — used by the finance
    services to auto-attach new payments/expenses."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return Shift.objects.filter(
        hotel=hotel, responsible_user=user, status=ShiftStatus.OPEN
    ).first()


# --- Shift ------------------------------------------------------------------------


def _shift_log(shift, previous, new, user, note=""):
    ShiftStatusLog.objects.create(
        hotel=shift.hotel,
        shift=shift,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


def _check_member(hotel, user, *, field: str) -> None:
    is_member = HotelMembership.objects.filter(
        hotel=hotel, user=user, is_active=True, user__is_active=True
    ).exists()
    if not is_member:
        raise CrossTenantReference({"field": field})


def _record(hotel, *, event_type, severity, title, message="", user=None, obj=None,
            target_user=None):
    """One shift/handover activity event through the Phase 14 system (lazy
    import keeps app loading order simple). Category ``shift`` matches the
    existing shift.closed / daily_close.closed events."""
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type=event_type,
        category="shift",
        severity=severity,
        title=title,
        message=message,
        actor=user,
        target_user=target_user,
        related_object=obj,
        related_url="/hotel/shifts",
    )


@transaction.atomic
def open_shift(
    hotel,
    *,
    user=None,
    responsible_user=None,
    opening_cash_amount=ZERO,
    opening_notes="",
    internal_notes="",
    business_date=None,
) -> Shift:
    responsible = responsible_user or user
    _check_member(hotel, responsible, field="responsible_user")
    # Serialize against the daily close on the central HotelSettings row.
    on_date = business_date or lock_business_date(hotel)
    ensure_business_day_open(hotel, on_date)
    if Shift.objects.filter(
        hotel=hotel, responsible_user=responsible, status=ShiftStatus.OPEN
    ).exists():
        raise ShiftAlreadyOpen({"responsible_user": responsible.id})
    actor = _actor(user)
    shift = Shift.objects.create(
        hotel=hotel,
        shift_number=next_number(hotel, "shift"),
        business_date=on_date,
        opened_by=actor,
        responsible_user=responsible,
        opening_cash_amount=money(opening_cash_amount),
        opening_notes=opening_notes or "",
        internal_notes=internal_notes or "",
        created_by=actor,
        updated_by=actor,
    )
    _shift_log(shift, "", ShiftStatus.OPEN, user)
    _record(
        hotel,
        event_type="shift.opened",
        severity="info",
        title=f"Shift {shift.shift_number} opened",
        message=(
            f"{responsible.full_name} · float {money(opening_cash_amount)} · "
            f"{on_date}"
        ),
        user=user,
        obj=shift,
        target_user=responsible,
    )
    return shift


@transaction.atomic
def update_shift(shift: Shift, *, user=None, **fields) -> Shift:
    """Edit an OPEN shift's notes/opening float (typo fixes). A CLOSED or
    CANCELLED shift is fully read-only — no field, not even the internal note,
    may change (final closure decision); corrections live in the finance
    services on later shifts."""
    editable = (
        ("opening_cash_amount", "opening_notes", "internal_notes")
        if shift.status == ShiftStatus.OPEN
        else ()
    )
    for field in fields:
        if field not in editable:
            raise OperationNotEditable({"status": shift.status, "field": field})
    for field, value in fields.items():
        if field == "opening_cash_amount":
            value = money(value)
        setattr(shift, field, value)
    shift.updated_by = _actor(user)
    shift.save()
    return shift


def shift_cash_summary(shift: Shift) -> dict:
    """The drawer math, straight from POSTED finance records attached to the
    shift. Cash drives the expected amount; other methods are informational."""
    payments = Payment.objects.filter(shift=shift, status=PostingStatus.POSTED)
    expenses = Expense.objects.filter(shift=shift, status=PostingStatus.POSTED)

    def by_method(qs):
        return {
            row["method"]: {
                "count": row["n"],
                "total": str(money(row["total"] or 0)),
            }
            for row in qs.values("method").annotate(n=Count("id"), total=Sum("amount"))
        }

    cash_in = money(
        payments.filter(method=PaymentMethod.CASH).aggregate(t=Sum("amount"))["t"] or 0
    )
    cash_out = money(
        expenses.filter(method=PaymentMethod.CASH).aggregate(t=Sum("amount"))["t"] or 0
    )
    expected = money(Decimal(shift.opening_cash_amount) + cash_in - cash_out)
    return {
        "opening_cash": money(shift.opening_cash_amount),
        "cash_payments_total": cash_in,
        "cash_expenses_total": cash_out,
        "expected_cash": expected,
        "payments_count": payments.count(),
        "expenses_count": expenses.count(),
        "payments_by_method": by_method(payments),
        "expenses_by_method": by_method(expenses),
    }


@transaction.atomic
def close_shift(
    shift: Shift,
    *,
    user=None,
    actual_cash_amount,
    difference_reason="",
    closing_notes="",
) -> Shift:
    # Row-lock so two concurrent closes cannot both pass.
    shift = Shift.objects.select_for_update().get(pk=shift.pk)
    if shift.status != ShiftStatus.OPEN:
        raise ShiftNotOpen({"status": shift.status})
    ensure_business_day_open(shift.hotel, shift.business_date)
    summary = shift_cash_summary(shift)
    expected = summary["expected_cash"]
    actual = money(actual_cash_amount)
    difference = money(actual - expected)
    if difference != ZERO and not (difference_reason or "").strip():
        raise CashDifferenceReasonRequired({"difference": str(difference)})
    shift.status = ShiftStatus.CLOSED
    shift.closed_at = timezone.now()
    shift.expected_cash_amount = expected
    shift.actual_cash_amount = actual
    shift.cash_difference = difference
    shift.difference_reason = (difference_reason or "").strip()
    shift.closing_notes = closing_notes or ""
    shift.updated_by = _actor(user)
    shift.save()
    _shift_log(shift, ShiftStatus.OPEN, ShiftStatus.CLOSED, user, shift.difference_reason)
    # Phase 14: activity + notifications (lazy import).
    from apps.notifications.services import record_activity

    record_activity(
        shift.hotel,
        event_type="shift.closed",
        category="shift",
        severity="warning" if difference != ZERO else "success",
        title=f"Shift {shift.shift_number} closed",
        message=(
            f"Expected {expected} · counted {actual} · difference {difference}"
        ),
        actor=user,
        related_object=shift,
        related_url="/hotel/shifts",
    )
    return shift


@transaction.atomic
def cancel_shift(shift: Shift, *, reason, user=None) -> Shift:
    """Cancel a shift opened by mistake. A shift that already has POSTED
    movements attached carries drawer accountability and must be CLOSED
    properly instead (documented rule)."""
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    if shift.status != ShiftStatus.OPEN:
        raise ShiftNotOpen({"status": shift.status})
    has_movements = (
        Payment.objects.filter(shift=shift, status=PostingStatus.POSTED).exists()
        or Expense.objects.filter(shift=shift, status=PostingStatus.POSTED).exists()
    )
    if has_movements:
        raise ResourceInUse({"reason": "shift_has_movements"})
    shift.status = ShiftStatus.CANCELLED
    shift.cancelled_at = timezone.now()
    shift.cancellation_reason = reason.strip()
    shift.updated_by = _actor(user)
    shift.save()
    _shift_log(shift, ShiftStatus.OPEN, ShiftStatus.CANCELLED, user, reason.strip())
    _record(
        shift.hotel,
        event_type="shift.cancelled",
        severity="warning",
        title=f"Shift {shift.shift_number} cancelled",
        message=reason.strip(),
        user=user,
        obj=shift,
        target_user=shift.responsible_user,
    )
    return shift


def _on_business_date(on_date):
    """Expenses closure: daily derivations run on the stamped BUSINESS date;
    legacy rows without one fall back to their paid_at calendar date."""
    from django.db.models import Q

    return Q(business_date=on_date) | Q(
        business_date__isnull=True, paid_at__date=on_date
    )


def unassigned_movements(hotel, on_date) -> dict:
    """POSTED payments/expenses dated to the business date with NO shift —
    reported (never hidden) so the drawer story stays honest."""
    payments = Payment.objects.filter(
        _on_business_date(on_date),
        hotel=hotel, shift__isnull=True, status=PostingStatus.POSTED,
    )
    expenses = Expense.objects.filter(
        _on_business_date(on_date),
        hotel=hotel, shift__isnull=True, status=PostingStatus.POSTED,
    )
    return {
        "payments_count": payments.count(),
        "payments_total": str(money(payments.aggregate(t=Sum("amount"))["t"] or 0)),
        "expenses_count": expenses.count(),
        "expenses_total": str(money(expenses.aggregate(t=Sum("amount"))["t"] or 0)),
    }


# --- Handover -----------------------------------------------------------------------


def _ho_log(handover, previous, new, user, note=""):
    ShiftHandoverStatusLog.objects.create(
        hotel=handover.hotel,
        handover=handover,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


HANDOVER_EDITABLE_STATUSES = (HandoverStatus.DRAFT,)
HANDOVER_OPEN_STATUSES = (HandoverStatus.DRAFT, HandoverStatus.SUBMITTED)

HANDOVER_NOTE_FIELDS = (
    "summary_notes",
    "pending_tasks_notes",
    "cash_notes",
    "guest_notes",
    "maintenance_notes",
    "lost_found_notes",
)


@transaction.atomic
def create_handover(hotel, *, user=None, from_shift, to_user, **notes) -> ShiftHandover:
    if from_shift.hotel_id != hotel.id:
        raise CrossTenantReference({"field": "from_shift"})
    if from_shift.status not in (ShiftStatus.OPEN, ShiftStatus.CLOSED):
        raise ShiftNotOpen({"status": from_shift.status})
    _check_member(hotel, to_user, field="to_user")
    actor = _actor(user)
    handover = ShiftHandover.objects.create(
        hotel=hotel,
        handover_number=next_number(hotel, "handover"),
        from_shift=from_shift,
        to_user=to_user,
        created_by=actor,
        updated_by=actor,
        **{k: (notes.get(k) or "") for k in HANDOVER_NOTE_FIELDS},
    )
    _ho_log(handover, "", HandoverStatus.DRAFT, user)
    return handover


@transaction.atomic
def update_handover(handover: ShiftHandover, *, user=None, to_user=None, **notes) -> ShiftHandover:
    if handover.status not in HANDOVER_EDITABLE_STATUSES:
        raise OperationNotEditable({"status": handover.status})
    if to_user is not None:
        _check_member(handover.hotel, to_user, field="to_user")
        handover.to_user = to_user
    for field in HANDOVER_NOTE_FIELDS:
        if field in notes:
            setattr(handover, field, notes[field] or "")
    handover.updated_by = _actor(user)
    handover.save()
    return handover


@transaction.atomic
def submit_handover(handover: ShiftHandover, *, user=None) -> ShiftHandover:
    if handover.status != HandoverStatus.DRAFT:
        raise OperationNotEditable({"status": handover.status})
    handover.status = HandoverStatus.SUBMITTED
    handover.submitted_at = timezone.now()
    handover.updated_by = _actor(user)
    handover.save()
    _ho_log(handover, HandoverStatus.DRAFT, HandoverStatus.SUBMITTED, user)
    _record(
        handover.hotel,
        event_type="handover.submitted",
        severity="info",
        title=f"Handover {handover.handover_number} submitted",
        message=f"{handover.from_shift.shift_number} → {handover.to_user.full_name}",
        user=user,
        obj=handover,
        target_user=handover.to_user,
    )
    return handover


def _guard_recipient(handover: ShiftHandover, user) -> None:
    """Only the designated recipient — or a manager — may accept/reject."""
    if user is not None and user.id == handover.to_user_id:
        return
    if _is_manager(user, handover.hotel):
        return
    raise HandoverNotRecipient()


@transaction.atomic
def accept_handover(handover: ShiftHandover, *, user=None, note="") -> ShiftHandover:
    if handover.status != HandoverStatus.SUBMITTED:
        raise OperationNotEditable({"status": handover.status})
    _guard_recipient(handover, user)
    handover.status = HandoverStatus.ACCEPTED
    handover.accepted_at = timezone.now()
    handover.updated_by = _actor(user)
    handover.save()
    _ho_log(handover, HandoverStatus.SUBMITTED, HandoverStatus.ACCEPTED, user, note)
    _record(
        handover.hotel,
        event_type="handover.accepted",
        severity="success",
        title=f"Handover {handover.handover_number} accepted",
        message=(note or "").strip(),
        user=user,
        obj=handover,
        target_user=handover.to_user,
    )
    return handover


@transaction.atomic
def reject_handover(handover: ShiftHandover, *, user=None, reason) -> ShiftHandover:
    if handover.status != HandoverStatus.SUBMITTED:
        raise OperationNotEditable({"status": handover.status})
    _guard_recipient(handover, user)
    if not (reason or "").strip():
        raise RejectionReasonRequired()
    handover.status = HandoverStatus.REJECTED
    handover.rejected_at = timezone.now()
    handover.rejection_reason = reason.strip()
    handover.updated_by = _actor(user)
    handover.save()
    _ho_log(handover, HandoverStatus.SUBMITTED, HandoverStatus.REJECTED, user, reason.strip())
    _record(
        handover.hotel,
        event_type="handover.rejected",
        severity="danger",
        title=f"Handover {handover.handover_number} rejected",
        message=reason.strip(),
        user=user,
        obj=handover,
        target_user=handover.to_user,
    )
    return handover


@transaction.atomic
def cancel_handover(handover: ShiftHandover, *, user=None, reason) -> ShiftHandover:
    if handover.status not in HANDOVER_OPEN_STATUSES:
        raise OperationNotEditable({"status": handover.status})
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    previous = handover.status
    handover.status = HandoverStatus.CANCELLED
    handover.cancelled_at = timezone.now()
    handover.cancellation_reason = reason.strip()
    handover.updated_by = _actor(user)
    handover.save()
    _ho_log(handover, previous, HandoverStatus.CANCELLED, user, reason.strip())
    _record(
        handover.hotel,
        event_type="handover.cancelled",
        severity="warning",
        title=f"Handover {handover.handover_number} cancelled",
        message=reason.strip(),
        user=user,
        obj=handover,
        target_user=handover.to_user,
    )
    return handover


# --- Daily close ---------------------------------------------------------------------


def _dc_log(close, previous, new, user, note=""):
    DailyCloseStatusLog.objects.create(
        hotel=close.hotel,
        daily_close=close,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


def _hotel_currency_safe(hotel):
    settings_obj = getattr(hotel, "settings", None)
    return (getattr(settings_obj, "default_currency", "") or "USD")


def _money_str(value):
    return str(money(value or 0))


def _shifts_block(hotel, business_date):
    shifts = list(
        Shift.objects.filter(hotel=hotel, business_date=business_date)
        .select_related("responsible_user")
    )
    closed = [s for s in shifts if s.status == ShiftStatus.CLOSED]
    cancelled = [s for s in shifts if s.status == ShiftStatus.CANCELLED]
    with_diff = [s for s in closed if money(s.cash_difference) != ZERO]
    return {
        "closed_shifts_count": len(closed),
        "cancelled_shifts_count": len(cancelled),
        "opening_balances_total": str(money(sum((s.opening_cash_amount for s in shifts), ZERO))),
        "expected_cash_total": str(money(sum((s.expected_cash_amount for s in closed), ZERO))),
        "actual_cash_total": str(money(sum(((s.actual_cash_amount or ZERO) for s in closed), ZERO))),
        "difference_total": str(money(sum((s.cash_difference for s in closed), ZERO))),
        "shifts_with_difference_count": len(with_diff),
        "difference_reasons_summary": [s.difference_reason for s in with_diff if s.difference_reason],
        "items": [
            {
                "shift_number": s.shift_number,
                "status": s.status,
                "responsible": s.responsible_user.full_name,
                "opening_cash": str(money(s.opening_cash_amount)),
                "expected_cash": str(money(s.expected_cash_amount)),
                "actual_cash": (
                    str(money(s.actual_cash_amount))
                    if s.actual_cash_amount is not None else None
                ),
                "cash_difference": str(money(s.cash_difference)),
            }
            for s in shifts
        ],
    }


def _movements_block(hotel, business_date, model, *, with_category=False):
    """Shared payments/expenses roll-up: originals by method (and category),
    cash/non-cash, voided, and reversals — the original and its reverse are
    NEVER merged into a single figure."""
    qs = model.objects.filter(_on_business_date(business_date), hotel=hotel)
    posted = qs.filter(status=PostingStatus.POSTED)
    originals = posted.filter(reverses__isnull=True)
    reversals = posted.filter(reverses__isnull=False)
    voided = qs.filter(status=PostingStatus.VOIDED)
    block = {
        "posted_by_method": {
            row["method"]: {"count": row["n"], "total": _money_str(row["t"])}
            for row in originals.values("method").annotate(n=Count("id"), t=Sum("amount"))
        },
        "cash_total": _money_str(
            originals.filter(method=PaymentMethod.CASH).aggregate(t=Sum("amount"))["t"]
        ),
        "non_cash_total": _money_str(
            originals.exclude(method=PaymentMethod.CASH).aggregate(t=Sum("amount"))["t"]
        ),
        "voided_count": voided.count(),
        "voided_total": _money_str(voided.aggregate(t=Sum("amount"))["t"]),
        "reversals_count": reversals.count(),
        "reversals_total": _money_str(reversals.aggregate(t=Sum("amount"))["t"]),
        "cash_reversals_total": _money_str(
            reversals.filter(method=PaymentMethod.CASH).aggregate(t=Sum("amount"))["t"]
        ),
        "non_cash_reversals_total": _money_str(
            reversals.exclude(method=PaymentMethod.CASH).aggregate(t=Sum("amount"))["t"]
        ),
    }
    if with_category:
        block["posted_by_category"] = {
            row["category"]: {"count": row["n"], "total": _money_str(row["t"])}
            for row in originals.values("category").annotate(n=Count("id"), t=Sum("amount"))
        }
    return block


def _unassigned_breakdown(hotel, business_date):
    """Shiftless CASH movements with originals and reversals SEPARATED so the
    story stays auditable. Reported, never blocking."""
    pay = Payment.objects.filter(
        _on_business_date(business_date), hotel=hotel, shift__isnull=True,
        status=PostingStatus.POSTED, method=PaymentMethod.CASH,
    )
    exp = Expense.objects.filter(
        _on_business_date(business_date), hotel=hotel, shift__isnull=True,
        status=PostingStatus.POSTED, method=PaymentMethod.CASH,
    )

    def bucket(qs):
        a = qs.aggregate(n=Count("id"), t=Sum("amount"))
        return {"count": a["n"] or 0, "total": _money_str(a["t"])}

    p = Decimal(pay.filter(reverses__isnull=True).aggregate(t=Sum("amount"))["t"] or 0)
    pr = Decimal(pay.filter(reverses__isnull=False).aggregate(t=Sum("amount"))["t"] or 0)
    e = Decimal(exp.filter(reverses__isnull=True).aggregate(t=Sum("amount"))["t"] or 0)
    er = Decimal(exp.filter(reverses__isnull=False).aggregate(t=Sum("amount"))["t"] or 0)
    return {
        "cash_payments": bucket(pay.filter(reverses__isnull=True)),
        "cash_expenses": bucket(exp.filter(reverses__isnull=True)),
        "cash_payment_reversals": bucket(pay.filter(reverses__isnull=False)),
        "cash_expense_reversals": bucket(exp.filter(reverses__isnull=False)),
        "net_cash": str(money(p + pr - e - er)),
    }


def _restaurant_block(hotel, business_date):
    from apps.services.models import (
        OrderSettlement, OrderStatus, Outlet, ServiceOrder,
    )

    def outlet_sales(outlet):
        folio_q = ServiceOrder.objects.filter(
            hotel=hotel, outlet=outlet, settlement=OrderSettlement.FOLIO,
            posted_at__date=business_date,
        ).select_related("posted_charge")
        direct_q = ServiceOrder.objects.filter(
            hotel=hotel, outlet=outlet, settlement=OrderSettlement.DIRECT,
            settled_at__date=business_date,
        ).select_related("settlement_payment")
        folio_total = sum(
            (money(o.posted_charge.total_amount) for o in folio_q if o.posted_charge), ZERO
        )
        direct_total = sum(
            (money(o.settlement_payment.amount) for o in direct_q if o.settlement_payment), ZERO
        )
        return str(money(folio_total + direct_total))

    direct = ServiceOrder.objects.filter(
        hotel=hotel, settlement=OrderSettlement.DIRECT, settled_at__date=business_date
    ).select_related("settlement_payment")
    folio = ServiceOrder.objects.filter(
        hotel=hotel, settlement=OrderSettlement.FOLIO, posted_at__date=business_date
    ).select_related("posted_charge")
    return {
        "restaurant_sales": outlet_sales(Outlet.RESTAURANT),
        "cafe_sales": outlet_sales(Outlet.CAFE),
        "direct_settlements": {
            "count": direct.count(),
            "total": str(money(sum(
                (money(o.settlement_payment.amount) for o in direct if o.settlement_payment), ZERO
            ))),
        },
        "folio_postings": {
            "count": folio.count(),
            "total": str(money(sum(
                (money(o.posted_charge.total_amount) for o in folio if o.posted_charge), ZERO
            ))),
        },
        "open_orders_count": ServiceOrder.objects.filter(
            hotel=hotel, settlement=OrderSettlement.UNSETTLED
        ).exclude(status=OrderStatus.CANCELLED).count(),
        "cancelled_orders_count": ServiceOrder.objects.filter(
            hotel=hotel, status=OrderStatus.CANCELLED, ordered_at__date=business_date
        ).count(),
    }


def _folios_block(hotel, business_date):
    from apps.finance.models import Folio, FolioStatus
    from apps.finance.services import _hotel_currency, folio_balance

    hotel_ccy = _hotel_currency(hotel)
    open_folios = list(Folio.objects.filter(hotel=hotel, status=FolioStatus.OPEN))
    pos_count = neg_count = zero_count = 0
    pos_amt = neg_amt = total = ZERO
    foreign = {}
    for f in open_folios:
        bal = folio_balance(f)["balance"]
        if f.currency and f.currency != hotel_ccy:
            entry = foreign.setdefault(f.currency, {"count": 0, "balance": ZERO})
            entry["count"] += 1
            entry["balance"] += bal
            continue
        total += bal
        if bal > ZERO:
            pos_count += 1
            pos_amt += bal
        elif bal < ZERO:
            neg_count += 1
            neg_amt += bal
        else:
            zero_count += 1
    return {
        "open_folios_count": len(open_folios),
        "total_balance": str(money(total)),
        "positive_balance_count": pos_count,
        "positive_balance_amount": str(money(pos_amt)),
        "negative_balance_count": neg_count,
        "negative_balance_amount": str(money(neg_amt)),
        "zero_balance_count": zero_count,
        "folios_closed_during_day": Folio.objects.filter(
            hotel=hotel, status=FolioStatus.CLOSED, closed_at__date=business_date
        ).count(),
        "foreign_currency_folios": [
            {"currency": c, "count": v["count"], "balance": str(money(v["balance"]))}
            for c, v in sorted(foreign.items())
        ],
    }


def _operations_block(hotel, business_date):
    from apps.operations.models import (
        HousekeepingStatus, HousekeepingTask, LostFoundItem, LostFoundStatus,
        MaintenanceRequest, MaintenanceStatus,
    )
    from apps.reservations.models import Reservation, ReservationStatus
    from apps.rooms.models import Room, RoomStatus
    from apps.stays.models import Stay, StayStatus

    in_house = Stay.objects.filter(hotel=hotel, status=StayStatus.IN_HOUSE)
    arrivals = (
        Reservation.objects.filter(
            hotel=hotel, check_in_date=business_date,
            status__in=(ReservationStatus.CONFIRMED, ReservationStatus.HELD),
        )
        .annotate(_n=Count("stays"))
        .filter(_n=0)
    )
    return {
        "in_house_stays": in_house.count(),
        "arrivals_not_checked_in": arrivals.count(),
        "overdue_departures": in_house.filter(
            planned_check_out_date__lte=business_date
        ).count(),
        "open_housekeeping_tasks": HousekeepingTask.objects.filter(hotel=hotel)
        .exclude(status__in=(HousekeepingStatus.COMPLETED, HousekeepingStatus.CANCELLED))
        .count(),
        "open_maintenance_requests": MaintenanceRequest.objects.filter(hotel=hotel)
        .exclude(
            status__in=(
                MaintenanceStatus.RESOLVED, MaintenanceStatus.CLOSED,
                MaintenanceStatus.CANCELLED,
            )
        )
        .count(),
        "not_ready_rooms": Room.objects.filter(hotel=hotel)
        .exclude(status=RoomStatus.AVAILABLE)
        .count(),
        "open_lost_found_records": LostFoundItem.objects.filter(hotel=hotel)
        .exclude(
            status__in=(
                LostFoundStatus.RETURNED, LostFoundStatus.DISPOSED,
                LostFoundStatus.CLOSED,
            )
        )
        .count(),
    }


def _daily_sections(hotel, business_date):
    """Every read-only section of one business date, from EXISTING records —
    nothing is recomputed as new financial truth."""
    return {
        "shifts": _shifts_block(hotel, business_date),
        "payments": _movements_block(hotel, business_date, Payment),
        "expenses": _movements_block(hotel, business_date, Expense, with_category=True),
        "restaurant": _restaurant_block(hotel, business_date),
        "folios": _folios_block(hotel, business_date),
        "operations": _operations_block(hotel, business_date),
        "unassigned_movements": _unassigned_breakdown(hotel, business_date),
    }


def _classify(hotel, business_date, sections):
    """The three exception classes. ONLY an open shift blocks; everything else
    is a warning or informational, and nothing here changes any state."""
    open_shifts = list(
        Shift.objects.filter(
            hotel=hotel, business_date=business_date, status=ShiftStatus.OPEN
        ).values_list("shift_number", flat=True)
    )
    blocking = []
    if open_shifts:
        blocking.append(
            {"code": "open_shifts", "count": len(open_shifts), "shifts": open_shifts}
        )

    warnings = []
    pending = ShiftHandover.objects.filter(
        hotel=hotel, status=HandoverStatus.SUBMITTED,
        from_shift__business_date=business_date,
    ).count()
    if pending:
        warnings.append({"code": "pending_handovers", "count": pending})
    ops = sections["operations"]
    if ops["overdue_departures"]:
        warnings.append({"code": "overdue_departures", "count": ops["overdue_departures"]})
    if ops["arrivals_not_checked_in"]:
        warnings.append(
            {"code": "arrivals_not_checked_in", "count": ops["arrivals_not_checked_in"]}
        )
    if sections["restaurant"]["open_orders_count"]:
        warnings.append(
            {"code": "open_service_orders", "count": sections["restaurant"]["open_orders_count"]}
        )

    informational = []
    fol = sections["folios"]
    if fol["open_folios_count"]:
        informational.append(
            {"code": "open_folios", "count": fol["open_folios_count"],
             "total_balance": fol["total_balance"]}
        )
    for key in (
        "open_housekeeping_tasks", "open_maintenance_requests",
        "not_ready_rooms", "open_lost_found_records",
    ):
        if ops[key]:
            informational.append({"code": key, "count": ops[key]})
    un = sections["unassigned_movements"]
    if any(
        un[k]["count"]
        for k in ("cash_payments", "cash_expenses",
                  "cash_payment_reversals", "cash_expense_reversals")
    ):
        informational.append({"code": "unassigned_movements", "net_cash": un["net_cash"]})
    return blocking, warnings, informational


def _totals_from(sections):
    p, e = sections["payments"], sections["expenses"]
    sh, r = sections["shifts"], sections["restaurant"]
    return {
        "payments_cash_total": p["cash_total"],
        "payments_non_cash_total": p["non_cash_total"],
        "expenses_cash_total": e["cash_total"],
        "expenses_non_cash_total": e["non_cash_total"],
        "restaurant_sales": r["restaurant_sales"],
        "cafe_sales": r["cafe_sales"],
        "shifts_count": sh["closed_shifts_count"] + sh["cancelled_shifts_count"],
        "expected_cash_total": sh["expected_cash_total"],
        "actual_cash_total": sh["actual_cash_total"],
        "difference_total": sh["difference_total"],
    }


def build_daily_snapshot(hotel, business_date):
    """The immutable documenting snapshot of one business date, from EXISTING
    records only. Returns (snapshot, totals). Built at CLOSE — never by
    Prepare. Stores totals/counters/refs, never full record copies."""
    sections = _daily_sections(hotel, business_date)
    blocking, warnings, informational = _classify(hotel, business_date, sections)
    snapshot = {
        "identity": {
            "hotel_id": hotel.id,
            "business_date": str(business_date),
            "previous_business_date": str(business_date - datetime.timedelta(days=1)),
            "next_business_date": str(business_date + datetime.timedelta(days=1)),
            "timezone": _hotel_timezone(hotel),
            "currency": _hotel_currency_safe(hotel),
        },
        "shifts": sections["shifts"],
        "payments": sections["payments"],
        "expenses": sections["expenses"],
        "restaurant": sections["restaurant"],
        "folios": sections["folios"],
        "operations": sections["operations"],
        "exceptions": {
            "blocking_errors": blocking,
            "warnings": warnings,
            "informational_alerts": informational,
            "unassigned_movements": sections["unassigned_movements"],
        },
        "business_date": str(business_date),
    }
    # Finance & Reports final closure: freeze the reporting block (revenue by
    # category, taxes, occupancy, room revenue) so closed days are reportable
    # without recomputing from live tables. Lazy import avoids an app cycle.
    from apps.reports.services import compute_day_reporting

    snapshot["reporting"] = compute_day_reporting(hotel, business_date)
    return snapshot, _totals_from(sections)


def prepare_daily_close(hotel, business_date, *, user=None, notes=""):
    """READ-ONLY preview of a business date. Writes NOTHING — no DailyClose,
    no DRAFT, no snapshot, no activity, no business-date change — and is fully
    repeatable with no side effects. Reads live records at call time and
    returns the three exception classes plus preview totals."""
    sections = _daily_sections(hotel, business_date)
    blocking, warnings, informational = _classify(hotel, business_date, sections)
    return {
        "business_date": str(business_date),
        "can_close": not blocking,
        "blocking_errors": blocking,
        "warnings": warnings,
        "informational_alerts": informational,
        "preview_totals": _totals_from(sections),
    }


@transaction.atomic
def close_business_day(hotel, business_date, *, user=None, notes=""):
    """Close ONE business date atomically, then roll the hotel's stored
    business_date forward by exactly one day. Only an OPEN shift blocks; a date
    can be closed ONCE; nothing is deleted or rewritten. A pending handover is
    a warning, not a blocker."""
    from apps.hotels.models import HotelSettings

    # 1) central lock  2) read the stored date UNDER it.
    settings_row = (
        HotelSettings.objects.select_for_update().filter(hotel=hotel).first()
    )
    current = (
        settings_row.business_date
        if settings_row is not None and settings_row.business_date is not None
        else _computed_business_date(hotel)
    )
    # 3-4) the close only ever targets the current open date.
    if business_date != current:
        raise BusinessDateMismatch(
            {"expected": str(current), "requested": str(business_date)}
        )
    # 5-6) lock/get the day's close; reject if already closed (reuse a DRAFT).
    existing = (
        DailyClose.objects.select_for_update()
        .filter(hotel=hotel, business_date=current)
        .first()
    )
    if existing is not None and existing.status == DailyCloseStatus.CLOSED:
        raise DayAlreadyClosed({"business_date": str(current)})
    # 7-9) re-check the ONE blocker under the lock.
    open_count = Shift.objects.filter(
        hotel=hotel, business_date=current, status=ShiftStatus.OPEN
    ).count()
    if open_count:
        raise OpenShiftsPreventClose({"open_shifts": open_count})
    # 10-11) build the final snapshot (warnings/info never block).
    snapshot, totals = build_daily_snapshot(hotel, current)
    # 12) persist the close.
    if existing is None:
        close = DailyClose.objects.create(
            hotel=hotel,
            close_number=next_number(hotel, "daily_close"),
            business_date=current,
            snapshot_json=snapshot,
            totals_json=totals,
            notes=notes or "",
        )
        _dc_log(close, "", DailyCloseStatus.DRAFT, user)
    else:
        close = existing
        close.snapshot_json = snapshot
        close.totals_json = totals
        if notes:
            close.notes = notes
    close.status = DailyCloseStatus.CLOSED
    close.closed_by = _actor(user)
    close.closed_at = timezone.now()
    close.save()
    _dc_log(close, DailyCloseStatus.DRAFT, DailyCloseStatus.CLOSED, user, notes)
    # 13) roll the stored business date forward by exactly one day.
    next_date = current + datetime.timedelta(days=1)
    if settings_row is not None:
        settings_row.business_date = next_date
        settings_row.save(update_fields=["business_date", "updated_at"])
    # 14) success activity — after all state is set, still inside the atomic
    # block so any failure rolls the whole close back.
    exc = snapshot["exceptions"]
    un = exc["unassigned_movements"]
    un_count = sum(
        un[k]["count"]
        for k in ("cash_payments", "cash_expenses",
                  "cash_payment_reversals", "cash_expense_reversals")
    )
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="daily_close.closed",
        category="shift",
        severity="success",
        title=f"Business day {current} closed ({close.close_number})",
        message=(
            f"{current} → {next_date} · warnings {len(exc['warnings'])} · "
            f"info {len(exc['informational_alerts'])} · unassigned {un_count}"
        ),
        actor=user,
        related_object=close,
        related_url="/hotel/shifts",
    )
    return close
