"""Finance services (Phase 8 + folio final closure) — the single controlled
path for money.

All numbering, balance math, and lifecycle transitions live here; views never
mutate money directly. Balances are always **re-derived from posted line items**
(a stored total is never trusted). Nothing here touches an external gateway.

Finality rules (folio final closure round):
- A CLOSED or VOIDED folio is fully read-only: no charges, no payments, no
  voids inside it, no note edits, and never ``closed -> open``.
- Every new charge/payment is stamped with the HOTEL business date; free
  back-dating and future-dating are impossible.
- **Void window**: a record may only be voided on its own business date while
  that day is open. Afterwards the correction is a linked counter-posting —
  ``adjust_charge`` for charges, ``reverse_payment`` for payments (full
  amounts only, one posted counter-posting per original, no chains).
- A folio may only be VOIDED while open and completely empty (no charge or
  payment rows, no non-voided invoices) — money history is never orphaned.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import (
    ActiveInvoiceExists,
    ChargeAlreadyAdjusted,
    FolioClosed,
    FolioHasPostings,
    FolioNotBalanced,
    InvalidAmount,
    InvalidFinanceOperation,
    PaymentAlreadyReversed,
    ReservationFolioNotSupported,
    StayNotInHouse,
    VoidReasonRequired,
    VoidWindowClosed,
    VoidWindowOpen,
)

from .models import (
    CREDIT_CHARGE_TYPES,
    ChargeType,
    Expense,
    FinancialNumberSequence,
    Folio,
    FolioCharge,
    FolioStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    NumberKind,
    Payment,
    PostingStatus,
)

TWO = Decimal("0.01")
ZERO = Decimal("0.00")

_PREFIX = {
    NumberKind.FOLIO: "FOL",
    NumberKind.RECEIPT: "RCP",
    NumberKind.INVOICE: "INV",
    NumberKind.EXPENSE: "EXP",
    NumberKind.CHARGE: "CHG",
}


def money(value) -> Decimal:
    """Quantize any numeric to 2 decimal places (bankers-safe half-up)."""
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def next_number(hotel, kind: str) -> str:
    """Allocate the next per-hotel document number for ``kind``.

    Uses ``select_for_update`` on the sequence row so concurrent allocations
    cannot collide. MUST run inside a transaction.
    """
    seq, _ = FinancialNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel, kind=kind
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"{_PREFIX[kind]}{seq.last_number:05d}"


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


# --- Business-date helpers (folio final closure) ------------------------------
# All lazy imports: shifts is a later app and finance must stay importable
# without it during app loading.


def _business_date(hotel):
    from apps.shifts.services import get_business_date

    return get_business_date(hotel)


def _ensure_day_open(hotel, on_date) -> None:
    from apps.shifts.services import ensure_business_day_open

    ensure_business_day_open(hotel, on_date)


def _day_is_closed(hotel, on_date) -> bool:
    from apps.shifts.models import DailyClose, DailyCloseStatus

    return DailyClose.objects.filter(
        hotel=hotel, business_date=on_date, status=DailyCloseStatus.CLOSED
    ).exists()


def _payment_business_date(payment):
    """The payment's business date; legacy rows (NULL) fall back to the
    calendar date of ``paid_at`` in the hotel's timezone."""
    if payment.business_date:
        return payment.business_date
    hotel_settings = getattr(payment.hotel, "settings", None)
    tz_name = ((getattr(hotel_settings, "timezone", "") or "")).strip()
    if tz_name:
        try:
            return payment.paid_at.astimezone(ZoneInfo(tz_name)).date()
        except (KeyError, ValueError):
            pass
    return timezone.localtime(payment.paid_at).date()


def _require_void_window(hotel, record_date) -> None:
    """Void only on the record's own business date while that day is open."""
    current = _business_date(hotel)
    if record_date != current or _day_is_closed(hotel, current):
        raise VoidWindowClosed(
            {"record_date": str(record_date), "business_date": str(current)}
        )


def _require_void_window_passed(hotel, record_date) -> None:
    """Adjustments/reversals only once the void window is gone, so the two
    correction paths never overlap."""
    current = _business_date(hotel)
    if record_date == current and not _day_is_closed(hotel, current):
        raise VoidWindowOpen({"record_date": str(record_date)})


def _require_reason(reason) -> str:
    if not (reason or "").strip():
        raise VoidReasonRequired()
    return reason.strip()


def _lock_folio(folio) -> Folio:
    """Re-read the folio under a row lock: every money mutation on a folio
    serializes here (charge vs close, double close, void vs close, ...)."""
    return Folio.objects.select_for_update().get(pk=folio.pk)


def _record_event(hotel, *, event_type, severity, title, message="", user=None,
                  obj=None) -> None:
    # Phase 14 activity system (lazy import keeps app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type=event_type,
        category="finance",
        severity=severity,
        title=title,
        message=message,
        actor=user,
        related_object=obj,
        related_url="/hotel/finance",
    )


# --- Balance ----------------------------------------------------------------


def folio_balance(folio) -> dict:
    """Re-derive a folio's totals from its posted charges and payments."""
    charges = folio.charges.filter(status=PostingStatus.POSTED)
    payments = folio.payments.filter(status=PostingStatus.POSTED)
    total_charges = money(sum((c.total_amount for c in charges), ZERO))
    total_payments = money(sum((p.amount for p in payments), ZERO))
    return {
        "total_charges": total_charges,
        "total_payments": total_payments,
        "balance": money(total_charges - total_payments),
    }


def compute_charge_totals(quantity, unit_amount, tax_rate, charge_type):
    """Return ``(amount, tax_amount, total_amount)`` for a charge."""
    amount = money(Decimal(quantity) * Decimal(unit_amount))
    tax_amount = money(amount * Decimal(tax_rate) / Decimal("100"))
    total = money(amount + tax_amount)
    is_credit = charge_type in CREDIT_CHARGE_TYPES
    if not is_credit and amount <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if total == ZERO:
        raise InvalidAmount({"field": "total_amount", "reason": "must_not_be_zero"})
    return amount, tax_amount, total


# --- Folio lifecycle --------------------------------------------------------


def _hotel_currency(hotel) -> str:
    """The hotel's default currency (from HotelSettings) or USD."""
    settings_obj = getattr(hotel, "settings", None)
    if settings_obj and getattr(settings_obj, "default_currency", ""):
        return settings_obj.default_currency
    return "USD"


@transaction.atomic
def create_folio(hotel, *, reservation=None, stay=None, guest=None,
                 customer_name="", currency=None, notes="", user=None,
                 origin="manual") -> Folio:
    """Open a folio. The currency is ALWAYS the hotel's (any passed value is
    ignored — documented decision). A reservation may only be referenced
    together with its stay: pre-arrival folios are not supported."""
    if reservation is not None and stay is None:
        raise ReservationFolioNotSupported()
    if stay is not None:
        # Serialize concurrent folio creation for the same stay on the stay
        # row; the partial unique constraint is the DB backstop.
        stay = type(stay).objects.select_for_update().get(pk=stay.pk)
        if Folio.objects.filter(
            hotel=hotel, stay=stay, status=FolioStatus.OPEN
        ).exists():
            raise InvalidFinanceOperation({"reason": "open_folio_exists_for_stay"})
    number = next_number(hotel, NumberKind.FOLIO)
    actor = _actor(user)
    try:
        folio = Folio.objects.create(
            hotel=hotel,
            reservation=reservation,
            stay=stay,
            guest=guest,
            customer_name=customer_name or (guest.full_name if guest else ""),
            folio_number=number,
            currency=_hotel_currency(hotel),
            notes=notes or "",
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError:
        raise InvalidFinanceOperation({"reason": "open_folio_exists_for_stay"})
    _record_event(
        hotel,
        event_type="folio.created",
        severity="info",
        title=f"Folio {folio.folio_number} opened",
        message=f"{folio.customer_name or '—'} · {origin}",
        user=user,
        obj=folio,
    )
    return folio


@transaction.atomic
def ensure_stay_folio(stay, *, user=None) -> Folio:
    """Get-or-create the stay's ONE open folio (idempotent, race-safe).

    Called from check-in (same transaction: a failed folio rolls back the
    whole check-in) and from service-order posting. Links stay + guest +
    reservation, uses the hotel currency, and never posts any charge,
    payment, or deposit.
    """
    stay = type(stay).objects.select_for_update().get(pk=stay.pk)
    # Restaurant closure (P0): a NEW operational folio may only be opened for
    # an IN-HOUSE stay — a departed/cancelled stay can never grow new money.
    # Reading, printing, and corrections on EXISTING folios are untouched;
    # check-in calls this while the stay is already in-house.
    if stay.status != "in_house":
        raise StayNotInHouse({"stay": stay.pk, "status": stay.status})
    existing = Folio.objects.filter(
        hotel=stay.hotel, stay=stay, status=FolioStatus.OPEN
    ).first()
    if existing is not None:
        return existing
    try:
        return create_folio(
            stay.hotel,
            reservation=stay.reservation,
            stay=stay,
            guest=stay.primary_guest,
            customer_name=stay.primary_guest.full_name,
            user=user,
            origin="stay",
        )
    except (IntegrityError, InvalidFinanceOperation):
        # Lost a race that slipped past the lock: the winner's folio is ours.
        return Folio.objects.get(
            hotel=stay.hotel, stay=stay, status=FolioStatus.OPEN
        )


def _guard_open(folio):
    if folio.status != FolioStatus.OPEN:
        raise FolioClosed({"folio": folio.id, "status": folio.status})


@transaction.atomic
def close_folio(folio, *, user=None) -> Folio:
    folio = _lock_folio(folio)
    _guard_open(folio)
    balance = folio_balance(folio)
    if balance["balance"] != ZERO:
        raise FolioNotBalanced({"folio": folio.id})
    folio.status = FolioStatus.CLOSED
    folio.closed_at = timezone.now()
    folio.closed_by = _actor(user)
    folio.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    _record_event(
        folio.hotel,
        event_type="folio.closed",
        severity="success",
        title=f"Folio {folio.folio_number} closed",
        message=(
            f"charges {balance['total_charges']} · "
            f"payments {balance['total_payments']} · {folio.currency}"
        ),
        user=user,
        obj=folio,
    )
    return folio


@transaction.atomic
def void_folio(folio, *, reason, user=None) -> Folio:
    """Void an OPEN folio created by mistake — only while completely empty.

    A folio holding ANY charge/payment row (even voided ones) keeps its
    history under a proper CLOSE instead; a closed folio is final and can
    never be voided.
    """
    reason = _require_reason(reason)
    folio = _lock_folio(folio)
    if folio.status == FolioStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    if folio.status == FolioStatus.CLOSED:
        raise FolioClosed({"folio": folio.id, "status": folio.status})
    if (
        folio.charges.exists()
        or folio.payments.exists()
        or folio.invoices.exclude(status=InvoiceStatus.VOIDED).exists()
    ):
        raise FolioHasPostings({"folio": folio.id})
    folio.status = FolioStatus.VOIDED
    folio.void_reason = reason
    folio.voided_at = timezone.now()
    folio.voided_by = _actor(user)
    folio.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    _record_event(
        folio.hotel,
        event_type="folio.voided",
        severity="danger",
        title=f"Folio {folio.folio_number} voided",
        message=reason,
        user=user,
        obj=folio,
    )
    return folio


# --- Charges ----------------------------------------------------------------


@transaction.atomic
def add_charge(folio, *, charge_type, description, quantity, unit_amount,
               tax_rate=ZERO, tax_amount=None, source="manual", user=None,
               adjusts=None, record_event=True) -> FolioCharge:
    """Post a charge dated to the CURRENT open hotel business date (the
    caller never chooses the date — no back- or future-dating)."""
    folio = _lock_folio(folio)
    _guard_open(folio)
    business_date = _business_date(folio.hotel)
    _ensure_day_open(folio.hotel, business_date)
    if tax_amount is None:
        amount, tax_amount, total = compute_charge_totals(
            quantity, unit_amount, tax_rate, charge_type
        )
    else:
        # Explicit tax override: used when the caller already holds an exact,
        # per-line-rounded tax sum (e.g. posting a Phase 9 service order whose
        # items may mix tax rates). The stored ``tax_rate`` is informational.
        amount = money(Decimal(quantity) * Decimal(unit_amount))
        tax_amount = money(tax_amount)
        if tax_amount < ZERO:
            raise InvalidAmount({"field": "tax_amount", "reason": "must_not_be_negative"})
        if charge_type not in CREDIT_CHARGE_TYPES and amount <= ZERO:
            raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
        total = money(amount + tax_amount)
        if total == ZERO:
            raise InvalidAmount({"field": "total_amount", "reason": "must_not_be_zero"})
    charge = FolioCharge.objects.create(
        hotel=folio.hotel,
        folio=folio,
        charge_number=next_number(folio.hotel, NumberKind.CHARGE),
        type=charge_type,
        description=description,
        quantity=money(quantity),
        unit_amount=money(unit_amount),
        amount=amount,
        tax_rate=Decimal(tax_rate),
        tax_amount=tax_amount,
        total_amount=total,
        charge_date=business_date,
        source=source,
        adjusts=adjusts,
        created_by=_actor(user),
    )
    if record_event:
        _record_event(
            folio.hotel,
            event_type="charge.posted",
            severity="info",
            title=f"Charge {charge.charge_number} posted",
            message=f"{charge.description} · {charge.total_amount} {folio.currency} · {folio.folio_number}",
            user=user,
            obj=charge,
        )
    return charge


@transaction.atomic
def void_charge(charge, *, reason, user=None) -> FolioCharge:
    """Void a charge — only inside its own open business date, on an open
    folio. Later corrections go through ``adjust_charge``."""
    reason = _require_reason(reason)
    folio = _lock_folio(charge.folio)
    _guard_open(folio)
    charge = FolioCharge.objects.select_for_update().get(pk=charge.pk)
    if charge.status == PostingStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    if charge.adjustments.filter(status=PostingStatus.POSTED).exists():
        raise InvalidFinanceOperation({"reason": "charge_adjusted"})
    _require_void_window(folio.hotel, charge.charge_date)
    charge.status = PostingStatus.VOIDED
    charge.void_reason = reason
    charge.voided_at = timezone.now()
    charge.voided_by = _actor(user)
    charge.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    _record_event(
        folio.hotel,
        event_type="charge.voided",
        severity="danger",
        title=f"Charge {charge.charge_number} voided",
        message=f"{charge.total_amount} {folio.currency} · {reason}",
        user=user,
        obj=charge,
    )
    return charge


@transaction.atomic
def adjust_charge(charge, *, reason, user=None) -> FolioCharge:
    """Post the FULL counter-charge for an original whose void window has
    closed. The original is never edited; the link (``adjusts``) plus the
    unique posted-adjustment constraint make repeats impossible."""
    reason = _require_reason(reason)
    folio = _lock_folio(charge.folio)
    _guard_open(folio)
    charge = FolioCharge.objects.select_for_update().get(pk=charge.pk)
    if charge.status != PostingStatus.POSTED:
        raise InvalidFinanceOperation({"reason": "not_posted"})
    if charge.adjusts_id is not None:
        raise InvalidFinanceOperation({"reason": "cannot_adjust_adjustment"})
    if charge.adjustments.filter(status=PostingStatus.POSTED).exists():
        raise ChargeAlreadyAdjusted({"charge": charge.id})
    _require_void_window_passed(folio.hotel, charge.charge_date)
    _ensure_day_open(folio.hotel, _business_date(folio.hotel))
    try:
        adjustment = add_charge(
            folio,
            charge_type=ChargeType.ADJUSTMENT,
            description=f"Adjustment ({charge.charge_number or charge.id}): {reason}",
            quantity=Decimal("1"),
            unit_amount=-charge.total_amount,
            tax_rate=ZERO,
            source="adjustment",
            user=user,
            adjusts=charge,
            record_event=False,
        )
    except IntegrityError:
        raise ChargeAlreadyAdjusted({"charge": charge.id})
    _record_event(
        folio.hotel,
        event_type="charge.adjusted",
        severity="warning",
        title=f"Charge {charge.charge_number} adjusted",
        message=(
            f"{adjustment.charge_number}: {adjustment.total_amount} "
            f"{folio.currency} · {reason}"
        ),
        user=user,
        obj=adjustment,
    )
    return adjustment


# --- Payments ---------------------------------------------------------------


def _shift_context(hotel, user, when):
    """Phase 12 hooks (imported lazily to avoid app-load cycles): refuse new
    dated activity on a CLOSED business day, and attach the movement to the
    creator's open shift when one exists — a missing shift never blocks the
    operation (it becomes a reported "unassigned movement"). Still used by
    the EXPENSE services (untouched this round)."""
    from apps.shifts.services import ensure_business_day_open, get_open_shift_for

    ensure_business_day_open(hotel, when.date())
    return get_open_shift_for(user, hotel)


@transaction.atomic
def record_payment(folio, *, amount, method, payer_name="",
                   reference="", notes="", user=None) -> Payment:
    """Record a payment stamped to NOW and to the current open hotel
    business date (the caller never chooses either)."""
    from apps.shifts.services import get_open_shift_for

    folio = _lock_folio(folio)
    _guard_open(folio)
    if money(amount) <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    business_date = _business_date(folio.hotel)
    _ensure_day_open(folio.hotel, business_date)
    payment = Payment.objects.create(
        hotel=folio.hotel,
        folio=folio,
        receipt_number=next_number(folio.hotel, NumberKind.RECEIPT),
        amount=money(amount),
        currency=folio.currency,
        method=method,
        paid_at=timezone.now(),
        business_date=business_date,
        shift=get_open_shift_for(user, folio.hotel),
        payer_name=payer_name or folio.customer_name,
        reference=reference or "",
        notes=notes or "",
        created_by=_actor(user),
    )
    _record_event(
        folio.hotel,
        event_type="payment.recorded",
        severity="success",
        title=f"Payment {payment.receipt_number} recorded",
        message=f"{payment.amount} {payment.currency} · {payment.method} · {folio.folio_number}",
        user=user,
        obj=payment,
    )
    return payment


@transaction.atomic
def void_payment(payment, *, reason, user=None) -> Payment:
    """Void a payment — only inside its own open business date, on an open
    folio. Later corrections go through ``reverse_payment``."""
    reason = _require_reason(reason)
    folio = _lock_folio(payment.folio)
    _guard_open(folio)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == PostingStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    if payment.reversals.filter(status=PostingStatus.POSTED).exists():
        raise InvalidFinanceOperation({"reason": "payment_reversed"})
    _require_void_window(folio.hotel, _payment_business_date(payment))
    payment.status = PostingStatus.VOIDED
    payment.void_reason = reason
    payment.voided_at = timezone.now()
    payment.voided_by = _actor(user)
    payment.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    _record_event(
        payment.hotel,
        event_type="payment.voided",
        severity="danger",
        title=f"Payment {payment.receipt_number} voided",
        message=f"{payment.amount} {payment.currency} · {reason}",
        user=user,
        obj=payment,
    )
    return payment


@transaction.atomic
def reverse_payment(payment, *, reason, user=None) -> Payment:
    """Post the FULL counter-payment (negative amount, new receipt number)
    for an original whose void window has closed. The original is never
    edited; reversals cannot be reversed and repeats are impossible."""
    reason = _require_reason(reason)
    folio = _lock_folio(payment.folio)
    _guard_open(folio)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status != PostingStatus.POSTED:
        raise InvalidFinanceOperation({"reason": "not_posted"})
    if payment.reverses_id is not None:
        raise InvalidFinanceOperation({"reason": "cannot_reverse_reversal"})
    if payment.reversals.filter(status=PostingStatus.POSTED).exists():
        raise PaymentAlreadyReversed({"payment": payment.id})
    _require_void_window_passed(folio.hotel, _payment_business_date(payment))
    business_date = _business_date(folio.hotel)
    _ensure_day_open(folio.hotel, business_date)
    from apps.shifts.services import get_open_shift_for

    try:
        reversal = Payment.objects.create(
            hotel=folio.hotel,
            folio=folio,
            receipt_number=next_number(folio.hotel, NumberKind.RECEIPT),
            amount=-payment.amount,
            currency=payment.currency,
            method=payment.method,
            paid_at=timezone.now(),
            business_date=business_date,
            reverses=payment,
            shift=get_open_shift_for(user, folio.hotel),
            payer_name=payment.payer_name,
            reference=payment.receipt_number,
            notes=reason,
            created_by=_actor(user),
        )
    except IntegrityError:
        raise PaymentAlreadyReversed({"payment": payment.id})
    _record_event(
        folio.hotel,
        event_type="payment.reversed",
        severity="warning",
        title=f"Payment {payment.receipt_number} reversed",
        message=(
            f"{reversal.receipt_number}: {reversal.amount} "
            f"{reversal.currency} · {reason}"
        ),
        user=user,
        obj=reversal,
    )
    return reversal


# --- Invoices ---------------------------------------------------------------


@transaction.atomic
def create_invoice(folio, *, due_date=None, customer_name="", customer_phone="",
                   notes="", user=None) -> Invoice:
    """Create a DRAFT invoice for an OPEN folio (no number/snapshot until
    issued). Closed/voided folios are read-only — reprints use the statement
    and the invoice history."""
    _guard_open(folio)
    guest = folio.guest
    return Invoice.objects.create(
        hotel=folio.hotel,
        folio=folio,
        status=InvoiceStatus.DRAFT,
        currency=folio.currency,
        due_date=due_date,
        customer_name=customer_name or folio.customer_name,
        customer_phone=customer_phone or (guest.phone if guest else ""),
        customer_email=guest.email if guest else "",
        customer_document_number=guest.document_number if guest else "",
        notes=notes or "",
        created_by=_actor(user),
    )


@transaction.atomic
def issue_invoice(invoice, *, user=None) -> Invoice:
    """Issue a draft invoice: allocate a number and freeze a line snapshot.
    ONE active (issued, non-voided) invoice per folio — a new one may only
    be issued after the previous is voided."""
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidFinanceOperation(
            {"reason": "not_draft", "status": invoice.status}
        )
    folio = _lock_folio(invoice.folio)
    _guard_open(folio)
    if Invoice.objects.filter(
        folio=folio, status=InvoiceStatus.ISSUED
    ).exclude(pk=invoice.pk).exists():
        raise ActiveInvoiceExists({"folio": folio.id})
    charges = list(
        folio.charges.filter(status=PostingStatus.POSTED).order_by(
            "charge_date", "id"
        )
    )
    if not charges:
        raise InvalidFinanceOperation({"reason": "no_charges"})

    subtotal = money(sum((c.amount for c in charges), ZERO))
    tax_total = money(sum((c.tax_amount for c in charges), ZERO))
    total = money(subtotal + tax_total)

    for c in charges:
        InvoiceLine.objects.create(
            hotel=invoice.hotel,
            invoice=invoice,
            description=c.description,
            quantity=c.quantity,
            unit_amount=c.unit_amount,
            tax_rate=c.tax_rate,
            tax_amount=c.tax_amount,
            total_amount=c.total_amount,
            source_charge=c,
        )
    invoice.invoice_number = next_number(invoice.hotel, NumberKind.INVOICE)
    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = timezone.now()
    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.total = total
    invoice.balance_at_issue = folio_balance(folio)["balance"]
    invoice.save()
    _record_event(
        invoice.hotel,
        event_type="invoice.issued",
        severity="success",
        title=f"Invoice {invoice.invoice_number} issued",
        message=f"{invoice.total} {invoice.currency} · {folio.folio_number}",
        user=user,
        obj=invoice,
    )
    return invoice


@transaction.atomic
def void_invoice(invoice, *, reason, user=None) -> Invoice:
    reason = _require_reason(reason)
    if invoice.status == InvoiceStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    invoice.status = InvoiceStatus.VOIDED
    invoice.void_reason = reason
    invoice.voided_at = timezone.now()
    invoice.voided_by = _actor(user)
    invoice.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    _record_event(
        invoice.hotel,
        event_type="invoice.voided",
        severity="danger",
        title=f"Invoice {invoice.invoice_number or 'draft'} voided",
        message=reason,
        user=user,
        obj=invoice,
    )
    return invoice


# --- Expenses (deliberately untouched in the folio closure round) ------------


@transaction.atomic
def create_expense(hotel, *, category, description, amount, method, paid_at=None,
                   vendor_name="", reference="", notes="", currency=None, user=None) -> Expense:
    if money(amount) <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    actor = _actor(user)
    paid_at = paid_at or timezone.now()
    shift = _shift_context(hotel, user, paid_at)
    return Expense.objects.create(
        hotel=hotel,
        expense_number=next_number(hotel, NumberKind.EXPENSE),
        category=category,
        description=description,
        amount=money(amount),
        currency=currency or _hotel_currency(hotel),
        method=method,
        paid_at=paid_at,
        shift=shift,
        vendor_name=vendor_name or "",
        reference=reference or "",
        notes=notes or "",
        created_by=actor,
        updated_by=actor,
    )


@transaction.atomic
def void_expense(expense, *, reason, user=None) -> Expense:
    if not (reason or "").strip():
        raise VoidReasonRequired()
    if expense.status == PostingStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    expense.status = PostingStatus.VOIDED
    expense.void_reason = reason.strip()
    expense.voided_at = timezone.now()
    expense.voided_by = _actor(user)
    expense.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    return expense
