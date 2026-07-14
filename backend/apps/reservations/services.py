"""Reservation lifecycle services (Phase 6).

Every state change that can affect inventory (create, update dates/lines,
confirm, hold) runs inside a transaction and re-checks availability through the
central :class:`~apps.reservations.availability.AvailabilityService` so the
backend — never the frontend — is the source of truth against overbooking.

No guest profile, payment, folio, invoice, or check-in/out is created here.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import IntegerField
from django.db.models.functions import Cast, Substr
from django.utils import timezone

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.common.exceptions import (
    CancellationReasonRequired,
    InvalidReservationTransition,
    NoAvailability,
    ReservationHasActiveStay,
    RoomAssignmentConflict,
)

from .availability import AvailabilityService
from .models import (
    Reservation,
    ReservationOccupant,
    ReservationRoomLine,
    ReservationStatus,
    ReservationStatusLog,
)

# Structured snapshot fields on Reservation mapped to their Guest source field.
# Used to freeze a faithful snapshot at booking time from a linked guest.
_PRIMARY_GUEST_SNAPSHOT_MAP = {
    "primary_guest_first_name": "first_name",
    "primary_guest_last_name": "last_name",
    "primary_guest_father_name": "father_name",
    "primary_guest_mother_name": "mother_name",
    "primary_guest_national_id": "national_id",
}

_NUMBER_PREFIX = "R"


def _next_reservation_number(hotel) -> str:
    """Generate the next per-hotel reservation number (e.g. ``R00001``).

    Numbers are unique per hotel (DB-enforced). They are monotonic but need not
    be gapless; a rare race is caught by the unique constraint and retried by
    :func:`create_reservation`.
    """
    last = (
        Reservation.objects.filter(
            hotel=hotel, reservation_number__startswith=_NUMBER_PREFIX
        )
        .annotate(
            seq=Cast(Substr("reservation_number", 2), output_field=IntegerField())
        )
        .order_by("-seq")
        .values_list("seq", flat=True)
        .first()
    )
    nxt = (last or 0) + 1
    return f"{_NUMBER_PREFIX}{nxt:05d}"


def _log_status(reservation, previous, new, *, note="", user=None):
    actor = user if getattr(user, "is_authenticated", False) else None
    ReservationStatusLog.objects.create(
        hotel=reservation.hotel,
        reservation=reservation,
        previous_status=previous or "",
        new_status=new,
        note=note or "",
        changed_by=actor,
    )


@transaction.atomic
def create_reservation(
    hotel, *, lines, status, user, occupants=None, room_assignment_mode=None, **fields
) -> Reservation:
    """Create a reservation with its room lines after an availability check.

    ``lines`` is a list of dicts: ``{"room_type": <RoomType>, "quantity": int,
    "adults": int?, "children": int?, "notes": str?, "floor": <Floor|None>}``.
    ``status`` is ``held`` or ``confirmed`` (both consume inventory, so both are
    availability-checked).

    ``room_assignment_mode`` (RESERVATIONS-AUTO-ROOM) is REQUEST-ONLY (never
    persisted) and optional:

    * ``None`` (absent) — LEGACY behaviour, unchanged: each line keeps the room
      the caller provided (or ``None``). No automatic assignment happens.
    * ``"automatic"`` — the client CANNOT pin a room; the backend
      deterministically assigns a specific room to every ``quantity == 1`` line
      inside this transaction (after ``ensure_can_book`` has locked the type). If
      no room fits a line, the whole create fails with ``no_room_available`` — no
      partial reservation, never a room of the wrong floor/type.
    * ``"manual"`` — every line must pin a specific room; the room is validated
      (hotel + type + floor + bookable + available) and a same-room overlap
      raises ``room_assignment_conflict`` (the backend never silently swaps).

    ``occupants`` (RESERVATIONS-FORM-REWORK) is an OPTIONAL list of adult
    companions ``{"guest": <Guest|None>, "first_name": str, ..., "relationship":
    str}``; children remain a count on ``fields['children']``. Passing
    ``primary_guest`` (a ``Guest``) in ``fields`` links the reservation to the
    central directory and freezes a faithful structured snapshot from it. The
    call stays backward compatible: callers that pass neither still work.
    """
    check_in = fields["check_in_date"]
    check_out = fields["check_out_date"]

    # Guests final closure: a guest blocked in THIS hotel gets no new
    # bookings. Reservations hold snapshots (no guest FK), so the guard
    # matches by exact document/phone — a fresh Guest row for the same
    # person cannot sidestep the block. Applies to every flow that creates
    # a reservation (console, wizard, instant, public site).
    from apps.common.exceptions import GuestBlocked
    from apps.guests.services import find_blocked_guest_matching

    blocked = find_blocked_guest_matching(
        hotel,
        phone=fields.get("primary_guest_phone", ""),
        document_number=fields.get("primary_guest_document_number", ""),
    )
    if blocked is not None:
        raise GuestBlocked({"guest": blocked.id})

    # Backend-authoritative capacity: total persons (1 primary + adult
    # companions + children) must fit the selected rooms' max_capacity.
    _enforce_capacity(lines, fields, occupants)

    # RESERVATIONS-AUTO-ROOM: manual mode requires each line to pin a specific
    # room (validated here, before locks) — a same-room overlap is caught by
    # ``ensure_can_book`` below. Automatic assignment happens after the locks.
    if room_assignment_mode == "manual":
        _validate_manual_assignment(lines)

    # DI-F4: when named companions are supplied, store ``adults`` authoritatively
    # as 1 primary + the companions so the persisted counter can never diverge
    # from the capacity that was actually enforced (a client cannot pass a
    # capacity-2 check while storing adults=5). No companions => legacy count.
    if occupants:
        fields["adults"] = 1 + len(occupants)

    # Freeze the structured snapshot from the linked guest (create only).
    _apply_primary_guest_snapshot(fields)

    if status in (ReservationStatus.HELD, ReservationStatus.CONFIRMED):
        AvailabilityService.ensure_can_book(
            hotel, _book_payload(lines), check_in, check_out
        )

    actor = user if getattr(user, "is_authenticated", False) else None
    # Retry on the (rare) reservation-number race.
    for _ in range(5):
        number = _next_reservation_number(hotel)
        try:
            with transaction.atomic():
                reservation = Reservation.objects.create(
                    hotel=hotel,
                    reservation_number=number,
                    status=status,
                    created_by=actor,
                    updated_by=actor,
                    **fields,
                )
                break
        except IntegrityError:
            continue
    else:  # pragma: no cover - only if 5 consecutive collisions
        raise IntegrityError("Could not allocate a reservation number.")

    # RESERVATIONS-AUTO-ROOM: automatic assignment runs under the type locks
    # ``ensure_can_book`` already acquired, so a concurrent booking cannot pick
    # the same room. On no match the whole transaction rolls back (no partial
    # reservation). Absent/manual mode leaves ``line["room"]`` untouched.
    if room_assignment_mode == "automatic":
        _assign_rooms_automatically(
            hotel,
            lines,
            check_in,
            check_out,
            total_persons=_total_persons_create(fields, occupants),
        )

    for line in lines:
        ReservationRoomLine.objects.create(
            hotel=hotel,
            reservation=reservation,
            room_type=line["room_type"],
            room=line.get("room"),
            quantity=line["quantity"],
            adults=line.get("adults"),
            children=line.get("children"),
            notes=line.get("notes", ""),
        )
    _create_occupants(hotel, reservation, occupants)
    _log_status(reservation, "", status, note="created", user=user)
    # Phase 14: activity + permission-matched notifications (lazy import to
    # keep app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="reservation.created",
        category="reservation",
        severity="success",
        title=f"Reservation {reservation.reservation_number} created",
        message=f"{reservation.primary_guest_name} · {check_in} → {check_out}",
        actor=user,
        related_object=reservation,
        related_url="/hotel/reservations",
    )
    return reservation


@transaction.atomic
def update_reservation(
    reservation,
    *,
    lines=None,
    status=None,
    user=None,
    occupants=None,
    room_assignment_mode=None,
    **fields,
):
    """Update a reservation, re-checking availability when inventory-affecting.

    Cancelled/expired reservations are terminal for inventory-affecting edits
    (only internal notes may change). Any change to dates or lines on a
    still-blocking reservation re-runs the availability check, excluding this
    reservation from the calculation so it does not conflict with itself.

    ``room_assignment_mode`` (RESERVATIONS-AUTO-ROOM §7) never auto-reassigns on
    a plain open/edit: rooms only change when the request explicitly REPLACES the
    lines (``lines is not None``) together with a mode. ``"automatic"`` picks
    fresh rooms for the new lines (client rooms discarded); ``"manual"`` requires
    and validates a pinned room per line; absent → legacy (the provided/``None``
    room is kept). The in-house / started-stay freeze still forbids any
    date/room change once a stay exists (guard below).

    ``occupants`` (RESERVATIONS-FORM-REWORK), when not ``None``, REPLACES the
    reservation's adult companions. Capacity is re-enforced whenever the room
    lines, occupants, or adult/child counts change. The structured snapshot is
    NOT rewritten on update — it stays frozen unless the caller sends the
    snapshot fields explicitly.
    """
    if reservation.status in (
        ReservationStatus.CANCELLED,
        ReservationStatus.EXPIRED,
    ) and (lines is not None or _touches_dates(fields)):
        raise InvalidReservationTransition(
            {"detail": "A cancelled or expired reservation cannot be re-booked."}
        )

    # Post-check-in guard (final closure + Finance-F1): once the reservation
    # has ANY stay — in-house OR already checked-out — the STAY is the source of
    # truth, so dates and room lines are frozen here; only safe, non-operational
    # fields (notes, requests, contact snapshot) may change. A checked-out
    # reservation is still CONFIRMED, so this broadened check (``has_any_stay``,
    # not ``has_in_house_stay``) also blocks re-shaping the inventory of a booking
    # whose guest has already departed. Operational changes travel through the
    # front desk (§33/§42 — the backend is the authoritative guard).
    if (lines is not None or _touches_dates(fields)) and has_any_stay(reservation):
        raise ReservationHasActiveStay(
            {
                "reservation": reservation.id,
                "reason": "dates_and_rooms_frozen_after_check_in",
            }
        )

    check_in = fields.get("check_in_date", reservation.check_in_date)
    check_out = fields.get("check_out_date", reservation.check_out_date)

    # RESERVATIONS-AUTO-ROOM §7: manual replacement validates each new line's
    # pinned room before the locks; automatic is assigned after the availability
    # check (below). Only fires when the lines are actually being replaced.
    if lines is not None and room_assignment_mode == "manual":
        _validate_manual_assignment(lines)

    effective_lines = lines
    inventory_affecting = (
        reservation.status in (ReservationStatus.HELD, ReservationStatus.CONFIRMED)
        and (lines is not None or _touches_dates(fields))
    )
    if inventory_affecting:
        payload = (
            _book_payload(effective_lines)
            if effective_lines is not None
            else _db_lines(reservation)
        )
        AvailabilityService.ensure_can_book(
            reservation.hotel,
            payload,
            check_in,
            check_out,
            exclude_reservation_id=reservation.id,
        )

    # Backend-authoritative capacity, occupant-aware. Only re-checked when a
    # relevant input (lines / occupants / adult or child counts) changes.
    if (
        lines is not None
        or occupants is not None
        or "adults" in fields
        or "children" in fields
    ):
        _enforce_capacity_update(reservation, lines, occupants, fields)

    # DI-F4: whenever the companion list is (re)provided — including an empty
    # list that clears companions — store ``adults`` authoritatively as 1
    # primary + the companions, matching the occupant-derived capacity that was
    # just enforced. When occupants is None the list is untouched, so the
    # existing ``adults`` behavior is preserved (backward compatible).
    if occupants is not None:
        fields["adults"] = 1 + len(occupants)

    for attr, value in fields.items():
        setattr(reservation, attr, value)
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.updated_by = user
    reservation.save()

    if lines is not None:
        reservation.lines.all().delete()
        # RESERVATIONS-AUTO-ROOM §7: assign the replacement lines under the locks
        # ``ensure_can_book`` acquired above; excluding this reservation so it
        # never conflicts with its own (now deleted) lines.
        if room_assignment_mode == "automatic":
            _assign_rooms_automatically(
                reservation.hotel,
                lines,
                check_in,
                check_out,
                total_persons=_total_persons_update(reservation, occupants, fields),
                exclude_reservation_id=reservation.id,
            )
        for line in lines:
            ReservationRoomLine.objects.create(
                hotel=reservation.hotel,
                reservation=reservation,
                room_type=line["room_type"],
                room=line.get("room"),
                quantity=line["quantity"],
                adults=line.get("adults"),
                children=line.get("children"),
                notes=line.get("notes", ""),
            )
    if occupants is not None:
        reservation.occupants.all().delete()
        _create_occupants(reservation.hotel, reservation, occupants)
    return reservation


@transaction.atomic
def confirm_reservation(reservation, *, user=None) -> Reservation:
    """Confirm a held reservation, re-checking availability first."""
    if reservation.status == ReservationStatus.CONFIRMED:
        return reservation
    if reservation.status not in (ReservationStatus.HELD,):
        raise InvalidReservationTransition(
            {"detail": "Only a held reservation can be confirmed."}
        )
    AvailabilityService.ensure_can_book(
        reservation.hotel,
        _db_lines(reservation),
        reservation.check_in_date,
        reservation.check_out_date,
        exclude_reservation_id=reservation.id,
    )
    previous = reservation.status
    reservation.status = ReservationStatus.CONFIRMED
    reservation.hold_expires_at = None
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.updated_by = user
    reservation.save(update_fields=["status", "hold_expires_at", "updated_by", "updated_at"])
    _log_status(reservation, previous, reservation.status, note="confirmed", user=user)
    return reservation


@transaction.atomic
def hold_reservation(reservation, *, hold_expires_at, user=None) -> Reservation:
    """Place or refresh a temporary hold, re-checking availability first.

    Only a held reservation can be (re)held; this refreshes its expiry, which is
    meaningful when the hold has lapsed and its inventory must be re-acquired.
    """
    from django.utils.dateparse import parse_datetime

    if reservation.status != ReservationStatus.HELD:
        raise InvalidReservationTransition(
            {"detail": "Only a held reservation can be re-held."}
        )
    if hold_expires_at is None:
        raise InvalidReservationTransition(
            {"detail": "A hold expiry time is required."}
        )
    if isinstance(hold_expires_at, str):
        parsed = parse_datetime(hold_expires_at)
        if parsed is None:
            raise InvalidReservationTransition(
                {"detail": "Invalid hold expiry time."}
            )
        hold_expires_at = parsed

    AvailabilityService.ensure_can_book(
        reservation.hotel,
        _db_lines(reservation),
        reservation.check_in_date,
        reservation.check_out_date,
        exclude_reservation_id=reservation.id,
    )
    reservation.hold_expires_at = hold_expires_at
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.updated_by = user
    reservation.save(update_fields=["hold_expires_at", "updated_by", "updated_at"])
    _log_status(
        reservation, reservation.status, reservation.status, note="hold refreshed", user=user
    )
    return reservation


@transaction.atomic
def cancel_reservation(reservation, *, reason, user=None) -> Reservation:
    """Cancel a reservation (soft — never a hard delete). Requires a reason."""
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    if reservation.status == ReservationStatus.CANCELLED:
        return reservation
    if reservation.status == ReservationStatus.EXPIRED:
        raise InvalidReservationTransition(
            {"detail": "An expired reservation cannot be cancelled."}
        )
    # Post-check-in guard (final closure): a reservation whose guest is
    # in-house cannot be cancelled — check the guest out from the front desk.
    if has_in_house_stay(reservation):
        raise ReservationHasActiveStay(
            {"reservation": reservation.id, "reason": "guest_in_house"}
        )
    previous = reservation.status
    reservation.status = ReservationStatus.CANCELLED
    reservation.cancellation_reason = reason.strip()
    reservation.cancelled_at = timezone.now()
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.cancelled_by = user
        reservation.updated_by = user
    reservation.save()
    _log_status(reservation, previous, reservation.status, note=reason.strip(), user=user)
    from apps.notifications.services import record_activity

    record_activity(
        reservation.hotel,
        event_type="reservation.cancelled",
        category="reservation",
        severity="warning",
        title=f"Reservation {reservation.reservation_number} cancelled",
        message=reason.strip(),
        actor=user,
        related_object=reservation,
        related_url="/hotel/reservations",
    )
    return reservation


def _book_payload(lines) -> list[dict]:
    """Normalize lines into ``ensure_can_book`` input dicts.

    Accepts serializer lines (``room_type``/``room`` model instances) or DB-shaped
    lines (``room_type_id``/``room_id``).
    """
    payload = []
    for line in lines:
        rt = line.get("room_type")
        rt_id = rt.id if hasattr(rt, "id") else line.get("room_type_id")
        room = line.get("room")
        if room is not None and hasattr(room, "id"):
            room_id = room.id
        elif room is not None:
            room_id = room
        else:
            room_id = line.get("room_id")
        payload.append(
            {
                "room_type_id": int(rt_id),
                "quantity": int(line["quantity"]),
                "room_id": room_id,
            }
        )
    return payload


def _db_lines(reservation) -> list[dict]:
    """DB-shaped line dicts for a reservation (no extra queries)."""
    return [
        {"room_type_id": ln.room_type_id, "quantity": ln.quantity, "room_id": ln.room_id}
        for ln in reservation.lines.all()
    ]


def _touches_dates(fields) -> bool:
    return "check_in_date" in fields or "check_out_date" in fields


# --- RESERVATIONS-AUTO-ROOM: automatic / manual room assignment --------------


def _total_persons_create(fields, occupants) -> int:
    """Total persons for a create (mirrors ``_enforce_capacity``): 1 primary +
    named adult companions + children when companions are supplied, else the
    legacy ``adults + children`` counts."""
    children = int(fields.get("children") or 0)
    if occupants:
        return 1 + len(occupants) + children
    return int(fields.get("adults") or 1) + children


def _total_persons_update(reservation, occupants, fields) -> int:
    """Total persons for an update (mirrors ``_enforce_capacity_update``)."""
    children = int(fields.get("children", reservation.children) or 0)
    if occupants is not None:
        return 1 + len(occupants) + children
    existing = reservation.occupants.count()
    if existing:
        return 1 + existing + children
    return int(fields.get("adults", reservation.adults) or 1) + children


def _validate_manual_assignment(lines) -> None:
    """Validate manual room assignment: every line MUST pin a specific room, and
    a request-pinned floor must match the room's floor.

    The room itself (hotel + type + bookable + quantity 1) is already validated
    by the write serializer; its availability is enforced by ``ensure_can_book``.
    The backend never silently swaps a conflicting room for another one.
    """
    for line in lines:
        room = line.get("room")
        if room is None:
            raise DRFValidationError(
                {"room": "A specific room is required in manual assignment mode."}
            )
        floor = line.get("floor")
        if floor is not None:
            floor_id = floor.pk if hasattr(floor, "pk") else floor
            if getattr(room, "floor_id", None) != floor_id:
                raise RoomAssignmentConflict(
                    {"room": room.id, "reason": "room_floor_mismatch"}
                )


def _assign_rooms_automatically(
    hotel, lines, check_in, check_out, *, total_persons, exclude_reservation_id=None
) -> None:
    """Deterministically assign a specific room to every ``quantity == 1`` line
    (RESERVATIONS-AUTO-ROOM). Mutates ``line["room"]`` in place.

    A client-provided room is ALWAYS discarded first (security: the client must
    not be able to pin a room in automatic mode). ``min_capacity`` is passed only
    for a single-line reservation — where the one room holds everyone — so a
    multi-room reservation (capacity already enforced across all rooms) is never
    wrongly rejected. Rooms picked earlier in the same request are excluded so
    two lines never receive the same room. Raises ``no_room_available`` (a clean
    no-availability error) when a line has no matching room, failing the save.
    """
    used: set[int] = set()
    single_line = len(lines) == 1
    for line in lines:
        line["room"] = None  # never honour a client-pinned room in auto mode
        if int(line["quantity"]) != 1:
            # A specific room cannot be pinned to a multi-room line (one FK);
            # it stays unassigned — ``ensure_can_book`` already guaranteed the
            # unassigned quantity fits.
            continue
        room = AvailabilityService.pick_available_room(
            hotel,
            room_type=line["room_type"],
            check_in=check_in,
            check_out=check_out,
            floor=line.get("floor"),
            min_capacity=total_persons if single_line else None,
            exclude_room_ids=used,
            exclude_reservation_id=exclude_reservation_id,
        )
        if room is None:
            raise NoAvailability(
                {
                    "room_type": line["room_type"].id,
                    "room_type_name": getattr(line["room_type"], "name", None),
                    "reason": "no_room_available",
                }
            )
        line["room"] = room
        used.add(room.id)


# --- RESERVATIONS-FORM-REWORK helpers ---------------------------------------


def _apply_primary_guest_snapshot(fields) -> None:
    """Freeze the structured snapshot from a linked ``primary_guest`` (create).

    Only fills snapshot fields that the caller left empty — an explicitly
    provided snapshot value always wins — so the snapshot is captured faithfully
    once at booking time. Mutates ``fields`` in place. No-op without a guest.
    """
    guest = fields.get("primary_guest")
    if guest is None:
        return
    for snap_field, guest_field in _PRIMARY_GUEST_SNAPSHOT_MAP.items():
        if not fields.get(snap_field):
            fields[snap_field] = getattr(guest, guest_field, "") or ""
    if not fields.get("primary_guest_date_of_birth") and getattr(
        guest, "date_of_birth", None
    ):
        fields["primary_guest_date_of_birth"] = guest.date_of_birth


def _create_occupants(hotel, reservation, occupants) -> None:
    """Create adult-companion rows. Links an existing guest when provided;
    otherwise stores the structured identity inline (no Guest row is forced)."""
    if not occupants:
        return
    for occ in occupants:
        ReservationOccupant.objects.create(
            hotel=hotel,
            reservation=reservation,
            guest=occ.get("guest"),
            first_name=occ.get("first_name", "") or "",
            last_name=occ.get("last_name", "") or "",
            father_name=occ.get("father_name", "") or "",
            mother_name=occ.get("mother_name", "") or "",
            national_id=occ.get("national_id", "") or "",
            nationality=occ.get("nationality", "") or "",
            date_of_birth=occ.get("date_of_birth"),
            relationship=occ.get("relationship", "") or "",
        )


def _capacity_of_lines(lines) -> int:
    """Sum ``quantity * room_type.max_capacity`` over resolved serializer lines."""
    return sum(
        int(line["quantity"]) * int(line["room_type"].max_capacity)
        for line in lines
    )


def _enforce_capacity(lines, fields, occupants) -> None:
    """Raise unless total persons fit the selected rooms (create path).

    Total persons = 1 primary + adult companions + children when companions are
    supplied; otherwise the legacy ``adults + children`` counts. Raises a clean
    validation error (same envelope/style as the serializer capacity check).
    """
    capacity = _capacity_of_lines(lines)
    children = int(fields.get("children") or 0)
    if occupants:
        total_persons = 1 + len(occupants) + children
    else:
        total_persons = int(fields.get("adults") or 1) + children
    _raise_if_over_capacity(total_persons, capacity)


def _enforce_capacity_update(reservation, lines, occupants, fields) -> None:
    """Raise unless total persons fit the selected rooms (update path).

    Uses the effective lines (new ones if provided, else the reservation's
    current lines) and the effective person counts (new occupants if provided,
    else the reservation's current occupants; falling back to ``adults`` only
    when there are no named companions at all).
    """
    if lines is not None:
        capacity = _capacity_of_lines(lines)
    else:
        capacity = sum(
            rl.quantity * rl.room_type.max_capacity
            for rl in reservation.lines.select_related("room_type").all()
        )
    children = int(fields.get("children", reservation.children) or 0)
    if occupants is not None:
        total_persons = 1 + len(occupants) + children
    else:
        existing_occupants = reservation.occupants.count()
        if existing_occupants:
            total_persons = 1 + existing_occupants + children
        else:
            total_persons = int(fields.get("adults", reservation.adults) or 1) + children
    _raise_if_over_capacity(total_persons, capacity)


def _raise_if_over_capacity(total_persons, capacity) -> None:
    if total_persons > capacity:
        raise DRFValidationError(
            {
                "occupants": (
                    "Total persons exceed the maximum capacity of the "
                    "selected rooms."
                )
            }
        )


def has_in_house_stay(reservation) -> bool:
    """True when a stay created from this reservation is currently in-house.

    Post-check-in the STAY is the source of truth (documented decision) —
    operational changes travel through the front desk, never the booking.
    """
    from apps.stays.models import Stay, StayStatus

    return Stay.objects.filter(
        reservation=reservation, status=StayStatus.IN_HOUSE
    ).exists()


def has_any_stay(reservation) -> bool:
    """True when the reservation has ANY related stay — in-house OR already
    checked-out (Finance-F1, §27/§33).

    A pre-arrival concept (a fresh deposit, a date/room/line edit) is only valid
    while the booking has NEVER produced a stay. The moment a stay exists the
    money and inventory live on the stay/folio, so a NEW reservation deposit
    would open an ORPHAN pre-arrival folio (inflating paid / negative remaining)
    and a date/room edit would silently diverge from the stay. This broadens
    ``has_in_house_stay`` to also catch a checked-out booking whose reservation is
    still CONFIRMED and whose stay folio is CLOSED. A single ``exists`` query — no
    prefetch assumption, safe on the un-prefetched view/service paths.
    """
    from apps.stays.models import Stay

    return Stay.objects.filter(reservation=reservation).exists()


def latest_stay(reservation):
    """The most recent Stay derived from this reservation, or ``None``.

    Uses the reverse ``stays`` relation (prefetched by the reservation list/detail
    querysets, so this adds no query there). "Most recent" = highest pk, i.e. the
    last stay row created for the booking — this lets a read serializer expose a
    single ``stay_status`` (in_house / checked_out / cancelled) that distinguishes
    an in-house guest, a departed guest, and a booking that never checked in
    (``None``), which the boolean ``has_in_house_stay`` alone cannot.
    """
    stays = list(reservation.stays.all())
    if not stays:
        return None
    return max(stays, key=lambda s: s.id)


def reservation_financials(reservation, *, hotel=None) -> dict:
    """Derive a reservation's money summary — a READ-ONLY view, never stored.

    Design (RESERVATIONS-FORM-UX-CORRECTION §26/§31/§35, office decision — there
    is NO pricing/tax engine in this repo, so none is invented):

    - ``reservation_total`` = ``Σ money(room_type.base_rate × nights × quantity)``
      over the reservation's room lines. ``base_rate`` is a reference value that
      may be ``NULL``; a line without one is UNPRICED — it contributes nothing and
      flags the whole reservation as not fully priced (``is_priced=False``), so the
      UI can honestly show "not priced" rather than a fabricated total.
    - ``nightly_rate`` = ``Σ money(base_rate × quantity)`` over priced lines.
    - ``paid`` = ``Σ`` POSTED ``Payment.amount`` (already the base/reservation
      currency equivalent — §29) across the reservation's folio(s). Deposits taken
      before check-in AND payments on the reused stay folio are all counted, since
      they hang off the same reservation-linked folio ledger (invariant #1).
    - ``remaining`` = ``money(total − paid)`` — DERIVED, never a stored second
      balance (§31).
    - ``payment_status`` ∈ {unpaid, partial, paid}, derived from paid vs total.

    ``currency`` is the reservation/base currency (the hotel default), matching the
    folio currency. Pass ``hotel`` to avoid an FK hit per row in list rendering.
    All money is :class:`~decimal.Decimal` via ``money()``. Returns a plain dict of
    Decimals/None (+ metadata); serialization to strings is the caller's job.
    """
    from apps.finance.models import PostingStatus
    from apps.finance.services import ZERO, money

    hotel = hotel or reservation.hotel
    settings_obj = getattr(hotel, "settings", None)
    currency = (getattr(settings_obj, "default_currency", "") or "") or "USD"

    nights = reservation.nights
    unpriced = False
    priced_present = False
    nightly = ZERO
    total = ZERO
    for line in reservation.lines.all():
        rate = line.room_type.base_rate
        qty = int(line.quantity or 0)
        if rate is None:
            unpriced = True
            continue
        priced_present = True
        rate = money(rate)
        nightly += rate * qty
        total += rate * qty * nights
    is_priced = priced_present and not unpriced
    nightly = money(nightly) if is_priced else None
    total = money(total) if is_priced else None

    paid = ZERO
    for folio in reservation.folios.all():
        for payment in folio.payments.all():
            if payment.status == PostingStatus.POSTED:
                paid += payment.amount
    paid = money(paid)

    remaining = money(total - paid) if total is not None else None
    if paid <= ZERO:
        payment_status = "unpaid"
    elif total is None:
        # Money received but the total is unknown (unpriced) — honestly partial.
        payment_status = "partial"
    elif paid >= total:
        payment_status = "paid"
    else:
        payment_status = "partial"

    return {
        "currency": currency,
        "nights": nights,
        "nightly_rate": nightly,
        "reservation_total": total,
        "paid": paid,
        "remaining": remaining,
        "payment_status": payment_status,
        "is_priced": is_priced,
    }
