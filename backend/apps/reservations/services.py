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

from apps.common.exceptions import (
    CancellationReasonRequired,
    InvalidReservationTransition,
)

from .availability import AvailabilityService
from .models import (
    Reservation,
    ReservationRoomLine,
    ReservationStatus,
    ReservationStatusLog,
)

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
def create_reservation(hotel, *, lines, status, user, **fields) -> Reservation:
    """Create a reservation with its room lines after an availability check.

    ``lines`` is a list of dicts: ``{"room_type": <RoomType>, "quantity": int,
    "adults": int?, "children": int?, "notes": str?}``. ``status`` is ``held``
    or ``confirmed`` (both consume inventory, so both are availability-checked).
    """
    check_in = fields["check_in_date"]
    check_out = fields["check_out_date"]

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
def update_reservation(reservation, *, lines=None, status=None, user=None, **fields):
    """Update a reservation, re-checking availability when inventory-affecting.

    Cancelled/expired reservations are terminal for inventory-affecting edits
    (only internal notes may change). Any change to dates or lines on a
    still-blocking reservation re-runs the availability check, excluding this
    reservation from the calculation so it does not conflict with itself.
    """
    if reservation.status in (
        ReservationStatus.CANCELLED,
        ReservationStatus.EXPIRED,
    ) and (lines is not None or _touches_dates(fields)):
        raise InvalidReservationTransition(
            {"detail": "A cancelled or expired reservation cannot be re-booked."}
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
