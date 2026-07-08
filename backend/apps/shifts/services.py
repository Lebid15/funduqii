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
  that business date (payment/expense creation, service-order posting, shift
  operations) — finance VOIDS stay allowed by design (corrections keep
  Phase 8 rules: void with a reason, never delete).
"""
from __future__ import annotations

from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.common.exceptions import (
    BusinessDayClosed,
    CancellationReasonRequired,
    CashDifferenceReasonRequired,
    CrossTenantReference,
    DayAlreadyClosed,
    HandoverNotRecipient,
    OpenShiftsPreventClose,
    OperationNotEditable,
    PendingHandoversPreventClose,
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


def get_business_date(hotel):
    """Today's operational date in the HOTEL's timezone.

    Uses ``HotelSettings.timezone`` when present/valid; otherwise falls back
    to the server timezone (documented default). The backend is the only
    source of the business date — the frontend never decides it.
    """
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
    on_date = business_date or get_business_date(hotel)
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
    return shift


@transaction.atomic
def update_shift(shift: Shift, *, user=None, **fields) -> Shift:
    """Edit an OPEN shift's notes/opening float (typo fixes). Closed and
    cancelled shifts are history — only ``internal_notes`` (the limited
    managerial remark) stays writable on them."""
    editable = (
        ("opening_cash_amount", "opening_notes", "internal_notes")
        if shift.status == ShiftStatus.OPEN
        else ("internal_notes",)
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
    return shift


def unassigned_movements(hotel, on_date) -> dict:
    """POSTED payments/expenses dated to the business date with NO shift —
    reported (never hidden) so the drawer story stays honest."""
    payments = Payment.objects.filter(
        hotel=hotel, shift__isnull=True, status=PostingStatus.POSTED,
        paid_at__date=on_date,
    )
    expenses = Expense.objects.filter(
        hotel=hotel, shift__isnull=True, status=PostingStatus.POSTED,
        paid_at__date=on_date,
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


def build_daily_snapshot(hotel, business_date) -> tuple[dict, dict]:
    """A documenting snapshot of the date from EXISTING records — nothing is
    recomputed as new financial truth. Returns (snapshot, totals)."""
    from apps.services.models import ServiceOrder
    from apps.stays.models import Stay

    payments = Payment.objects.filter(hotel=hotel, paid_at__date=business_date)
    expenses = Expense.objects.filter(hotel=hotel, paid_at__date=business_date)
    posted_orders = ServiceOrder.objects.filter(
        hotel=hotel, posted_at__date=business_date
    )
    shifts = Shift.objects.filter(hotel=hotel, business_date=business_date)
    pending_handovers = ShiftHandover.objects.filter(
        hotel=hotel,
        status=HandoverStatus.SUBMITTED,
        from_shift__business_date=business_date,
    )
    arrivals = Stay.objects.filter(
        hotel=hotel, actual_check_in_at__date=business_date
    ).count()
    departures = Stay.objects.filter(
        hotel=hotel, actual_check_out_at__date=business_date
    ).count()

    def money_block(qs):
        posted = qs.filter(status=PostingStatus.POSTED)
        return {
            "count": posted.count(),
            "total": str(money(posted.aggregate(t=Sum("amount"))["t"] or 0)),
            "cash_total": str(
                money(
                    posted.filter(method=PaymentMethod.CASH).aggregate(t=Sum("amount"))["t"]
                    or 0
                )
            ),
            "voided_count": qs.filter(status=PostingStatus.VOIDED).count(),
        }

    payments_block = money_block(payments)
    expenses_block = money_block(expenses)
    posted_total = money(
        sum(
            (money(o.posted_charge.total_amount) for o in posted_orders.select_related("posted_charge") if o.posted_charge),
            ZERO,
        )
    )
    snapshot = {
        "business_date": str(business_date),
        "payments": payments_block,
        "expenses": expenses_block,
        "service_postings": {
            "count": posted_orders.count(),
            "total": str(posted_total),
        },
        "stays": {"arrivals": arrivals, "departures": departures},
        "shifts": [
            {
                "shift_number": s.shift_number,
                "status": s.status,
                "responsible": s.responsible_user.full_name,
                "opening_cash": str(money(s.opening_cash_amount)),
                "expected_cash": str(money(s.expected_cash_amount)),
                "actual_cash": (
                    str(money(s.actual_cash_amount))
                    if s.actual_cash_amount is not None
                    else None
                ),
                "cash_difference": str(money(s.cash_difference)),
            }
            for s in shifts.select_related("responsible_user")
        ],
        "pending_handovers": pending_handovers.count(),
        "unassigned_movements": unassigned_movements(hotel, business_date),
    }
    totals = {
        "payments_total": payments_block["total"],
        "payments_cash_total": payments_block["cash_total"],
        "expenses_total": expenses_block["total"],
        "expenses_cash_total": expenses_block["cash_total"],
        "service_postings_total": str(posted_total),
        "shifts_count": shifts.count(),
        "open_shifts_count": shifts.filter(status=ShiftStatus.OPEN).count(),
    }
    return snapshot, totals


@transaction.atomic
def prepare_daily_close(hotel, business_date, *, user=None, notes="") -> DailyClose:
    """Create/refresh the DRAFT close for a date with a fresh snapshot —
    idempotent preview; nothing is locked yet."""
    existing = DailyClose.objects.filter(hotel=hotel, business_date=business_date).first()
    if existing is not None and existing.status == DailyCloseStatus.CLOSED:
        raise DayAlreadyClosed({"business_date": str(business_date)})
    snapshot, totals = build_daily_snapshot(hotel, business_date)
    if existing is None:
        close = DailyClose.objects.create(
            hotel=hotel,
            close_number=next_number(hotel, "daily_close"),
            business_date=business_date,
            snapshot_json=snapshot,
            totals_json=totals,
            notes=notes or "",
        )
        _dc_log(close, "", DailyCloseStatus.DRAFT, user)
        return close
    existing.snapshot_json = snapshot
    existing.totals_json = totals
    if notes:
        existing.notes = notes
    existing.save(update_fields=["snapshot_json", "totals_json", "notes", "updated_at"])
    return existing


@transaction.atomic
def close_business_day(hotel, business_date, *, user=None, notes="") -> DailyClose:
    """Close one business date: every shift of the date must be closed or
    cancelled, submitted handovers must be resolved, and a date can only be
    closed ONCE. Stores a final snapshot; deletes and rewrites nothing."""
    if DailyClose.objects.filter(
        hotel=hotel, business_date=business_date, status=DailyCloseStatus.CLOSED
    ).exists():
        raise DayAlreadyClosed({"business_date": str(business_date)})
    open_count = Shift.objects.filter(
        hotel=hotel, business_date=business_date, status=ShiftStatus.OPEN
    ).count()
    if open_count:
        raise OpenShiftsPreventClose({"open_shifts": open_count})
    pending = ShiftHandover.objects.filter(
        hotel=hotel,
        status=HandoverStatus.SUBMITTED,
        from_shift__business_date=business_date,
    ).count()
    if pending:
        raise PendingHandoversPreventClose({"pending_handovers": pending})

    close = prepare_daily_close(hotel, business_date, user=user, notes=notes)
    close.status = DailyCloseStatus.CLOSED
    close.closed_by = _actor(user)
    close.closed_at = timezone.now()
    if notes:
        close.notes = notes
    close.save(update_fields=["status", "closed_by", "closed_at", "notes", "updated_at"])
    _dc_log(close, DailyCloseStatus.DRAFT, DailyCloseStatus.CLOSED, user, notes)
    return close
