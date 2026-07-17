"""Immediate atomic check-in orchestration (RESERVATIONS-FORM-REWORK, Wave 3).

ONE controlled, all-or-nothing compose that turns a single front-desk action —
"the guest is here now" — into a confirmed instant reservation, an optional
pre-arrival deposit, an in-house stay, and the guests attached to it, all on ONE
money ledger.

Ordering inside a SINGLE ``transaction.atomic`` (the nested service atomics
become savepoints):

  1. resolve/create the primary ``Guest`` when the caller did not link one
     (``CheckInService`` needs a central guest for the primary ``StayGuest``);
  2. ``create_reservation(status=confirmed, booking_kind=instant, ...)`` —
     availability + capacity are enforced there;
  3. optional ``record_reservation_payment`` — opens the reservation's ONE folio
     and posts the deposit payment;
  4. ``CheckInService.execute(...)`` → Stay + primary StayGuest + folio, where
     ``ensure_stay_folio`` REUSES the deposit folio (never a second ledger);
  5. promote the reservation's adult occupants to companion ``StayGuest`` rows;
  6. audit the composed operation.

Any failure at any step rolls the WHOLE thing back — there is never a partial
reservation / stay / folio / payment.
"""
from __future__ import annotations

from django.db import transaction

from apps.common.exceptions import InvalidCheckIn
from apps.reservations.models import BookingKind, ReservationStatus
from apps.reservations.services import create_reservation

from .services import CheckInService, promote_reservation_occupants


def _resolve_existing_primary_guest(hotel, provided_guest, reservation_fields):
    """Return a PRE-EXISTING hotel-scoped ``Guest`` for the primary occupant, or
    ``None`` — WITHOUT creating anything (no side effect, so it is replay-safe).

    Prefers the guest the caller linked; else reuses an existing guest by EXACT
    national ID (matched on the NORMALIZED key the constraint + lookup use).
    """
    if provided_guest is not None:
        return provided_guest
    from apps.guests.models import Guest
    from apps.guests.normalize import normalize_id

    national_id_normalized = normalize_id(
        (reservation_fields.get("primary_guest_national_id") or "").strip()
    )
    if national_id_normalized:
        return Guest.objects.filter(
            hotel=hotel, national_id_normalized=national_id_normalized
        ).first()
    return None


def _create_primary_guest(hotel, reservation_fields, *, user=None):
    """Create a lightweight central ``Guest`` from the reservation snapshot fields.

    A central Guest is REQUIRED because ``CheckInService`` attaches it as the
    primary ``StayGuest`` (a PROTECT FK). Called ONLY on the fresh-booking path
    (after ``create_reservation`` has confirmed this is not an idempotent replay),
    so a retried check-in never leaks a duplicate orphan Guest. The generic
    document fields are not copied to avoid document-uniqueness collisions.
    """
    from apps.guests.models import Guest

    actor = user if getattr(user, "is_authenticated", False) else None
    full_name = (reservation_fields.get("primary_guest_name") or "").strip()
    return Guest.objects.create(
        hotel=hotel,
        full_name=full_name or "Guest",
        first_name=(reservation_fields.get("primary_guest_first_name") or ""),
        last_name=(reservation_fields.get("primary_guest_last_name") or ""),
        father_name=(reservation_fields.get("primary_guest_father_name") or ""),
        mother_name=(reservation_fields.get("primary_guest_mother_name") or ""),
        national_id=(reservation_fields.get("primary_guest_national_id") or "").strip(),
        phone=(reservation_fields.get("primary_guest_phone") or ""),
        email=(reservation_fields.get("primary_guest_email") or ""),
        nationality=(reservation_fields.get("primary_guest_nationality") or "")[:80],
        date_of_birth=reservation_fields.get("primary_guest_date_of_birth"),
        created_by=actor,
        updated_by=actor,
    )


def _ensure_primary_guest(hotel, provided_guest, reservation_fields, *, user=None):
    """Resolve an existing primary Guest or create one. Thin wrapper kept for any
    caller that wants the classic resolve-or-create in one step."""
    return _resolve_existing_primary_guest(
        hotel, provided_guest, reservation_fields
    ) or _create_primary_guest(hotel, reservation_fields, user=user)


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

    # Resolve a PRE-EXISTING primary guest (a provided link or an exact national-id
    # match) up front — this has NO side effect, so it is replay-safe and lets the
    # reservation snapshot be filled from it. A BRAND-NEW guest is deferred to the
    # fresh-booking path below, so an idempotent replay never leaks a duplicate
    # orphan Guest (the side effect that must NOT re-run).
    resolved_guest = _resolve_existing_primary_guest(
        hotel, primary_guest, reservation_fields
    )
    if resolved_guest is not None:
        reservation_fields["primary_guest"] = resolved_guest

    # 1) confirmed, instant reservation — the idempotency gate (availability +
    #    capacity enforced within). On a replay ``create_reservation`` returns the
    #    existing booking and we create NOTHING else.
    reservation = create_reservation(
        hotel,
        lines=lines,
        status=ReservationStatus.CONFIRMED,
        user=user,
        occupants=occupants,
        **reservation_fields,
    )

    # S6 remediation — idempotent replay: if the SAME creation idempotency key was
    # already used, ``create_reservation`` returns the EXISTING reservation. Since
    # this whole orchestration is one ``transaction.atomic``, a committed
    # reservation for the key means its stay + folio (+ deposit) already exist, so
    # we return them WITHOUT re-running any side effect — no duplicate Guest,
    # deposit, stay, folio, payment, or audit. (Inventory limits are NOT relied on.)
    if getattr(reservation, "_idempotent_replay", False):
        from apps.finance.models import Folio, FolioStatus
        from apps.stays.models import Stay

        existing_stay = (
            Stay.objects.filter(hotel=hotel, reservation=reservation)
            .order_by("id")
            .first()
        )
        existing_folio = (
            Folio.objects.filter(
                hotel=hotel, stay=existing_stay, status=FolioStatus.OPEN
            ).first()
            if existing_stay is not None
            else None
        )
        return {
            "reservation": reservation,
            "stay": existing_stay,
            "folio": existing_folio,
        }

    # Fresh booking — NOW materialize the primary Guest (creating one only here, so
    # a retry never leaves an orphan) and link it for the stay's primary StayGuest.
    primary = resolved_guest or _create_primary_guest(
        hotel, reservation_fields, user=user
    )
    if reservation.primary_guest_id is None:
        reservation.primary_guest = primary
        reservation.save(update_fields=["primary_guest"])

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
