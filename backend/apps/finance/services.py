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

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.common.exceptions import (
    ActiveInvoiceExists,
    ChargeAlreadyAdjusted,
    ExpenseAlreadyReversed,
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
#: Largest magnitude a ``MONEY_KW`` field (max_digits=12, decimal_places=2) can
#: store: 10 integer digits, so ``abs(value)`` must stay strictly below 10**10.
#: An FX-derived base amount at or beyond this is rejected as a clean validation
#: error instead of surfacing later as a DB ``NumericValueOutOfRange`` (500).
MONEY_MAX_ABS = Decimal(10) ** 10


class RateBasis(models.TextChoices):
    """Canonical FX direction for a multi-currency ``Payment`` — the stored
    label DIRECTS how the base/folio ``amount`` is derived from the tendered
    ``original_amount`` and the manual ``exchange_rate`` (see
    ``record_reservation_payment``):

    - ``base_per_payment``: base = ``original_amount`` * ``exchange_rate``
      (rate = base-currency units per 1 unit of the payment currency).
    - ``payment_per_base``: base = ``original_amount`` / ``exchange_rate``
      (rate = payment-currency units per 1 unit of the base currency).
    """

    BASE_PER_PAYMENT = "base_per_payment", "Base per payment (base = original * rate)"
    PAYMENT_PER_BASE = "payment_per_base", "Payment per base (base = original / rate)"


#: Canonical FX direction stored on multi-currency payments when the caller does
#: not supply its own ``rate_basis`` label (see ``RateBasis``). Preserved as the
#: back-compat default so existing same-direction callers are unaffected — the
#: value is the plain string ``"base_per_payment"``.
DEFAULT_RATE_BASIS = RateBasis.BASE_PER_PAYMENT.value


def _resolve_rate_basis(rate_basis) -> str:
    """Normalise a caller-supplied ``rate_basis`` to one of the two canonical
    ``RateBasis`` values; an empty/blank label falls back to
    ``DEFAULT_RATE_BASIS``. Anything else is rejected as a clean validation
    error rather than being stored as a cosmetic, math-ignored label."""
    value = (rate_basis or "").strip() or DEFAULT_RATE_BASIS
    if value not in RateBasis.values:
        raise InvalidFinanceOperation(
            {"reason": "invalid_rate_basis", "rate_basis": rate_basis}
        )
    return value

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
    # Daily-close serialization: every dated finance write reads the operational
    # date UNDER a row lock on HotelSettings (all callers here run inside a
    # transaction), so a write and the daily close can never straddle a roll.
    from apps.shifts.services import lock_business_date

    return lock_business_date(hotel)


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


def _accepted_currencies(hotel) -> list[str]:
    """The hotel's accepted PAYMENT currencies, upper-cased and de-duplicated.

    ``HotelSettings.accepted_currencies`` (a JSON list) is added in a separate
    package; until it exists — or whenever it is empty — the accepted set is
    exactly the hotel's default (base) currency. The default is ALWAYS accepted.
    """
    default = _hotel_currency(hotel).upper()
    settings_obj = getattr(hotel, "settings", None)
    raw = getattr(settings_obj, "accepted_currencies", None) or []
    codes = {str(code).strip().upper() for code in raw if str(code).strip()}
    codes.add(default)
    return sorted(codes)


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


def _reuse_reservation_folio_for_stay(stay, *, user=None):
    """Attach ``stay`` to its reservation's existing OPEN pre-arrival folio.

    When a deposit was taken before arrival the reservation already owns its ONE
    open folio (``reservation`` set, ``stay`` NULL). Instead of opening a SECOND
    folio for the stay — which would split the ledger and strand the deposit —
    the stay is linked onto that same folio. It then satisfies the per-stay open
    folio guard (``stay`` is no longer NULL) and no longer the per-reservation
    one, so no unique constraint is violated. Any deposit payment already on the
    folio now belongs to the stay folio automatically — ONE ledger (invariant #1);
    the balance stays DERIVED.

    Returns the now stay-linked folio, or ``None`` when there is nothing to reuse
    (the stay has no reservation, or the reservation has no open stay-null folio).
    The reservation row is locked first to serialize with
    ``ensure_reservation_folio`` so a folio created mid-flight is never missed.
    """
    if stay.reservation_id is None:
        return None
    from apps.reservations.models import Reservation

    # Serialize with ensure_reservation_folio on the reservation row so a
    # concurrently-created deposit folio can never be missed (which would open a
    # duplicate ledger). Re-locking inside the same transaction is a no-op.
    Reservation.objects.select_for_update().filter(
        pk=stay.reservation_id
    ).first()
    folio = (
        Folio.objects.select_for_update()
        .filter(
            hotel=stay.hotel,
            reservation_id=stay.reservation_id,
            stay__isnull=True,
            status=FolioStatus.OPEN,
        )
        .first()
    )
    if folio is None:
        return None
    folio.stay = stay
    folio.updated_by = _actor(user)
    update_fields = ["stay", "updated_by", "updated_at"]
    # Fill the folio's guest from the stay when it was opened from a bare
    # snapshot (no central guest linked yet) — keeps the ledger coherent.
    if folio.guest_id is None and stay.primary_guest_id is not None:
        folio.guest = stay.primary_guest
        update_fields.append("guest")
        if not folio.customer_name:
            folio.customer_name = stay.primary_guest.full_name
            update_fields.append("customer_name")
    folio.save(update_fields=update_fields)
    _record_event(
        stay.hotel,
        event_type="folio.attached_to_stay",
        severity="info",
        title=f"Folio {folio.folio_number} carried into stay",
        message=f"{folio.customer_name or '—'} · deposit folio → stay",
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
    # Reservation-folio reuse (RESERVATIONS-FORM-REWORK — immediate check-in):
    # if a pre-arrival deposit opened the reservation's ONE folio (reservation
    # set, stay NULL), ATTACH this stay to that same folio instead of opening a
    # second one — the deposit then lives on the stay folio automatically (ONE
    # ledger). Backward-compatible: with no reservation, or no open reservation
    # folio, this is a no-op and the stay folio is created below exactly as
    # before.
    reused = _reuse_reservation_folio_for_stay(stay, user=user)
    if reused is not None:
        return reused
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


@transaction.atomic
def ensure_reservation_folio(reservation, *, user=None) -> Folio:
    """Get-or-create the reservation's ONE open PRE-ARRIVAL folio (idempotent,
    race-safe) — the folio for a deposit taken before check-in.

    This is the SANCTIONED path that may create a reservation-only folio
    (``reservation`` set, ``stay`` NULL). The generic ``create_folio`` still
    refuses that shape (``ReservationFolioNotSupported``); only this service is
    allowed to build it directly. Currency is forced to the hotel default and
    NO charge, payment, or deposit is posted here.

    Concurrency: the reservation row is locked (``select_for_update``) so two
    callers cannot open two folios; the partial unique constraint
    ``unique_open_folio_per_reservation`` is the DB backstop.
    """
    reservation = (
        type(reservation).objects.select_for_update().get(pk=reservation.pk)
    )
    hotel = reservation.hotel
    existing = Folio.objects.filter(
        hotel=hotel,
        reservation=reservation,
        stay__isnull=True,
        status=FolioStatus.OPEN,
    ).first()
    if existing is not None:
        return existing
    # FIN-F2: the two partial-unique constraints (``unique_open_folio_per_stay``
    # and ``unique_open_folio_per_reservation``) do NOT jointly forbid a single
    # reservation from holding BOTH an open stay-null folio AND an open stay
    # folio. Guard that structural gap: if this reservation already has an OPEN
    # STAY folio, refuse to open a second (reservation-only) ledger for it — this
    # runs under the reservation ``select_for_update`` above, so it is race-safe.
    stay_folio = Folio.objects.filter(
        hotel=hotel,
        reservation=reservation,
        stay__isnull=False,
        status=FolioStatus.OPEN,
    ).first()
    if stay_folio is not None:
        raise InvalidFinanceOperation(
            {"reason": "reservation_already_has_stay_folio", "folio": stay_folio.id}
        )
    # ``primary_guest`` (a central Guest FK) is added in a later package; until
    # then it is absent — fall back to the reservation's snapshot name.
    guest = getattr(reservation, "primary_guest", None)
    customer_name = (
        (guest.full_name if guest else "")
        or getattr(reservation, "primary_guest_name", "")
        or ""
    )
    actor = _actor(user)
    number = next_number(hotel, NumberKind.FOLIO)
    try:
        folio = Folio.objects.create(
            hotel=hotel,
            reservation=reservation,
            stay=None,
            guest=guest,
            customer_name=customer_name,
            folio_number=number,
            currency=_hotel_currency(hotel),
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError:
        # Lost a race that slipped past the lock: the winner's folio is ours.
        return Folio.objects.get(
            hotel=hotel,
            reservation=reservation,
            stay__isnull=True,
            status=FolioStatus.OPEN,
        )
    _record_event(
        hotel,
        event_type="folio.created",
        severity="info",
        title=f"Folio {folio.folio_number} opened",
        message=f"{folio.customer_name or '—'} · reservation",
        user=user,
        obj=folio,
    )
    return folio


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


@transaction.atomic
def set_folio_awaiting_final_charges(folio, *, awaiting, note="", user=None) -> Folio:
    """Toggle the folio's "awaiting final charges" operational flag (§32). While
    true the folio must NOT close and departure is blocked; cleared once the final
    charges are confirmed. Only on an OPEN folio."""
    folio = _lock_folio(folio)
    _guard_open(folio)
    awaiting = bool(awaiting)
    folio.awaiting_final_charges = awaiting
    folio.awaiting_final_charges_note = (note or "")[:255] if awaiting else ""
    folio.save(
        update_fields=[
            "awaiting_final_charges",
            "awaiting_final_charges_note",
            "updated_at",
        ]
    )
    _record_event(
        folio.hotel,
        event_type=(
            "folio.awaiting_final_charges_set"
            if awaiting
            else "folio.awaiting_final_charges_cleared"
        ),
        severity="info",
        title=(
            f"Folio {folio.folio_number} "
            f"{'is awaiting' if awaiting else 'cleared'} final charges"
        ),
        message=folio.awaiting_final_charges_note,
        user=user,
        obj=folio,
    )
    return folio


@transaction.atomic
def reopen_folio(folio, *, reason, user=None) -> Folio:
    """Reopen a CLOSED folio (STAYS-ARRIVALS-DEPARTURES §42).

    Special permission (view layer) + mandatory reason + audit. A VOIDED folio
    can never reopen. The reopen requires (and is dated to) the current OPEN
    business day, so it respects the daily close. No financial movement is created
    — closed history is never edited, only the folio is made writable again.
    """
    reason = _require_reason(reason)
    folio = _lock_folio(folio)
    if folio.status == FolioStatus.OPEN:
        return folio
    if folio.status == FolioStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "cannot_reopen_voided"})
    business_date = _business_date(folio.hotel)
    _ensure_day_open(folio.hotel, business_date)
    folio.status = FolioStatus.OPEN
    folio.closed_at = None
    folio.closed_by = None
    folio.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    _record_event(
        folio.hotel,
        event_type="folio.reopened",
        severity="warning",
        title=f"Folio {folio.folio_number} reopened",
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
def post_room_account_charge(folio, *, description, quantity, unit_amount,
                            charge_type=ChargeType.ROOM, tax_rate=ZERO,
                            tax_amount=None, source="room_account",
                            user=None) -> FolioCharge:
    """Post an "on room account" item: the charge is added to the folio and
    left OWING. This is a thin, intent-revealing delegate to ``add_charge``.

    Invariant #5: on-room-account is NOT a payment. This NEVER creates a
    ``Payment`` — doing so would falsely reduce the balance. The balance stays
    truthful (``folio_balance`` = posted charges − posted payments)."""
    return add_charge(
        folio,
        charge_type=charge_type,
        description=description,
        quantity=quantity,
        unit_amount=unit_amount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        source=source,
        user=user,
    )


# STAYS-ARRIVALS-DEPARTURES — source markers for the stay's own room charges so
# the initial charge is idempotent while later extensions post distinct rows.
ROOM_CHARGE_SOURCE = "stay_room"
ROOM_EXTENSION_SOURCE = "stay_room_extension"


@transaction.atomic
def post_stay_room_charge(stay, *, user=None):
    """Post the stay's initial ROOM charge (nightly rate × nights) to its open
    folio (STAYS-ARRIVALS-DEPARTURES §24/§31 / owner decision D1).

    The folio must hold the COMPLETE account: without the room charge the balance
    understates what the guest owes and the check-out "balance == 0" gate would be
    wrong. Idempotent — skips if this stay's folio already holds a ``stay_room``
    ROOM charge. Skips an UNPRICED room (``base_rate`` NULL/<=0) so the statement
    honestly shows no room line (matching reservation ``is_priced=False``).
    Returns the ``FolioCharge`` or ``None``.
    """
    folio = ensure_stay_folio(stay, user=user)
    if folio.charges.filter(
        type=ChargeType.ROOM,
        source=ROOM_CHARGE_SOURCE,
        status=PostingStatus.POSTED,
    ).exists():
        return None
    line = stay.reservation_line
    room_type = getattr(line, "room_type", None) if line is not None else None
    rate = room_type.base_rate if room_type is not None else None
    nights = stay.nights
    if rate is None or money(rate) <= ZERO or nights <= 0:
        return None
    label = room_type.name if room_type is not None else "Room"
    return add_charge(
        folio,
        charge_type=ChargeType.ROOM,
        description=f"{label} — {nights} night(s)",
        quantity=nights,
        unit_amount=money(rate),
        source=ROOM_CHARGE_SOURCE,
        user=user,
    )


@transaction.atomic
def post_stay_extension_charge(stay, *, added_nights, user=None):
    """Post a ROOM charge for ADDED nights when a stay is extended (§25). Distinct
    from the initial charge (its own ``stay_room_extension`` source), so each
    extension is a real, separately-audited folio movement. Skips an unpriced room
    or a non-positive ``added_nights``. Returns the ``FolioCharge`` or ``None``.
    """
    if added_nights is None or int(added_nights) <= 0:
        return None
    folio = ensure_stay_folio(stay, user=user)
    line = stay.reservation_line
    room_type = getattr(line, "room_type", None) if line is not None else None
    rate = room_type.base_rate if room_type is not None else None
    if rate is None or money(rate) <= ZERO:
        return None
    label = room_type.name if room_type is not None else "Room"
    return add_charge(
        folio,
        charge_type=ChargeType.ROOM,
        description=f"{label} — extension ({int(added_nights)} night(s))",
        quantity=int(added_nights),
        unit_amount=money(rate),
        source=ROOM_EXTENSION_SOURCE,
        user=user,
    )


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


@transaction.atomic
def record_payment(folio, *, amount, method, payer_name="",
                   reference="", notes="", user=None,
                   payment_currency="", original_amount=None,
                   exchange_rate=None, rate_basis="",
                   rate_captured_at=None, rate_entered_by=None) -> Payment:
    """Record a payment stamped to NOW and to the current open hotel
    business date (the caller never chooses either).

    ``amount`` is ALWAYS the equivalent in the folio/base currency — it is the
    only value ``folio_balance()`` reads. The optional FX snapshot fields
    (``payment_currency``/``original_amount``/``exchange_rate``/``rate_basis``/
    ``rate_captured_at``/``rate_entered_by``) are purely informational and
    default to legacy behaviour, so existing callers are unaffected. Prefer
    ``record_reservation_payment`` (or a stay equivalent) to derive and pass
    these; this base recorder does not compute FX itself.
    """
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
        payment_currency=payment_currency or "",
        original_amount=(money(original_amount)
                         if original_amount is not None else None),
        exchange_rate=exchange_rate,
        rate_basis=rate_basis or "",
        rate_captured_at=rate_captured_at,
        rate_entered_by=_actor(rate_entered_by),
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
def record_reservation_payment(reservation, *, amount=None, method,
                               currency=None, original_amount=None,
                               exchange_rate=None, rate_basis="",
                               user=None, business_date=None,
                               payer_name="", reference="", notes="") -> Payment:
    """Record a payment (typically a pre-arrival deposit) against a
    reservation's own folio, with optional multi-currency capture at the
    PAYMENT layer only.

    Flow:
      1. ``ensure_reservation_folio`` gets/creates the reservation's single
         open stay-null folio (currency = hotel default = base currency).
      2. Resolve ``currency`` (defaults to the folio/base currency); it must be
         one of the hotel's accepted currencies (or the default).
      3. Same currency as the folio → ``amount`` is the base amount (positive).
         Different currency → a manual ``exchange_rate`` AND the tendered
         ``original_amount`` are REQUIRED and the base ``amount`` is derived as
         ``money(original_amount * exchange_rate)`` (canonical
         ``base_per_payment`` direction; ``rate_basis`` records the direction).
         The FX snapshot (payment_currency / original_amount / exchange_rate /
         rate_basis / rate_captured_at=now / rate_entered_by=user) is stored.
      4. The Payment is posted through the existing ``record_payment`` path, so
         it is stamped to NOW + the current open business date and attached to
         the creator's open shift. The base ``amount`` alone drives
         ``folio_balance`` (its derivation is unchanged).

    ``business_date`` is accepted for signature stability only: like every
    dated finance write, the payment is stamped to the hotel's current open
    business date by ``record_payment`` (no back-/future-dating), so any value
    passed here is deliberately ignored.

    The ``exchange_rate.override`` permission that gates a MANUAL rate is
    enforced at the view/serializer layer in a later package; this service is
    the sanctioned money path only.
    """
    folio = ensure_reservation_folio(reservation, user=user)
    base_currency = folio.currency
    resolved_currency = (currency or base_currency).strip().upper()

    accepted = _accepted_currencies(folio.hotel)
    if resolved_currency not in accepted:
        raise InvalidFinanceOperation(
            {
                "reason": "currency_not_accepted",
                "currency": resolved_currency,
                "accepted": accepted,
            }
        )

    if resolved_currency == base_currency.upper():
        # Same-currency payment: the given amount IS the base amount.
        if amount is None or money(amount) <= ZERO:
            raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
        base_amount = money(amount)
        fx = dict(
            payment_currency=base_currency,
            original_amount=base_amount,
            exchange_rate=None,
            rate_basis="",
            rate_captured_at=None,
            rate_entered_by=None,
        )
    else:
        # Foreign-currency payment: a manual rate + the tendered amount are
        # required; the base amount is DERIVED (never client-trusted) and the
        # DIRECTION of that derivation is DICTATED by ``rate_basis``.
        resolved_basis = _resolve_rate_basis(rate_basis)
        if exchange_rate is None or Decimal(str(exchange_rate)) <= ZERO:
            raise InvalidFinanceOperation(
                {"reason": "exchange_rate_required", "currency": resolved_currency}
            )
        if original_amount is None or money(original_amount) <= ZERO:
            raise InvalidFinanceOperation(
                {"reason": "original_amount_required", "currency": resolved_currency}
            )
        rate = Decimal(str(exchange_rate))
        original = money(original_amount)
        if resolved_basis == RateBasis.PAYMENT_PER_BASE:
            # rate = payment-currency units per 1 base unit ⇒ base = original / rate.
            if rate == ZERO:
                raise InvalidFinanceOperation({"reason": "invalid_exchange_rate"})
            base_amount = money(original / rate)
        else:
            # base_per_payment: rate = base units per 1 payment unit ⇒ multiply.
            base_amount = money(original * rate)
        fx = dict(
            payment_currency=resolved_currency,
            original_amount=original,
            exchange_rate=rate,
            rate_basis=resolved_basis,
            rate_captured_at=timezone.now(),
            rate_entered_by=user,
        )

    # FIN-F3: the resolved base amount must be strictly positive AND fit what a
    # ``MONEY_KW`` column can hold, so an extreme rate/amount is rejected here as
    # a clean 400 instead of surfacing later as a DB ``NumericValueOutOfRange``
    # (500). Applies to both the same- and foreign-currency branches above.
    if base_amount <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if base_amount.copy_abs() >= MONEY_MAX_ABS:
        raise InvalidFinanceOperation({"reason": "amount_out_of_range"})

    return record_payment(
        folio,
        amount=base_amount,
        method=method,
        payer_name=payer_name,
        reference=reference,
        notes=notes,
        user=user,
        **fx,
    )


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


# --- Expenses (final closure round) ------------------------------------------


def _expense_business_date(expense):
    """The expense's business date; legacy rows (NULL) fall back to the
    calendar date of ``paid_at`` in the hotel's timezone."""
    if expense.business_date:
        return expense.business_date
    hotel_settings = getattr(expense.hotel, "settings", None)
    tz_name = ((getattr(hotel_settings, "timezone", "") or "")).strip()
    if tz_name:
        try:
            return expense.paid_at.astimezone(ZoneInfo(tz_name)).date()
        except (KeyError, ValueError):
            pass
    return timezone.localtime(expense.paid_at).date()


#: The ONLY fields a posted voucher may still change — descriptive text,
#: inside its own open business date. Money/date/shift are immutable.
EXPENSE_EDITABLE_FIELDS = ("description", "notes", "reference", "vendor_name")


@transaction.atomic
def create_expense(hotel, *, category, description, amount, method,
                   vendor_name="", reference="", notes="", user=None) -> Expense:
    """Record an expense voucher stamped to NOW and to the current open
    hotel business date, in the HOTEL currency (the caller never chooses
    the timestamp, the financial date, or the currency)."""
    from apps.shifts.services import get_open_shift_for

    if money(amount) <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    actor = _actor(user)
    business_date = _business_date(hotel)
    _ensure_day_open(hotel, business_date)
    expense = Expense.objects.create(
        hotel=hotel,
        expense_number=next_number(hotel, NumberKind.EXPENSE),
        category=category,
        description=description,
        amount=money(amount),
        currency=_hotel_currency(hotel),
        method=method,
        paid_at=timezone.now(),
        business_date=business_date,
        shift=get_open_shift_for(user, hotel),
        vendor_name=vendor_name or "",
        reference=reference or "",
        notes=notes or "",
        created_by=actor,
        updated_by=actor,
    )
    _record_event(
        hotel,
        event_type="expense.created",
        severity="info",
        title=f"Expense {expense.expense_number} recorded",
        message=f"{expense.category} · {expense.amount} {expense.currency} · {expense.method}",
        user=user,
        obj=expense,
    )
    return expense


@transaction.atomic
def update_expense(expense, *, user=None, **fields) -> Expense:
    """Edit the DESCRIPTIVE fields of a posted voucher — only inside its own
    open business date. Money, category, method, currency, dates, and the
    shift are immutable; corrections are void (same day) or a reversal."""
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != PostingStatus.POSTED:
        raise InvalidFinanceOperation({"reason": "not_editable", "status": expense.status})
    for field in fields:
        if field not in EXPENSE_EDITABLE_FIELDS:
            raise InvalidFinanceOperation({"reason": "field_not_editable", "field": field})
    _require_void_window(expense.hotel, _expense_business_date(expense))
    changes = {}
    for field, value in fields.items():
        value = (value or "").strip() if isinstance(value, str) else value
        old = getattr(expense, field)
        if value != old:
            changes[field] = (old, value)
            setattr(expense, field, value)
    if not changes:
        # Nothing actually changed — no write, no activity (owner rule).
        return expense
    expense.updated_by = _actor(user)
    expense.save(update_fields=[*changes.keys(), "updated_by", "updated_at"])
    diff = " · ".join(
        f"{field}: '{old}' → '{new}'" for field, (old, new) in changes.items()
    )
    _record_event(
        expense.hotel,
        event_type="expense.updated",
        severity="info",
        title=f"Expense {expense.expense_number} updated",
        message=diff,
        user=user,
        obj=expense,
    )
    return expense


@transaction.atomic
def void_expense(expense, *, reason, user=None) -> Expense:
    """Void a voucher — only inside its own open business date. Later
    corrections go through ``reverse_expense``."""
    reason = _require_reason(reason)
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status == PostingStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    if expense.reversals.filter(status=PostingStatus.POSTED).exists():
        raise InvalidFinanceOperation({"reason": "expense_reversed"})
    _require_void_window(expense.hotel, _expense_business_date(expense))
    expense.status = PostingStatus.VOIDED
    expense.void_reason = reason
    expense.voided_at = timezone.now()
    expense.voided_by = _actor(user)
    expense.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    _record_event(
        expense.hotel,
        event_type="expense.voided",
        severity="danger",
        title=f"Expense {expense.expense_number} voided",
        message=f"{expense.amount} {expense.currency} · {reason}",
        user=user,
        obj=expense,
    )
    return expense


@transaction.atomic
def reverse_expense(expense, *, reason, user=None) -> Expense:
    """Post the FULL counter-voucher (negative amount, new EXP number) for an
    original whose void window has closed. The original stays posted and is
    never edited; reversals cannot be reversed and repeats are impossible."""
    from apps.shifts.services import get_open_shift_for

    reason = _require_reason(reason)
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != PostingStatus.POSTED:
        raise InvalidFinanceOperation({"reason": "not_posted"})
    if expense.reverses_id is not None:
        raise InvalidFinanceOperation({"reason": "cannot_reverse_reversal"})
    if expense.reversals.filter(status=PostingStatus.POSTED).exists():
        raise ExpenseAlreadyReversed({"expense": expense.id})
    _require_void_window_passed(expense.hotel, _expense_business_date(expense))
    business_date = _business_date(expense.hotel)
    _ensure_day_open(expense.hotel, business_date)
    actor = _actor(user)
    try:
        reversal = Expense.objects.create(
            hotel=expense.hotel,
            expense_number=next_number(expense.hotel, NumberKind.EXPENSE),
            category=expense.category,
            description=f"Reversal ({expense.expense_number}): {reason}",
            amount=-expense.amount,
            currency=expense.currency,
            method=expense.method,
            paid_at=timezone.now(),
            business_date=business_date,
            reverses=expense,
            shift=get_open_shift_for(user, expense.hotel),
            vendor_name=expense.vendor_name,
            reference=expense.reference,
            notes=reason,
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError:
        raise ExpenseAlreadyReversed({"expense": expense.id})
    _record_event(
        expense.hotel,
        event_type="expense.reversed",
        severity="warning",
        title=f"Expense {expense.expense_number} reversed",
        message=(
            f"{reversal.expense_number}: {reversal.amount} "
            f"{reversal.currency} · {reason}"
        ),
        user=user,
        obj=reversal,
    )
    return reversal


# --- Refundable insurance (STAYS-ARRIVALS-DEPARTURES §35 / owner D2) ---------
# Held SEPARATELY from the folio: never revenue, never on the folio balance. A
# documented deduction posts ONLY the deducted portion to the folio (a payment
# settling the account); a refund returns money to the guest (no folio movement).


def _refresh_insurance_status(ins) -> None:
    """Recompute the derived insurance status from held/deducted/refunded."""
    from .models import InsuranceStatus

    held = ins.amount - ins.deducted_amount - ins.refunded_amount
    if held >= ins.amount:
        ins.status = InsuranceStatus.HELD
    elif held > ZERO:
        ins.status = InsuranceStatus.PARTIALLY_DEDUCTED
    elif ins.deducted_amount == ZERO:
        ins.status = InsuranceStatus.REFUNDED
    else:
        ins.status = InsuranceStatus.CONSUMED
    if held <= ZERO and ins.settled_at is None:
        ins.settled_at = timezone.now()


@transaction.atomic
def record_insurance(*, hotel, amount, currency=None, method=None, reservation=None,
                     stay=None, reference="", notes="", user=None):
    """Record a REFUNDABLE insurance/security amount held SEPARATELY from the
    folio (§35). Never revenue; never on the folio balance. Positive amount."""
    from .models import PaymentMethod, RefundableInsurance

    amt = money(amount)
    if amt <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    return RefundableInsurance.objects.create(
        hotel=hotel,
        reservation=reservation,
        stay=stay,
        currency=(currency or _hotel_currency(hotel)).upper(),
        amount=amt,
        method=(method or PaymentMethod.CASH),
        reference=reference or "",
        notes=notes or "",
        received_by=_actor(user),
        received_at=timezone.now(),
        created_by=_actor(user),
    )


@transaction.atomic
def refund_insurance(insurance, *, amount=None, reason="", user=None):
    """Refund held insurance to the guest (§35). The money returns to the guest —
    NOT a folio movement. ``amount`` defaults to the full remaining held amount."""
    from .models import RefundableInsurance

    insurance = RefundableInsurance.objects.select_for_update().get(pk=insurance.pk)
    held = insurance.amount - insurance.deducted_amount - insurance.refunded_amount
    amt = money(amount) if amount is not None else held
    if amt <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if amt > held:
        raise InvalidAmount({"field": "amount", "reason": "exceeds_held"})
    insurance.refunded_amount += amt
    _refresh_insurance_status(insurance)
    insurance.settled_by = _actor(user)
    insurance.save()
    _record_event(
        insurance.hotel,
        event_type="insurance.refunded",
        severity="info",
        title=f"Insurance refunded {amt} {insurance.currency}",
        message=reason or "",
        user=user,
        obj=insurance,
    )
    return insurance


@transaction.atomic
def deduct_insurance(insurance, *, amount, reason, user=None):
    """Deduct part of the held insurance for a documented reason (§35): the
    deducted portion is posted to the stay's folio as a documented payment
    (settling the account) — needs a reason + audit. Reduces the held amount."""
    reason = _require_reason(reason)
    from .models import PaymentMethod, RefundableInsurance

    insurance = RefundableInsurance.objects.select_for_update().get(pk=insurance.pk)
    held = insurance.amount - insurance.deducted_amount - insurance.refunded_amount
    amt = money(amount)
    if amt <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if amt > held:
        raise InvalidAmount({"field": "amount", "reason": "exceeds_held"})
    if insurance.stay_id is None:
        raise InvalidFinanceOperation({"reason": "insurance_not_linked_to_stay"})
    folio = ensure_stay_folio(insurance.stay, user=user)
    record_payment(
        folio,
        amount=amt,
        method=PaymentMethod.OTHER,
        payer_name="Insurance",
        reference=f"insurance:{insurance.id}",
        notes=f"insurance deduction: {reason}"[:255],
        user=user,
    )
    insurance.deducted_amount += amt
    _refresh_insurance_status(insurance)
    insurance.settled_by = _actor(user)
    insurance.save()
    _record_event(
        insurance.hotel,
        event_type="insurance.deducted",
        severity="warning",
        title=f"Insurance deducted {amt} {insurance.currency}",
        message=reason,
        user=user,
        obj=insurance,
    )
    return insurance


# --- Stay-folio settlement + credit refund (STAYS §34/§37) ------------------


def _resolve_payment_fx(folio, *, amount, currency, original_amount,
                        exchange_rate, rate_basis, user):
    """Resolve a payment's BASE amount + FX snapshot for ``folio`` (§34/§57).

    Same currency as the folio → ``amount`` IS the base amount. Foreign currency →
    a manual ``exchange_rate`` AND the tendered ``original_amount`` are required and
    the base amount is DERIVED (never client-trusted); the direction is dictated by
    ``rate_basis``. Returns ``(base_amount, fx_dict)``. Mirrors the deposit path.
    """
    base_currency = folio.currency
    resolved_currency = (currency or base_currency).strip().upper()
    accepted = _accepted_currencies(folio.hotel)
    if resolved_currency not in accepted:
        raise InvalidFinanceOperation(
            {"reason": "currency_not_accepted", "currency": resolved_currency,
             "accepted": accepted}
        )
    if resolved_currency == base_currency.upper():
        if amount is None or money(amount) <= ZERO:
            raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
        base_amount = money(amount)
        fx = dict(payment_currency=base_currency, original_amount=base_amount,
                  exchange_rate=None, rate_basis="", rate_captured_at=None,
                  rate_entered_by=None)
    else:
        resolved_basis = _resolve_rate_basis(rate_basis)
        if exchange_rate is None or Decimal(str(exchange_rate)) <= ZERO:
            raise InvalidFinanceOperation(
                {"reason": "exchange_rate_required", "currency": resolved_currency}
            )
        if original_amount is None or money(original_amount) <= ZERO:
            raise InvalidFinanceOperation(
                {"reason": "original_amount_required", "currency": resolved_currency}
            )
        rate = Decimal(str(exchange_rate))
        original = money(original_amount)
        if resolved_basis == RateBasis.PAYMENT_PER_BASE:
            if rate == ZERO:
                raise InvalidFinanceOperation({"reason": "invalid_exchange_rate"})
            base_amount = money(original / rate)
        else:
            base_amount = money(original * rate)
        fx = dict(payment_currency=resolved_currency, original_amount=original,
                  exchange_rate=rate, rate_basis=resolved_basis,
                  rate_captured_at=timezone.now(), rate_entered_by=user)
    if base_amount <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if base_amount.copy_abs() >= MONEY_MAX_ABS:
        raise InvalidFinanceOperation({"reason": "amount_out_of_range"})
    return base_amount, fx


@transaction.atomic
def record_folio_settlement(folio, *, method, amount=None, currency=None,
                            original_amount=None, exchange_rate=None, rate_basis="",
                            payer_name="", reference="", notes="", user=None):
    """Settle a stay/folio balance with a payment (§34), multi-currency aware
    (same FX resolution as a deposit). Only on an OPEN folio; the base amount alone
    drives ``folio_balance``. A manual FX rate is gated by ``exchange_rate.override``
    at the view layer."""
    folio = _lock_folio(folio)
    _guard_open(folio)
    base_amount, fx = _resolve_payment_fx(
        folio, amount=amount, currency=currency, original_amount=original_amount,
        exchange_rate=exchange_rate, rate_basis=rate_basis, user=user,
    )
    return record_payment(
        folio, amount=base_amount, method=method, payer_name=payer_name,
        reference=reference, notes=notes, user=user, **fx,
    )


@transaction.atomic
def refund_folio_credit(folio, *, amount=None, reason, method=None, user=None):
    """Refund a folio CREDIT balance to the guest (§37): when posted payments
    exceed posted charges (overpaid), return the excess. Posts a NEGATIVE payment
    (money out) that brings the balance toward zero; the original payments are
    NEVER deleted and the financial date is never changed silently. Requires a
    reason (finance.refund at the view layer)."""
    from .models import PaymentMethod

    reason = _require_reason(reason)
    folio = _lock_folio(folio)
    _guard_open(folio)
    balance = folio_balance(folio)["balance"]
    credit = -balance  # positive when the guest overpaid (balance is negative)
    if credit <= ZERO:
        raise InvalidFinanceOperation(
            {"reason": "no_credit_to_refund", "balance": str(balance)}
        )
    amt = money(amount) if amount is not None else credit
    if amt <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if amt > credit:
        raise InvalidFinanceOperation({"reason": "exceeds_credit", "credit": str(credit)})
    business_date = _business_date(folio.hotel)
    _ensure_day_open(folio.hotel, business_date)
    refund = Payment.objects.create(
        hotel=folio.hotel,
        folio=folio,
        receipt_number=next_number(folio.hotel, NumberKind.RECEIPT),
        amount=money(-amt),
        currency=folio.currency,
        method=(method or PaymentMethod.CASH),
        status=PostingStatus.POSTED,
        paid_at=timezone.now(),
        business_date=business_date,
        reference="refund",
        notes=reason[:255],
        created_by=_actor(user),
    )
    _record_event(
        folio.hotel,
        event_type="folio.refund",
        severity="warning",
        title=f"Refund {amt} {folio.currency} on folio {folio.folio_number}",
        message=reason,
        user=user,
        obj=refund,
    )
    return refund
