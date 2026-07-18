"""Immediate atomic check-in orchestration (RESERVATIONS-FORM-REWORK, Wave 3).

ONE controlled, all-or-nothing compose that turns a single front-desk action —
"the guest is here now" — into a confirmed instant reservation, an optional
pre-arrival deposit, an in-house stay, and the guests attached to it, all on ONE
money ledger.

Ordering inside a SINGLE ``transaction.atomic`` (the nested service atomics
become savepoints):

  1. ``create_reservation(status=confirmed, booking_kind=instant, ...)`` —
     availability + capacity are enforced there, and the primary ``Guest`` is
     resolved / created + LINKED through the ONE central identity service
     (``CheckInService`` then reuses it for the primary ``StayGuest``);
  2. optional ``record_reservation_payment`` — opens the reservation's ONE folio
     and posts the deposit payment;
  3. ``CheckInService.execute(...)`` → Stay + primary StayGuest + folio, where
     ``ensure_stay_folio`` REUSES the deposit folio (never a second ledger);
  4. promote the reservation's adult occupants to companion ``StayGuest`` rows;
  5. audit the composed operation.

Any failure at any step rolls the WHOLE thing back — there is never a partial
reservation / stay / folio / payment.
"""
from __future__ import annotations

from django.db import transaction

from apps.common.exceptions import InvalidCheckIn
from apps.reservations.models import BookingKind, ReservationStatus
from apps.reservations.services import create_reservation

from .services import CheckInService, promote_reservation_occupants


def _immediate_check_in_extra(deposit, room, line_index):
    """The immediate-check-in-SPECIFIC material inputs folded into the creation
    idempotency fingerprint: the deposit (amount/currency/method/FX — the money
    effect), the admit room, and the target line. So a replay with the same key
    but a different deposit / room / line is a materially different request (409),
    not a silent no-op. Money-ish values are coerced to ``Decimal`` (via the same
    ``_decimal_or_none`` the line-rate uses) so the fingerprint is type-independent —
    ``"50.00"``, ``50`` and ``Decimal("50")`` all match — instead of relying on the
    API always sending a ``Decimal``; currency is upper/stripped (``usd``≡``USD``)
    and method stripped. Descriptive-only deposit fields (payer_name / reference /
    notes) are excluded — changing a note is not a materially different request."""
    from apps.reservations.services import _decimal_or_none

    d = deposit or {}
    return {
        "deposit": {
            "amount": _decimal_or_none(d.get("amount")),
            "original_amount": _decimal_or_none(d.get("original_amount")),
            "currency": (d.get("currency") or "").strip().upper(),
            "method": (d.get("method") or "").strip(),
            "exchange_rate": _decimal_or_none(d.get("exchange_rate")),
            "rate_basis": (d.get("rate_basis") or "").strip(),
        }
        if d
        else None,
        "room": getattr(room, "id", room),
        "line_index": line_index,
    }


def _existing_stay_folio(hotel, stay):
    """The stay's folio in WHATEVER state it is now (the immediate-check-in compose
    creates exactly one). Used on an idempotent replay so a retry after check-out
    still returns the real folio (possibly CLOSED) instead of ``None`` — never
    re-opening, creating, or mutating it."""
    from apps.finance.models import Folio

    return Folio.objects.filter(hotel=hotel, stay=stay).order_by("id").first()


def _select_check_in_line(reservation, room, line_index):
    """Pick the reservation line to admit into.

    Explicit ``line_index`` wins; otherwise the first line whose room type
    matches the chosen ``room``; otherwise the first line. ``CheckInService`` then
    re-validates the line/room/quantity as usual.
    """
    lines = list(reservation.lines.order_by("id"))
    if not lines:
        raise InvalidCheckIn({"reason": "reservation_has_no_lines"})
    if line_index is not None:
        if line_index < 0 or line_index >= len(lines):
            raise InvalidCheckIn(
                {"reason": "line_index_out_of_range", "line_index": line_index}
            )
        return lines[line_index]
    if room is not None:
        for line in lines:
            if line.room_type_id == room.room_type_id:
                return line
    return lines[0]


@transaction.atomic
def execute_immediate_check_in(
    hotel,
    *,
    lines,
    primary_guest=None,
    occupants=None,
    room=None,
    line_index=None,
    deposit=None,
    check_in_notes="",
    user=None,
    **reservation_fields,
) -> dict:
    """Compose an instant reservation + optional deposit + in-house stay atomically.

    Args:
        hotel: the tenant.
        lines: resolved reservation line dicts (as ``create_reservation`` expects).
        primary_guest: an optional linked ``Guest`` for the primary occupant.
        occupants: optional resolved adult-companion dicts.
        room: the ``Room`` instance to admit into (or ``None`` when the chosen
            line already pins a room).
        line_index: which reservation line to admit (default: matched/first).
        deposit: optional dict of ``record_reservation_payment`` kwargs
            (``amount``/``method``/``currency``/``original_amount``/
            ``exchange_rate``/``rate_basis``/``payer_name``/``reference``/
            ``notes``). When falsy, no payment is created.
        check_in_notes: free-text stay note.
        user: the acting user (actor + shift resolution).
        **reservation_fields: the remaining ``Reservation`` model fields (dates,
            snapshot, source, ...). ``status`` is forced to confirmed and
            ``booking_kind`` defaults to instant.

    Returns:
        ``{"reservation": Reservation, "stay": Stay, "folio": Folio | None}``.
    """
    reservation_fields.setdefault("booking_kind", BookingKind.INSTANT)
    reservation_fields.pop("status", None)  # status is forced to confirmed
    reservation_fields.pop("hold_expires_at", None)  # not a confirmed-booking field

    # Guests central identity (W3): forward an explicit primary-guest link (when the
    # caller passed one) to create_reservation, which resolves the primary guest
    # through the ONE central identity service (reuse + create + ban + conflict +
    # concurrency IntegrityError-refetch). There is NO pre-resolution here: the
    # resolve/create runs INSIDE create_reservation on its FRESH path only (after its
    # own idempotent-replay guard), so a replay never leaks a duplicate orphan guest.
    if primary_guest is not None:
        reservation_fields["primary_guest"] = primary_guest

    # 1) confirmed, instant reservation — the idempotency gate (availability +
    #    capacity enforced within). The fingerprint scopes this as an
    #    ``immediate_check_in`` operation and folds in the WHOLE material payload
    #    (the deposit + the check-in room/line), so the same key can neither replay
    #    across to a plain reservation create nor return the original when the
    #    deposit/room differs — a materially different request 409s here. On a
    #    genuine replay ``create_reservation`` returns the existing booking and we
    #    create NOTHING else.
    reservation = create_reservation(
        hotel,
        lines=lines,
        status=ReservationStatus.CONFIRMED,
        user=user,
        occupants=occupants,
        operation="immediate_check_in",
        idempotency_extra=_immediate_check_in_extra(deposit, room, line_index),
        **reservation_fields,
    )

    # S6 remediation — idempotent replay: if the SAME creation idempotency key was
    # already used, ``create_reservation`` returns the EXISTING reservation. Since
    # this whole orchestration is one ``transaction.atomic``, a committed
    # reservation for the key means its stay + folio (+ deposit) already exist, so
    # we return them WITHOUT re-running any side effect — no duplicate Guest,
    # deposit, stay, folio, payment, or audit. (Inventory limits are NOT relied on.)
    if getattr(reservation, "_idempotent_replay", False):
        from apps.stays.models import Stay

        existing_stay = (
            Stay.objects.filter(hotel=hotel, reservation=reservation)
            .order_by("id")
            .first()
        )
        # Return the operation's folio in WHATEVER state it is now (OPEN or CLOSED).
        # The original compose created exactly one; we never re-open, create, or
        # mutate it — a replay after check-out still returns the real (closed) folio.
        existing_folio = (
            _existing_stay_folio(hotel, existing_stay)
            if existing_stay is not None
            else None
        )
        return {
            "reservation": reservation,
            "stay": existing_stay,
            "folio": existing_folio,
        }

    # Fresh booking — create_reservation resolved / created + LINKED the central
    # primary guest through the identity service (ban + conflict + concurrency all
    # handled there), so the reservation already carries it. Reuse that exact guest
    # as the stay's primary StayGuest — no second resolution, no duplicate create.
    primary = reservation.primary_guest

    # 2) optional pre-arrival deposit → opens the reservation's ONE folio.
    if deposit:
        from apps.finance.services import record_reservation_payment

        record_reservation_payment(reservation, user=user, **deposit)

    # 3) admit into the room → Stay + primary StayGuest + folio. ensure_stay_folio
    #    REUSES the deposit folio (attaches the stay), so NO second ledger exists.
    line = _select_check_in_line(reservation, room, line_index)
    stay = CheckInService.execute(
        hotel,
        reservation=reservation,
        reservation_line=line,
        room=room,
        primary_guest=primary,
        companions=(),
        check_in_notes=check_in_notes or "",
        user=user,
    )

    # 4) carry named adult companions into the stay.
    promote_reservation_occupants(reservation, stay, user=user)

    # 5) the single open stay folio (the reused deposit folio when there was one).
    from apps.finance.models import Folio, FolioStatus

    folio = Folio.objects.filter(
        hotel=hotel, stay=stay, status=FolioStatus.OPEN
    ).first()

    # 6) audit the composed operation.
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="stay.immediate_check_in",
        category="reservation",
        severity="success",
        title=f"Immediate check-in {reservation.reservation_number}",
        message=f"{primary.full_name} · room {stay.room.number}",
        actor=user,
        related_object=reservation,
        related_url="/hotel/front-desk",
    )
    return {"reservation": reservation, "stay": stay, "folio": folio}
