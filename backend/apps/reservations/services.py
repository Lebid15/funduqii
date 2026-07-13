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
    ReservationHasActiveStay,
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
    hotel, *, lines, status, user, occupants=None, **fields
) -> Reservation:
    """Create a reservation with its room lines after an availability check.

    ``lines`` is a list of dicts: ``{"room_type": <RoomType>, "quantity": int,
    "adults": int?, "children": int?, "notes": str?}``. ``status`` is ``held``
    or ``confirmed`` (both consume inventory, so both are availability-checked).

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
    reservation, *, lines=None, status=None, user=None, occupants=None, **fields
):
    """Update a reservation, re-checking availability when inventory-affecting.

    Cancelled/expired reservations are terminal for inventory-affecting edits
    (only internal notes may change). Any change to dates or lines on a
    still-blocking reservation re-runs the availability check, excluding this
    reservation from the calculation so it does not conflict with itself.

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

    # Post-check-in guard (final closure): with an in-house stay the STAY is
    # the source of truth — dates and room lines are frozen here; only safe,
    # non-operational fields (notes, requests, contact snapshot) may change.
    # Operational changes travel through the front desk.
    if (lines is not None or _touches_dates(fields)) and has_in_house_stay(
        reservation
    ):
        raise ReservationHasActiveStay(
            {
                "reservation": reservation.id,
                "reason": "dates_and_rooms_frozen_after_check_in",
            }
        )

    check_in = fields.get("check_in_date", reservation.check_in_date)
    check_out = fields.get("check_out_date", reservation.check_out_date)

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
