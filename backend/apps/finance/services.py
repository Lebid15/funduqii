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

import hashlib
import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.common.exceptions import (
    ActiveInvoiceExists,
    ChargeAlreadyAdjusted,
    ExpenseAlreadyReversed,
    FolioAwaitingFinalCharges,
    FolioClosed,
    FolioCurrencyMismatch,
    FolioHasPostings,
    FolioNotBalanced,
    IdempotencyKeyConflict,
    InvalidAmount,
    InvalidFinanceOperation,
    MissingAgreedNightlyRate,
    PaymentAlreadyReversed,
    ReservationFolioNotSupported,
    StayNotInHouse,
    VoidReasonRequired,
    VoidWindowClosed,
    VoidWindowOpen,
)

from .constants import ChargeSource
from .models import (
    CREDIT_CHARGE_TYPES,
    DEFAULT_EXPENSE_TYPE_NAMES,
    ChargeType,
    Expense,
    ExpenseType,
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
    normalize_expense_type_name,
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
                  obj=None, dedup_key=None) -> None:
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
        dedup_key=dedup_key,
    )


# --- Balance ----------------------------------------------------------------

#: The SINGLE definition of "what counts toward a folio balance": only rows with
#: this posting status contribute, a charge adds its ``total_amount`` and a
#: payment subtracts its ``amount``. Both the per-folio ``folio_balance`` and the
#: DB-aggregate finance overview (``aggregate_open_folio_balances``) filter on
#: THIS constant and these field names, so the two derivations can never drift
#: (a parity test locks the equivalence). Voided charges/payments (status
#: ``VOIDED``) are excluded; posted negative adjustment/reversal rows ARE
#: included and net the original out, exactly as intended.
BALANCE_STATUS = PostingStatus.POSTED
BALANCE_CHARGE_FIELD = "total_amount"
BALANCE_PAYMENT_FIELD = "amount"


def _balance_dict(total_charges, total_payments) -> dict:
    """Assemble the balance result from already-summed charge/payment totals —
    the ONE arithmetic used by every balance derivation."""
    total_charges = money(total_charges or ZERO)
    total_payments = money(total_payments or ZERO)
    return {
        "total_charges": total_charges,
        "total_payments": total_payments,
        "balance": money(total_charges - total_payments),
    }


def folio_balance(folio) -> dict:
    """Re-derive ONE folio's totals from its posted charges and payments.

    COST (C4 — do not misread this): each call issues TWO queries, ALWAYS.
    ``.filter()`` on a related manager builds a fresh queryset and therefore
    ALWAYS bypasses ``prefetch_related``'s cache, so prefetching the caller's
    folios does NOT make this free — it merely fetches the same rows twice. (The
    pre-P0 finance overview carried exactly that useless ``prefetch_related`` and
    still cost 2N+3 queries.) Never call this in a loop over folios: use
    ``aggregate_open_folio_balances``, which computes the SAME
    ``BALANCE_STATUS``/field definition over the DB in a constant number of
    queries, so the two derivations can never drift.
    """
    charges = folio.charges.filter(status=BALANCE_STATUS)
    payments = folio.payments.filter(status=BALANCE_STATUS)
    total_charges = sum((getattr(c, BALANCE_CHARGE_FIELD) for c in charges), ZERO)
    total_payments = sum((getattr(p, BALANCE_PAYMENT_FIELD) for p in payments), ZERO)
    return _balance_dict(total_charges, total_payments)


def aggregate_open_folio_balances(folios, *, base_currency) -> dict:
    """Finance-overview aggregation across a queryset of folios.

    Reuses ``folio_balance``'s exact definition (``BALANCE_STATUS`` charges'
    ``total_amount`` minus ``BALANCE_STATUS`` payments' ``amount``) but computes
    it over the DB in a CONSTANT number of queries regardless of how many folios
    are open — no per-folio query, so the endpoint has no N+1.

    Currency is kept SEPARATE exactly as the previous per-folio loop did: only
    folios whose ``currency`` equals ``base_currency`` contribute to the summed
    ``outstanding`` / ``unpaid`` numbers (money is never added across
    currencies); the rest are counted and their distinct currencies listed.

    Returns ``{"outstanding": Decimal, "unpaid": int, "foreign_count": int,
    "foreign_currencies": [str, ...]}``.
    """
    from django.db.models import Sum

    # S3 — the base-currency folio set is passed to the DB as a SUBQUERY (an
    # independent one, NOT correlated: it references no column of the outer
    # query), never as a materialized python list of ids. Sending ``id__in=[...]``
    # made the SQL text and the bind-parameter count grow linearly with the number
    # of open folios (measured: ~129KB of SQL at 20k folios) and would hard-fail
    # past PostgreSQL's 65535-parameter ceiling. ``.order_by()`` strips ``Folio``'s
    # default ordering, which is meaningless — and on some backends illegal —
    # inside an ``IN`` subquery.
    base_folios = folios.filter(currency=base_currency).order_by()
    base_ids_sq = base_folios.values("id")
    # Two independent grouped sums (NOT one query joining both relations, which
    # would fan out and multiply each side by the other's row count).
    charge_totals = {
        row["folio"]: row["t"]
        for row in FolioCharge.objects.filter(
            folio_id__in=base_ids_sq, status=BALANCE_STATUS
        )
        .values("folio")
        .annotate(t=Sum(BALANCE_CHARGE_FIELD))
    }
    payment_totals = {
        row["folio"]: row["t"]
        for row in Payment.objects.filter(
            folio_id__in=base_ids_sq, status=BALANCE_STATUS
        )
        .values("folio")
        .annotate(t=Sum(BALANCE_PAYMENT_FIELD))
    }
    outstanding = ZERO
    unpaid = 0
    # PARITY: iterating the folios that actually have a posted charge or payment is
    # equivalent to iterating every base-currency folio. A folio with neither
    # contributes ``money(0) - money(0) == 0`` to ``outstanding`` and is not
    # ``> 0``, so it can change neither number — it only cost a row to fetch.
    for fid in charge_totals.keys() | payment_totals.keys():
        balance = _balance_dict(
            charge_totals.get(fid), payment_totals.get(fid)
        )["balance"]
        outstanding += balance
        if balance > ZERO:
            unpaid += 1
    foreign = folios.exclude(currency=base_currency)
    return {
        "outstanding": money(outstanding),
        "unpaid": unpaid,
        "foreign_count": foreign.count(),
        "foreign_currencies": sorted(
            foreign.values_list("currency", flat=True).distinct()
        ),
    }


def _assert_money_bound(*values) -> None:
    """Reject any money value that would overflow a ``MONEY_KW`` column
    (``abs`` at/above ``MONEY_MAX_ABS``) with a clean typed 400 instead of
    letting it surface later as a DB ``NumericValueOutOfRange`` (500)."""
    for value in values:
        if abs(Decimal(value)) >= MONEY_MAX_ABS:
            raise InvalidAmount({"field": "amount", "reason": "amount_too_large"})


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
    # Overflow guard on the normal charge path (quantity x unit_amount, + tax).
    _assert_money_bound(amount, tax_amount, total)
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
                 origin="manual", agreed_currency=None) -> Folio:
    """Open a folio. The client-facing ``currency`` is ALWAYS ignored (documented
    decision — a client can never set a folio currency). ``agreed_currency`` is an
    INTERNAL override used ONLY by the stay-folio path (FIX 1): the folio adopts the
    BOOKING's agreed currency instead of the hotel's CURRENT default; when it is
    ``None`` the hotel default currency is used exactly as before. A reservation may
    only be referenced together with its stay: pre-arrival folios are not
    supported."""
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
            # FIX 1 — the stay-folio path may adopt the BOOKING's agreed currency;
            # every other caller (agreed_currency None) keeps the hotel default.
            currency=agreed_currency or _hotel_currency(hotel),
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


def _stay_folio_currency(stay) -> str:
    """The currency the stay's folio must use (FIX 1 — the folio adopts the
    BOOKING's agreed currency, NOT the hotel's CURRENT default).

    * PRICED stay (its reservation line has a non-null ``agreed_nightly_rate``): the
      folio currency = that line's ``agreed_rate_currency``. If the reservation
      feeding the stay has MULTIPLE priced lines whose currencies CONFLICT (>1
      distinct) OR a priced line has a MISSING currency, raise
      :class:`FolioCurrencyMismatch` (check-in is BLOCKED, no folio created).
    * UNPRICED stay (no agreed rate): fall back to the hotel default currency —
      there is no agreed currency to honor, so walk-in / unpriced check-in keeps
      working (the rate is remediated later).

    NO conversion, NO auto-FX anywhere.
    """
    line = stay.reservation_line
    own_priced = line is not None and line.agreed_nightly_rate is not None
    if not own_priced:
        return _hotel_currency(stay.hotel)
    reservation = stay.reservation
    priced = (
        [rl for rl in reservation.lines.all() if rl.agreed_nightly_rate is not None]
        if reservation is not None
        else [line]
    )
    currencies = set()
    for rl in priced:
        cur = (rl.agreed_rate_currency or "").strip()
        if not cur:
            raise FolioCurrencyMismatch(
                {"reason": "missing_line_currency", "line": rl.id}
            )
        currencies.add(cur)
    if len(currencies) > 1:
        raise FolioCurrencyMismatch(
            {
                "reason": "conflicting_line_currencies",
                "currencies": sorted(currencies),
            }
        )
    return next(iter(currencies))


def _guard_existing_folio_currency(folio, agreed_currency):
    """Block (never silently change) when an existing folio's currency differs from
    the resolved agreed currency."""
    if folio.currency and folio.currency != agreed_currency:
        raise FolioCurrencyMismatch(
            {
                "reason": "existing_folio_currency",
                "folio_currency": folio.currency,
                "agreed_currency": agreed_currency,
            }
        )


@transaction.atomic
def ensure_stay_folio(stay, *, user=None) -> Folio:
    """Get-or-create the stay's ONE open folio (idempotent, race-safe).

    Called from check-in (same transaction: a failed folio rolls back the
    whole check-in) and from service-order posting. Links stay + guest +
    reservation, adopts the BOOKING's agreed currency (FIX 1), and never posts any
    charge, payment, or deposit.
    """
    stay = type(stay).objects.select_for_update().get(pk=stay.pk)
    # Restaurant closure (P0): a NEW operational folio may only be opened for
    # an IN-HOUSE stay — a departed/cancelled stay can never grow new money.
    # Reading, printing, and corrections on EXISTING folios are untouched;
    # check-in calls this while the stay is already in-house.
    if stay.status != "in_house":
        raise StayNotInHouse({"stay": stay.pk, "status": stay.status})
    # FIX 1 — resolve the currency the folio must carry (may BLOCK check-in on a
    # conflicting / missing agreed currency; no folio is created then).
    agreed_currency = _stay_folio_currency(stay)
    existing = Folio.objects.filter(
        hotel=stay.hotel, stay=stay, status=FolioStatus.OPEN
    ).first()
    if existing is not None:
        _guard_existing_folio_currency(existing, agreed_currency)
        return existing
    # Reservation-folio reuse (RESERVATIONS-FORM-REWORK — immediate check-in):
    # if a pre-arrival deposit opened the reservation's ONE folio (reservation
    # set, stay NULL), ATTACH this stay to that same folio instead of opening a
    # second one — the deposit then lives on the stay folio automatically (ONE
    # ledger). Backward-compatible: with no reservation, or no open reservation
    # folio, this is a no-op and the stay folio is created below exactly as
    # before. A currency mismatch BLOCKS (the atomic rolls the attach back).
    reused = _reuse_reservation_folio_for_stay(stay, user=user)
    if reused is not None:
        _guard_existing_folio_currency(reused, agreed_currency)
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
            agreed_currency=agreed_currency,
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
    # §32/§38 — a folio still flagged awaiting final charges must NOT close. This
    # is the single source of truth: the stay checkout gate also checks it, but
    # enforcing it here protects the direct FolioCloseView path too.
    if folio.awaiting_final_charges:
        raise FolioAwaitingFinalCharges(
            {
                "folio": folio.id,
                "folio_number": folio.folio_number,
                "reason": folio.awaiting_final_charges_note,
            }
        )
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
               tax_rate=ZERO, tax_amount=None, source=ChargeSource.MANUAL,
               user=None, adjusts=None, room_night=None, record_event=True,
               currency_snapshot=None, service_name_snapshot=None,
               unit_price_snapshot=None, tax_rate_snapshot=None,
               source_reference=None) -> FolioCharge:
    """Post a charge dated to the CURRENT open hotel business date (the
    caller never chooses the date — no back- or future-dating). ``room_night``
    is set only for a room-night charge and is the idempotency key enforced by
    the partial unique index (folio + room_night).

    The ``*_snapshot`` / ``source_reference`` kwargs are OPTIONAL frozen
    metadata (used by the guest extra-services flow) — when omitted they persist
    as NULL, so every existing caller is unchanged. There is NO FK to any
    catalog: a later rename/reprice cannot alter a posted charge's snapshot.
    """
    # H1 revenue-integrity: this is the SINGLE creator of every FolioCharge, so it
    # is the one chokepoint that guarantees a ROOM charge can only ever be a
    # per-night charge. A ROOM charge without a ``room_night`` is never legitimate
    # (the central night poster ``ensure_due_room_charges`` always supplies it); an
    # unlinked ROOM charge would otherwise sit on the folio and be mistaken for
    # "already billed", silently disabling automated nightly billing (revenue leak).
    if charge_type == ChargeType.ROOM and room_night is None:
        raise InvalidFinanceOperation({"reason": "manual_room_charge_forbidden"})
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
        # Same overflow guard as compute_charge_totals for the explicit-tax path.
        _assert_money_bound(amount, tax_amount, total)
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
        room_night=room_night,
        currency_snapshot=currency_snapshot,
        service_name_snapshot=service_name_snapshot,
        unit_price_snapshot=(
            money(unit_price_snapshot) if unit_price_snapshot is not None else None
        ),
        tax_rate_snapshot=(
            Decimal(tax_rate_snapshot) if tax_rate_snapshot is not None else None
        ),
        source_reference=source_reference,
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
                            charge_type, tax_rate=ZERO,
                            tax_amount=None, source=ChargeSource.ROOM_ACCOUNT,
                            user=None) -> FolioCharge:
    """Post an "on room account" item: the charge is added to the folio and
    left OWING. This is a thin, intent-revealing delegate to ``add_charge``.

    ``charge_type`` is a REQUIRED keyword (no default): the earlier ``ROOM``
    default was ambiguous — a caller could silently post a ROOM charge that
    would trip the room-night guard. The caller must now state the type
    explicitly. This delegate NEVER sets ``room_night`` (it is left NULL); the
    per-night idempotency key is owned solely by the central night service
    ``ensure_due_room_charges``.

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


# STAYS-ARRIVALS-DEPARTURES — every room NIGHT is its own charge, marked with a
# short ``source`` and its ``room_night`` date. The stable idempotency key is
# (folio, room_night), enforced by a partial unique index, so check-in, a retry,
# the pre-checkout safety net, the manual ensure-room-charges endpoint, the daily
# close (``post_due_room_charges_for_hotel`` in ``close_business_day``), and any
# two CONCURRENT posters all converge on exactly one charge per night.
ROOM_NIGHT_SOURCE = ChargeSource.STAY_ROOM


def _room_rate_for_night(stay, night):
    """Resolve ``(rate, currency, label)`` for one room night from the stay's rate
    periods — the AGREED price for that date, NEVER the live catalog rate.

    STAYS rate-integrity round: every night is billed from the ``StayRatePeriod``
    whose half-open range ``[start_date, end_date)`` covers ``night`` (the booking
    period, an extension, or an override). The periods are read from the
    (preferably prefetched) ``stay.rate_periods`` relation, evaluated once and
    cached on the instance so a multi-night loop issues no per-night query.

    * period found, rate > 0 -> ``(money(rate), currency, label)`` — bill it.
    * period found, rate NULL -> raise :class:`MissingAgreedNightlyRate`. NULL is
      the agreed price MISSING (must be remediated), NOT a free night: it is NEVER
      skipped and NEVER posted as zero.
    * NO period covers the night -> raise :class:`MissingAgreedNightlyRate`.

    Either gap must fail posting (and therefore checkout / daily close) so nothing
    settles short and no live-catalog rate is ever used. The display label always
    comes from the room type when known.
    """
    line = stay.reservation_line
    room_type = getattr(line, "room_type", None) if line is not None else None
    label = room_type.name if room_type is not None else "Room"
    # Prefer the per-call cache ``ensure_due_room_charges`` sets (kept fresh each
    # call so an extension that just added a period is never missed); fall back to
    # a direct read for a standalone call. Never write the cache here, so a reused
    # stay instance can never carry a STALE period list between calls.
    periods = getattr(stay, "_rate_periods_cache", None)
    if periods is None:
        periods = list(stay.rate_periods.all())
    for period in periods:
        if period.start_date <= night < period.end_date:
            if period.nightly_rate is None:
                # A covering-but-unpriced period: agreed price MISSING, not free.
                raise MissingAgreedNightlyRate(
                    {
                        "stay": stay.id,
                        "room_night": night.isoformat(),
                        "reason": "unpriced_period",
                    }
                )
            return money(period.nightly_rate), period.currency, label
    raise MissingAgreedNightlyRate(
        {"stay": stay.id, "room_night": night.isoformat()}
    )


@transaction.atomic
def ensure_due_room_charges(stay, *, as_of=None, user=None):
    """Idempotently post one ROOM charge per CONSUMED night (owner correction to
    §24/§31): billing runs from the guest's ACTUAL arrival up to — but not
    including — the planned departure, and only for nights the hotel business date
    has already passed (``D < business_date``). Future nights are NEVER pre-posted
    — the folio only ever holds the nights the guest has actually stayed by the
    hotel's clock, so an early departure owes exactly the nights it consumed.

    Each night is keyed by its ``room_night`` date; the partial unique index on
    (folio, room_night) is the idempotency backstop, so a retry or a concurrent
    poster never double-posts. This function is invoked at CHECK-IN, by the
    pre-checkout safety net in ``CheckOutService``, by the manual
    ``stays/<id>/ensure-room-charges`` endpoint, AND by the daily close
    (``post_due_room_charges_for_hotel`` in ``close_business_day``). Skips an
    UNPRICED room type. The charge itself is dated to the current business date
    (no back-dating); the ``room_night``/description carry the night it settles.
    Returns the number of night charges newly posted.
    """
    # ``ensure_stay_folio`` locks the stay row (select_for_update), so concurrent
    # calls for the SAME stay already serialize here; the partial unique index on
    # (folio, room_night) is the DB backstop for any path that bypasses the lock.
    folio = ensure_stay_folio(stay, user=user)
    business_date = as_of or _business_date(stay.hotel)
    # STAYS rate-integrity round: load THIS stay's rate periods once, FRESH for
    # this call (an extension may have added one since this in-memory instance was
    # last billed), so the per-night resolver issues no per-night query and never
    # reads a stale list. Uses the prefetched relation when the caller provided it.
    stay._rate_periods_cache = list(stay.rate_periods.all())
    # H1 revenue-integrity: per-night idempotency is owned SOLELY by the
    # ``room_night``-keyed ``posted`` set below plus the partial unique index
    # (folio, room_night). A ROOM charge with room_night IS NULL is NOT a per-night
    # charge and must NEVER be read as evidence that a night is billed, nor be
    # allowed to disable this poster — the previous silent ``return 0`` here is
    # exactly what let an unlinked ROOM charge silently suppress ALL nightly
    # billing (revenue leak). New unlinked ROOM charges are now impossible (blocked
    # in ``add_charge`` + the charge serializer), so any such row is a pre-existing
    # LEGACY anomaly: surface it (non-silent) for owner remediation and CONTINUE
    # billing the due nights.
    #
    # NOTE (legacy-data policy — OWNER DECISION): if a genuine legacy row is a
    # whole-stay AGGREGATE, continuing to post per-night charges double-counts
    # against it, so such rows must be reconciled (void-not-delete) before this
    # runs on that folio. See the H1 report; no legacy rows are altered here.
    if folio.charges.filter(
        type=ChargeType.ROOM,
        status=PostingStatus.POSTED,
        room_night__isnull=True,
    ).exists():
        _record_event(
            stay.hotel,
            event_type="charge.room_unlinked_detected",
            severity="warning",
            title="Unlinked room charge detected on folio",
            message=(
                f"Folio {folio.folio_number} carries a ROOM charge with no "
                "room_night; nightly billing proceeds — this legacy row needs "
                "review (void-not-delete)."
            ),
            user=user,
            obj=folio,
            # De-dup the alert per folio: ensure_due_room_charges runs on every
            # check-in / pre-checkout / daily close, so without this the same
            # unreconciled folio would notify finance staff on every run.
            dedup_key=f"room-unlinked-folio-{folio.pk}",
        )
    posted = set(
        folio.charges.filter(
            type=ChargeType.ROOM,
            status=PostingStatus.POSTED,
            room_night__isnull=False,
        ).values_list("room_night", flat=True)
    )
    # FIX-1 (billing window START): billing begins at the guest's ACTUAL arrival,
    # so nights before check-in are never billed (consumed nights only). Convert
    # the aware ``actual_check_in_at`` to the hotel-local date; when no arrival is
    # recorded — or the hotel carries an INVALID timezone string (the ``timezone``
    # field has no validators) — fall back to the planned check-in, mirroring the
    # ``_computed_business_date`` guard so a bad tz never breaks check-in/-out. The
    # upper bound (planned check-out) is deliberately left unchanged — overstay is
    # a separate decision.
    from apps.shifts.services import _hotel_timezone

    arrival_date = stay.planned_check_in_date
    if stay.actual_check_in_at is not None:
        try:
            arrival_date = timezone.localtime(
                stay.actual_check_in_at, ZoneInfo(_hotel_timezone(stay.hotel))
            ).date()
        except (KeyError, ValueError):
            # ZoneInfoNotFoundError subclasses KeyError; a bad tz name keeps the
            # safe planned-check-in fallback rather than failing the posting path.
            arrival_date = stay.planned_check_in_date
    night = max(stay.planned_check_in_date, arrival_date)
    end = stay.planned_check_out_date
    count = 0
    while night < end and night < business_date:
        if night not in posted:
            # STAYS rate-integrity remediation: resolve THIS night's agreed rate
            # from the stay's rate periods. The resolver RAISES
            # MissingAgreedNightlyRate for either a night with NO covering period OR
            # a covering period whose rate is NULL (agreed price missing — never a
            # free night, never a live-catalog fallback), so a rate gap correctly
            # fails checkout / daily close instead of settling short.
            rate, currency, label = _room_rate_for_night(stay, night)
            # ITEM 7 (currency hardening): a priced period MUST carry an explicit
            # currency equal to the folio currency — the room charge posts in the
            # folio currency and there is no FX conversion for room nights here. An
            # empty OR mismatched currency is refused (never a silent wrong-currency
            # post).
            if not currency or currency != folio.currency:
                raise InvalidFinanceOperation(
                    {
                        "reason": (
                            "rate_currency_required"
                            if not currency
                            else "rate_currency_mismatch"
                        ),
                        "room_night": night.isoformat(),
                        "rate_currency": currency,
                        "folio_currency": folio.currency,
                    }
                )
            try:
                # add_charge is @transaction.atomic -> a savepoint, so a unique
                # collision from a concurrent poster rolls back only this insert
                # and leaves the surrounding transaction usable.
                add_charge(
                    folio,
                    charge_type=ChargeType.ROOM,
                    description=f"{label} — night {night.isoformat()}",
                    quantity=1,
                    unit_amount=rate,
                    source=ROOM_NIGHT_SOURCE,
                    room_night=night,
                    user=user,
                )
                count += 1
            except IntegrityError:
                # FIX-3: a concurrent poster may have inserted THIS night between
                # our read and our insert, so the partial unique index (folio,
                # room_night) rejected the duplicate. Re-query: if the night is now
                # POSTED the invariant (one charge per night) holds and we treat it
                # as done. But if it is NOT posted then this IntegrityError is not a
                # uniqueness collision — do not silently swallow it; re-raise.
                if not folio.charges.filter(
                    type=ChargeType.ROOM,
                    room_night=night,
                    status=PostingStatus.POSTED,
                ).exists():
                    raise
            posted.add(night)
        night = night + timedelta(days=1)
    return count


@transaction.atomic
def post_due_room_charges_for_hotel(hotel, *, business_date=None, user=None) -> int:
    """STAYS ITEM-2 — post every room night now DUE for the hotel's IN-HOUSE
    stays, in one tenant-scoped pass.

    Iterates the hotel's in-house stays and runs the central idempotent
    ``ensure_due_room_charges`` on each. That service decides which nights are due
    (never a future night, never on/after the planned check-out — the billing cap
    stays intact) and never double-posts.

    NO N+1 on active stays (owner requirement):
      * The business date is read ONCE here (not re-locked per stay). The daily
        close already holds the ``HotelSettings`` lock and knows the closing date,
        so it passes ``business_date`` and no per-stay ``lock_business_date`` runs;
        called standalone, we take the lock exactly once. It is forwarded as
        ``as_of`` so ``ensure_due_room_charges`` skips its own per-stay read. The
        posted charge is still dated to the real business date by ``add_charge``
        (``as_of`` only BOUNDS the night loop; the charge computes its own date).
      * ``hotel__settings`` is ``select_related`` so the per-stay hotel-timezone
        lookup (``_hotel_timezone`` in the arrival-window calc) is served from the
        already-fetched row, not a query per stay. Room / room type / reservation /
        line are joined for the same reason.

    Designed to run INSIDE the daily close's atomic block, immediately before the
    snapshot is built, so the day's folios and room revenue reflect the consumed
    nights. Because the close is atomic, a failure posting ANY stay rolls the
    whole close back (no partial snapshot, no CLOSED status, no date roll) and
    surfaces a diagnosable exception. Returns the total night charges newly posted.
    """
    from apps.stays.models import Stay, StayStatus

    if business_date is None:
        business_date = _business_date(hotel)
    stays = (
        Stay.objects.filter(hotel=hotel, status=StayStatus.IN_HOUSE)
        .select_related(
            "hotel",
            "hotel__settings",
            "room",
            "room__room_type",
            "reservation",
            "reservation_line",
            "reservation_line__room_type",
        )
        # STAYS rate-integrity round: the per-night resolver reads each stay's
        # rate periods, so prefetch them here to keep this a fixed-query pass
        # (no per-stay rate-period query).
        .prefetch_related("rate_periods")
        .order_by("id")
    )
    total = 0
    for stay in stays:
        total += ensure_due_room_charges(stay, as_of=business_date, user=user)
    return total


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
            source=ChargeSource.ADJUSTMENT,
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


# --- Expense types (manageable per-hotel categories) ------------------------


def create_expense_type(hotel, *, name, is_active=True, user=None) -> ExpenseType:
    """Add a hotel-scoped expense type. Name is required and unique within the
    hotel after normalization (trim + collapse whitespace + lower-case)."""
    clean = " ".join((name or "").split())
    if not clean:
        raise InvalidFinanceOperation({"reason": "name_required"})
    normalized = normalize_expense_type_name(clean)
    actor = _actor(user)
    try:
        with transaction.atomic():
            etype = ExpenseType.objects.create(
                hotel=hotel,
                name=clean,
                name_normalized=normalized,
                is_active=bool(is_active),
                created_by=actor,
                updated_by=actor,
            )
    except IntegrityError:
        raise InvalidFinanceOperation({"reason": "duplicate_name", "name": clean})
    _record_event(
        hotel,
        event_type="expense_type.created",
        severity="info",
        title=f"Expense type '{etype.name}' created",
        message=etype.name,
        user=user,
        obj=etype,
    )
    return etype


@transaction.atomic
def update_expense_type(expense_type, *, name=None, is_active=None, user=None) -> ExpenseType:
    """Rename and/or (de)activate a type — NEVER a hard delete. A deactivated
    type is hidden from the create form but stays on historical rows/reports."""
    etype = ExpenseType.objects.select_for_update().get(pk=expense_type.pk)
    before = (etype.name, etype.is_active)
    if name is not None:
        clean = " ".join((name or "").split())
        if not clean:
            raise InvalidFinanceOperation({"reason": "name_required"})
        etype.name = clean
        etype.name_normalized = normalize_expense_type_name(clean)
    if is_active is not None:
        etype.is_active = bool(is_active)
    etype.updated_by = _actor(user)
    try:
        # A SAVEPOINT so a duplicate-name violation does not poison the
        # surrounding transaction on PostgreSQL.
        with transaction.atomic():
            etype.save(
                update_fields=["name", "name_normalized", "is_active", "updated_by", "updated_at"]
            )
    except IntegrityError:
        raise InvalidFinanceOperation({"reason": "duplicate_name", "name": etype.name})
    after = (etype.name, etype.is_active)
    if before != after:
        _record_event(
            etype.hotel,
            event_type="expense_type.updated",
            severity="info",
            title=f"Expense type '{etype.name}' updated",
            message=f"name: '{before[0]}' → '{after[0]}' · active: {before[1]} → {after[1]}",
            user=user,
            obj=etype,
        )
    return etype


def ensure_default_expense_types(hotel, *, user=None) -> int:
    """Seed the default expense-type catalogue for ``hotel``. Returns how many
    types were actually created.

    Called from the central hotel-creation path so a hotel provisioned AFTER the
    expenses migrations is immediately usable: the type is REQUIRED on an
    expense, so a hotel with an empty catalogue could not record one at all
    until someone with ``expenses.manage_types`` added the first type.

    IDEMPOTENT — matches on the normalized name, so calling it again (or on a
    hotel the backfill already seeded) creates nothing and never raises on the
    per-hotel uniqueness constraint.
    """
    actor = _actor(user)
    created = 0
    for name in DEFAULT_EXPENSE_TYPE_NAMES:
        _, was_created = ExpenseType.objects.get_or_create(
            hotel=hotel,
            name_normalized=normalize_expense_type_name(name),
            defaults={
                "name": name,
                "is_active": True,
                "created_by": actor,
                "updated_by": actor,
            },
        )
        created += int(was_created)
    return created


def expense_currency_options(hotel) -> dict:
    """Base + accepted currencies for the expense entry form.

    Exposed through an ``expenses.view``-gated endpoint so an expenses clerk can
    enter a foreign-currency expense WITHOUT holding ``settings.view`` (the hotel
    settings resource) — otherwise the multi-currency feature is unusable for
    exactly the role that needs it.
    """
    return {
        "base_currency": _hotel_currency(hotel).upper(),
        "accepted_currencies": _accepted_currencies(hotel),
    }


def _resolve_expense_type_for_write(hotel, expense_type):
    """Resolve a type id/instance to an ACTIVE type belonging to ``hotel``.

    Rejects a foreign-hotel type (tenant isolation) and a deactivated type (you
    cannot file a new/edited expense under a retired category)."""
    etype_id = getattr(expense_type, "pk", expense_type)
    try:
        etype = ExpenseType.objects.get(pk=etype_id, hotel=hotel)
    except (ExpenseType.DoesNotExist, ValueError, TypeError):
        raise InvalidFinanceOperation({"reason": "expense_type_invalid"})
    if not etype.is_active:
        raise InvalidFinanceOperation({"reason": "expense_type_inactive", "expense_type": etype.id})
    return etype


# --- Expense FX (multi-currency; mirrors the payment FX resolver) ------------


def _resolve_expense_fx(hotel, *, amount, currency, original_amount,
                        exchange_rate, rate_basis, user):
    """Resolve an expense's BASE amount + FX snapshot (mirrors
    ``_resolve_payment_fx``). Same currency as the hotel base → ``amount`` IS the
    base amount, no rate stored. Foreign currency → a manual ``exchange_rate`` AND
    the spent ``original_amount`` are required and the base is DERIVED (never
    client-trusted). Returns ``(base_amount, fx_dict)`` keyed for Expense fields."""
    base_currency = _hotel_currency(hotel).upper()
    resolved_currency = (currency or base_currency).strip().upper()
    accepted = _accepted_currencies(hotel)
    if resolved_currency not in accepted:
        raise InvalidFinanceOperation(
            {"reason": "currency_not_accepted", "currency": resolved_currency,
             "accepted": accepted}
        )
    if resolved_currency == base_currency:
        if amount is None or money(amount) <= ZERO:
            raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
        base_amount = money(amount)
        fx = dict(original_currency=base_currency, original_amount=base_amount,
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
            base_amount = money(original / rate)
        else:
            base_amount = money(original * rate)
        fx = dict(original_currency=resolved_currency, original_amount=original,
                  exchange_rate=rate, rate_basis=resolved_basis,
                  rate_captured_at=timezone.now(), rate_entered_by=user)
    if base_amount <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if base_amount.copy_abs() >= MONEY_MAX_ABS:
        raise InvalidFinanceOperation({"reason": "amount_out_of_range"})
    return base_amount, fx


# --- Expense idempotency (mirrors the reservation creation key) --------------


def build_expense_fingerprint(*, hotel_id, expense_type_id, description, amount,
                              method, currency, original_amount, exchange_rate,
                              rate_basis, notes) -> str:
    """A stable sha256 over the SALIENT creation inputs (never server-derived
    values). A replayed idempotency key with a matching fingerprint is the same
    request (returns the same voucher); a different fingerprint is a 409."""
    def _s(v):
        return "" if v is None else str(v)

    payload = json.dumps(
        {
            "hotel": _s(hotel_id),
            "expense_type": _s(expense_type_id),
            "description": (description or "").strip(),
            "amount": _s(amount),
            "method": (method or "").strip(),
            "currency": (currency or "").strip().upper(),
            "original_amount": _s(original_amount),
            "exchange_rate": _s(exchange_rate),
            "rate_basis": (rate_basis or "").strip(),
            "notes": (notes or "").strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _assert_same_expense_request(existing, fingerprint) -> None:
    """Replaying a key with a materially DIFFERENT payload is a 409 — the
    original voucher is never returned as the result of a different request."""
    stored = existing.creation_request_fingerprint or ""
    if stored and fingerprint and stored != fingerprint:
        raise IdempotencyKeyConflict({"expense": existing.id})


#: Fields the atomic financial edit may change on a posted voucher, inside its
#: own open business date. business_date / paid_at / shift / status / reverses /
#: hotel / currency-base are never client-editable.
EXPENSE_EDITABLE_FIELDS = (
    "description", "notes", "method", "expense_type",
    "amount", "currency", "original_amount", "exchange_rate", "rate_basis",
)

#: Salient fields compared before/after an edit to build the audit diff.
_EXPENSE_DIFF_FIELDS = (
    "description", "notes", "method", "expense_type_id",
    "amount", "currency", "original_currency", "original_amount",
    "exchange_rate", "rate_basis",
)

#: Money inputs — presence of ANY re-resolves the base amount + FX snapshot.
_EXPENSE_MONEY_FIELDS = frozenset(
    {"amount", "currency", "original_amount", "exchange_rate", "rate_basis"}
)

#: Fields whose change moves the SHIFT CASH DRAWER (``method`` flips an expense
#: between cash and non-cash, so it counts too).
_EXPENSE_CASH_AFFECTING_FIELDS = _EXPENSE_MONEY_FIELDS | {"method"}


def _require_live_shift_for_money(expense) -> None:
    """Money may not change once the assigned shift has left OPEN.

    Closing a shift FREEZES its cash reconciliation (``expected_cash_amount``
    and ``cash_difference`` are stored at close, and the daily close snapshots
    them). Re-pricing an expense that belongs to a closed shift would silently
    invalidate that frozen record: cash would appear to have left the drawer
    with no trace, inside an immutable close. The correction after a shift has
    closed is a corrective movement posted to the CURRENT shift — never an edit
    of the settled one.
    """
    from apps.shifts.models import ShiftStatus

    shift = expense.shift
    if shift is not None and shift.status != ShiftStatus.OPEN:
        raise InvalidFinanceOperation(
            {"reason": "shift_not_open", "shift": shift.id, "status": shift.status}
        )


def _expense_snapshot(expense) -> dict:
    return {f: getattr(expense, f) for f in _EXPENSE_DIFF_FIELDS}


@transaction.atomic
def create_expense(hotel, *, expense_type, description, amount, method,
                   currency="", original_amount=None, exchange_rate=None,
                   rate_basis="", notes="",
                   idempotency_key="", request_fingerprint="", user=None) -> Expense:
    """Record an expense voucher stamped to NOW and to the current open hotel
    business date. ``amount`` is stored in the HOTEL BASE currency (derived for a
    foreign ``currency`` via a manual rate). The caller never chooses the
    timestamp, the financial date, or the base currency. A repeated submit with
    the same ``idempotency_key`` returns the SAME voucher (no double cash-out).

    The attachment is NOT set here — it is uploaded through the validated
    endpoint once the voucher exists (the file path needs the row's id).
    """
    from apps.shifts.services import get_open_shift_for

    key = (idempotency_key or "").strip()
    fingerprint = (request_fingerprint or "").strip()
    # A keyed create ALWAYS carries a fingerprint: the replay guard skips its
    # comparison when either side is blank, so a caller that supplied a key but
    # no fingerprint would silently lose the 409-on-different-payload guarantee.
    if key and not fingerprint:
        fingerprint = build_expense_fingerprint(
            hotel_id=hotel.id,
            expense_type_id=getattr(expense_type, "pk", expense_type),
            description=description,
            amount=amount,
            method=method,
            currency=currency,
            original_amount=original_amount,
            exchange_rate=exchange_rate,
            rate_basis=rate_basis,
            notes=notes,
        )
    # Fast-path replay before doing any work.
    if key:
        existing = Expense.objects.filter(
            hotel=hotel, creation_idempotency_key=key
        ).first()
        if existing is not None:
            _assert_same_expense_request(existing, fingerprint)
            return existing

    etype = _resolve_expense_type_for_write(hotel, expense_type)
    base_amount, fx = _resolve_expense_fx(
        hotel, amount=amount, currency=currency, original_amount=original_amount,
        exchange_rate=exchange_rate, rate_basis=rate_basis, user=user,
    )
    actor = _actor(user)
    business_date = _business_date(hotel)
    _ensure_day_open(hotel, business_date)
    try:
        with transaction.atomic():
            expense = Expense.objects.create(
                hotel=hotel,
                expense_number=next_number(hotel, NumberKind.EXPENSE),
                expense_type=etype,
                description=description,
                amount=base_amount,
                currency=_hotel_currency(hotel).upper(),
                method=method,
                paid_at=timezone.now(),
                business_date=business_date,
                shift=get_open_shift_for(user, hotel),
                notes=notes or "",
                creation_idempotency_key=key,
                creation_request_fingerprint=fingerprint,
                created_by=actor,
                updated_by=actor,
                **fx,
            )
    except IntegrityError:
        # A concurrent submit with the same key won the race — return its result
        # (idempotent) or 409 when the payloads differ. No second voucher.
        if key:
            existing = Expense.objects.filter(
                hotel=hotel, creation_idempotency_key=key
            ).first()
            if existing is not None:
                _assert_same_expense_request(existing, fingerprint)
                return existing
        raise
    _record_event(
        hotel,
        event_type="expense.created",
        severity="info",
        title=f"Expense {expense.expense_number} recorded",
        message=f"{expense.expense_type.name} · {expense.amount} {expense.currency} · {expense.method}",
        user=user,
        obj=expense,
    )
    return expense


@transaction.atomic
def update_expense(expense, *, user=None, **fields) -> Expense:
    """Atomic financial edit of a posted voucher, ONLY inside its own open
    business date. Locks the row + business day, applies the new descriptive AND
    money values (re-deriving the base amount + FX snapshot from scratch — the
    drawer/reports re-sum the new ``amount``, so the old effect is reversed and
    the new one applied within one transaction), and records a full before→after
    diff. A reversal row cannot be edited. Nothing changed → no write."""
    unknown = [f for f in fields if f not in EXPENSE_EDITABLE_FIELDS]
    if unknown:
        raise InvalidFinanceOperation({"reason": "field_not_editable", "field": unknown[0]})
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != PostingStatus.POSTED:
        raise InvalidFinanceOperation({"reason": "not_editable", "status": expense.status})
    if expense.reverses_id is not None:
        raise InvalidFinanceOperation({"reason": "cannot_edit_reversal"})
    _require_void_window(expense.hotel, _expense_business_date(expense))
    # A settled (non-open) shift has a FROZEN cash reconciliation — refuse any
    # change that would move its drawer.
    if _EXPENSE_CASH_AFFECTING_FIELDS & set(fields):
        _require_live_shift_for_money(expense)
    before = _expense_snapshot(expense)

    # Descriptive / classification.
    if "description" in fields:
        expense.description = (fields["description"] or "").strip()
    if "notes" in fields:
        expense.notes = (fields["notes"] or "").strip()
    if "method" in fields:
        expense.method = fields["method"]
    if "expense_type" in fields:
        expense.expense_type = _resolve_expense_type_for_write(
            expense.hotel, fields["expense_type"]
        )

    # Money/FX: any money input re-resolves the base amount + FX snapshot from
    # the NEW effective values (a full money re-specification, like create).
    saved_money_fields = []
    if _EXPENSE_MONEY_FIELDS & set(fields):
        # An omitted ``currency`` defaults to the voucher's CURRENT entry
        # currency — never blindly to the base. Otherwise a partial payload
        # (e.g. only ``amount``) would silently re-interpret a FOREIGN voucher
        # as base currency and WIPE its FX snapshot. Keeping the current
        # currency means such a payload is either correct (base voucher) or
        # cleanly rejected as ``original_amount_required`` (foreign voucher).
        current_currency = expense.original_currency or expense.currency
        base_amount, fx = _resolve_expense_fx(
            expense.hotel,
            amount=fields.get("amount"),
            currency=fields.get("currency", current_currency),
            original_amount=fields.get("original_amount"),
            exchange_rate=fields.get("exchange_rate"),
            rate_basis=fields.get("rate_basis", ""),
            user=user,
        )
        expense.amount = base_amount
        expense.currency = _hotel_currency(expense.hotel).upper()
        for k, v in fx.items():
            setattr(expense, k, v)
        saved_money_fields = [
            "amount", "currency", "original_currency", "original_amount",
            "exchange_rate", "rate_basis", "rate_captured_at", "rate_entered_by",
        ]

    after = _expense_snapshot(expense)
    changed = {
        f: (before[f], after[f]) for f in _EXPENSE_DIFF_FIELDS if before[f] != after[f]
    }
    if not changed:
        # Nothing actually changed — no write, no activity (owner rule). Drop the
        # in-memory re-derivation (e.g. a fresh ``rate_captured_at``) so the
        # caller never sees a value that was not persisted.
        expense.refresh_from_db()
        return expense
    expense.updated_by = _actor(user)
    update_fields = sorted(
        ({"description", "notes", "method", "expense_type"} & set(fields))
        | set(saved_money_fields)
        | {"updated_by", "updated_at"}
    )
    expense.save(update_fields=update_fields)
    diff = " · ".join(f"{f}: '{o}' → '{n}'" for f, (o, n) in changed.items())
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
            expense_type=expense.expense_type,
            description=f"Reversal ({expense.expense_number}): {reason}",
            amount=-expense.amount,
            currency=expense.currency,
            # Mirror the original's FX snapshot (the counter-voucher offsets the
            # same base amount; original_amount is negated for symmetry).
            original_currency=expense.original_currency,
            original_amount=(
                -expense.original_amount if expense.original_amount is not None else None
            ),
            exchange_rate=expense.exchange_rate,
            rate_basis=expense.rate_basis,
            rate_captured_at=expense.rate_captured_at,
            rate_entered_by=expense.rate_entered_by,
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


# --- Expense attachment (ONE optional private receipt) ----------------------


def _delete_stored_file_after_commit(storage, name) -> None:
    """Physically remove a replaced/removed attachment ONLY after the enclosing
    transaction COMMITS.

    A filesystem delete cannot be rolled back: doing it inline would destroy the
    receipt while a later failure rolled the row back to still reference it —
    a dangling pointer AND a lost financial document. Best-effort on failure.
    """
    if not name:
        return

    def _remove():
        try:
            storage.delete(name)
        except (OSError, ValueError):  # pragma: no cover - best-effort cleanup
            pass

    transaction.on_commit(_remove)


@transaction.atomic
def set_expense_attachment(expense, file, *, user=None) -> Expense:
    """Attach or REPLACE the single receipt scan — only on a posted voucher
    inside its own open business date (locked post-close). A replaced file is
    deleted first so nothing orphans. The file must already be validated by the
    caller (serializer/endpoint) via ``validate_expense_attachment``."""
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != PostingStatus.POSTED:
        raise InvalidFinanceOperation({"reason": "not_editable", "status": expense.status})
    if expense.reverses_id is not None:
        raise InvalidFinanceOperation({"reason": "cannot_edit_reversal"})
    _require_void_window(expense.hotel, _expense_business_date(expense))
    # Defence in depth: a FileField's ``validators`` run under ``full_clean()``,
    # NOT on ``save()`` — so without this a direct service call would store an
    # unvalidated file. The endpoint validates too; this makes the SERVICE safe
    # on its own.
    from .expense_validators import validate_expense_attachment

    validate_expense_attachment(file)
    old_storage = old_name = None
    if expense.attachment:
        old_storage, old_name = expense.attachment.storage, expense.attachment.name
    expense.attachment = file
    expense.updated_by = _actor(user)
    expense.save(update_fields=["attachment", "updated_by", "updated_at"])
    _delete_stored_file_after_commit(old_storage, old_name)
    _record_event(
        expense.hotel,
        event_type="expense.attachment_set",
        severity="info",
        title=f"Expense {expense.expense_number} attachment updated",
        message=f"{expense.expense_number}",
        user=user,
        obj=expense,
    )
    return expense


@transaction.atomic
def remove_expense_attachment(expense, *, user=None) -> Expense:
    """Remove the receipt scan — only on a posted voucher inside its own open
    business date. Deletes the underlying file (no orphan)."""
    expense = Expense.objects.select_for_update().get(pk=expense.pk)
    if expense.status != PostingStatus.POSTED:
        raise InvalidFinanceOperation({"reason": "not_editable", "status": expense.status})
    if expense.reverses_id is not None:
        raise InvalidFinanceOperation({"reason": "cannot_edit_reversal"})
    _require_void_window(expense.hotel, _expense_business_date(expense))
    if not expense.attachment:
        return expense
    old_storage, old_name = expense.attachment.storage, expense.attachment.name
    expense.attachment = None
    expense.updated_by = _actor(user)
    expense.save(update_fields=["attachment", "updated_by", "updated_at"])
    _delete_stored_file_after_commit(old_storage, old_name)
    _record_event(
        expense.hotel,
        event_type="expense.attachment_removed",
        severity="info",
        title=f"Expense {expense.expense_number} attachment removed",
        message=f"{expense.expense_number}",
        user=user,
        obj=expense,
    )
    return expense


# --- Refundable insurance (STAYS-ARRIVALS-DEPARTURES §35 / owner D2) ---------
# Held SEPARATELY from the folio: never revenue, never on the folio balance. A
# documented deduction posts ONLY the deducted portion to the folio (a payment
# settling the account); a refund returns money to the guest (no folio movement).


def held_insurance_qs(stay):
    """The refundable-insurance rows that gate ``stay``'s checkout (§35/§38).

    A stay is blocked from departure while ANY of these still hold money: the
    insurance taken directly against the stay AND the insurance taken at booking
    against the reservation while the stay was not yet linked (``stay`` NULL).

    This is the SINGLE definition of "insurance that blocks this stay", used by
    BOTH ``CheckOutService.execute`` (the settlement gate that actually raises
    ``InsuranceNotSettled``) and the checkout-dialog folio summary
    (``stays.views._stay_folio_summary``). Keeping one query means the endpoint's
    ``can_check_out`` / ``financial_clearance_complete`` can never say "ready"
    while the service would block on a reservation-level deposit (the earlier
    ``stay=stay``-only endpoint query missed exactly that case).
    """
    from .models import RefundableInsurance

    held_filter = models.Q(stay=stay)
    if stay.reservation_id:
        held_filter |= models.Q(
            reservation_id=stay.reservation_id, stay__isnull=True
        )
    return RefundableInsurance.objects.filter(hotel=stay.hotel).filter(held_filter)


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
    cur = (currency or _hotel_currency(hotel)).upper()
    if cur not in _accepted_currencies(hotel):
        raise InvalidFinanceOperation({"reason": "currency_not_accepted", "currency": cur})
    # Defence in depth: the linked reservation/stay must belong to the same hotel
    # (the view already scopes them, but never trust a cross-hotel link here).
    if reservation is not None and reservation.hotel_id != hotel.id:
        raise InvalidFinanceOperation({"reason": "reservation_hotel_mismatch"})
    if stay is not None and stay.hotel_id != hotel.id:
        raise InvalidFinanceOperation({"reason": "stay_hotel_mismatch"})
    return RefundableInsurance.objects.create(
        hotel=hotel,
        reservation=reservation,
        stay=stay,
        currency=cur,
        amount=amt,
        method=(method or PaymentMethod.CASH),
        reference=reference or "",
        notes=notes or "",
        received_by=_actor(user),
        received_at=timezone.now(),
        created_by=_actor(user),
    )


# Standard, audit-visible reason for the routine return of a deposit at
# departure — the front desk is not asked to re-type a reason for it (owner
# rule §35); a manual out-of-cycle refund may still pass its own reason.
INSURANCE_RETURN_ON_CHECKOUT_REASON = "insurance_return_on_checkout"


@transaction.atomic
def refund_insurance(insurance, *, amount=None, reason="", user=None):
    """Refund held insurance to the guest (§35). The money returns to the guest —
    NOT a folio movement. ``amount`` defaults to the full remaining held amount.
    A blank reason (the normal deposit return at departure) is recorded under a
    standard reason so the movement is always audited without staff friction."""
    from .models import RefundableInsurance

    insurance = RefundableInsurance.objects.select_for_update().get(pk=insurance.pk)
    held = insurance.amount - insurance.deducted_amount - insurance.refunded_amount
    amt = money(amount) if amount is not None else held
    if amt <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if amt > held:
        raise InvalidAmount({"field": "amount", "reason": "exceeds_held"})
    reason = (reason or "").strip() or INSURANCE_RETURN_ON_CHECKOUT_REASON
    insurance.refunded_amount += amt
    _refresh_insurance_status(insurance)
    insurance.settled_by = _actor(user)
    insurance.save()
    _record_event(
        insurance.hotel,
        event_type="insurance.refunded",
        severity="info",
        title=f"Insurance refunded {amt} {insurance.currency}",
        message=reason,
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
    # The deducted portion settles an OUTSTANDING folio charge — it must never
    # exceed what the folio actually owes (else it would create a credit that
    # refund_folio_credit could pay back = double payout), and it is posted in
    # the folio's own currency, so the insurance must match it (no silent 1:1 FX).
    if insurance.currency.upper() != folio.currency.upper():
        raise InvalidFinanceOperation(
            {
                "reason": "insurance_currency_mismatch",
                "insurance_currency": insurance.currency,
                "folio_currency": folio.currency,
            }
        )
    outstanding = folio_balance(folio)["balance"]
    if outstanding <= ZERO:
        raise InvalidFinanceOperation(
            {"reason": "no_outstanding_balance", "balance": str(outstanding)}
        )
    if amt > outstanding:
        raise InvalidFinanceOperation(
            {"reason": "exceeds_folio_balance", "balance": str(outstanding)}
        )
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
    from apps.shifts.services import get_open_shift_for

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
        shift=get_open_shift_for(user, folio.hotel),
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
