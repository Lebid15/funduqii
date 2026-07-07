"""The availability engine (Phase 6) — the single source of truth for "can we
book these rooms for these dates?".

All availability logic lives here. Serializers and views never re-implement the
overlap rule or the inventory math — they call ``AvailabilityService``.

Core rules
----------
* **Date overlap** — two stays ``[in, out)`` overlap iff
  ``existing.check_in < requested.check_out AND requested.check_in <
  existing.check_out``. Because a stay is a half-open interval, **back-to-back**
  bookings (one checks out on the same day another checks in) do **not** overlap
  and are always allowed.
* **What consumes inventory** — a reservation blocks rooms only while it is
  ``confirmed``, or ``held`` with a ``hold_expires_at`` still in the future.
  ``cancelled``, ``expired``, and lapsed holds consume nothing (holds are
  expired lazily here — no background job is required for correctness).
* **Physical inventory** comes from Phase 5: rooms that are active, on an active
  floor, of an active room type, and whose manual status is not
  ``maintenance`` / ``out_of_service`` / ``archived``. Transient housekeeping
  states (``dirty`` / ``cleaning``) are still counted as bookable, because a
  future stay is unaffected by today's housekeeping state.
* **Overbooking is prevented on the backend**, inside a transaction that locks
  the involved room types before re-computing availability.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q, Sum
from django.utils import timezone

from apps.rooms.models import Room, RoomStatus, RoomType

from .models import Reservation, ReservationRoomLine, ReservationStatus

# Manual room statuses that remove a physical room from bookable inventory.
NON_BOOKABLE_ROOM_STATUSES = (
    RoomStatus.MAINTENANCE,
    RoomStatus.OUT_OF_SERVICE,
    RoomStatus.ARCHIVED,
)


def overlap_q(check_in, check_out) -> Q:
    """Reservations whose stay overlaps the half-open range ``[check_in, check_out)``."""
    return Q(check_in_date__lt=check_out) & Q(check_out_date__gt=check_in)


def blocking_q(now=None) -> Q:
    """Reservations that currently consume inventory (confirmed or a live hold)."""
    now = now or timezone.now()
    live_hold = Q(status=ReservationStatus.HELD) & (
        Q(hold_expires_at__isnull=True) | Q(hold_expires_at__gt=now)
    )
    return Q(status=ReservationStatus.CONFIRMED) | live_hold


@dataclass(frozen=True)
class TypeAvailability:
    room_type_id: int
    room_type_name: str
    room_type_code: str
    base_capacity: int
    max_capacity: int
    total_rooms: int
    blocked_rooms: int
    reserved_quantity: int
    available_quantity: int
    can_book: bool
    reason: str | None

    def as_dict(self) -> dict:
        return {
            "room_type": self.room_type_id,
            "room_type_name": self.room_type_name,
            "room_type_code": self.room_type_code,
            "base_capacity": self.base_capacity,
            "max_capacity": self.max_capacity,
            "total_rooms": self.total_rooms,
            "blocked_rooms": self.blocked_rooms,
            "reserved_quantity": self.reserved_quantity,
            "available_quantity": self.available_quantity,
            "can_book": self.can_book,
            "reason": self.reason,
        }


class AvailabilityService:
    """Central availability calculations. Stateless — call the classmethods."""

    @staticmethod
    def bookable_rooms_count(hotel, room_type) -> int:
        """Physical rooms of ``room_type`` that can currently hold a booking."""
        return (
            Room.objects.filter(
                hotel=hotel,
                room_type=room_type,
                is_active=True,
                floor__is_active=True,
                room_type__is_active=True,
            )
            .exclude(status__in=NON_BOOKABLE_ROOM_STATUSES)
            .count()
        )

    @staticmethod
    def reserved_quantity(
        hotel,
        room_type,
        check_in,
        check_out,
        *,
        exclude_reservation_id=None,
        now=None,
    ) -> int:
        """Rooms of ``room_type`` already blocked for the given range.

        Sums the quantities of every blocking, overlapping reservation line,
        optionally excluding one reservation (used when re-checking an edit of
        that same reservation so it does not conflict with itself).
        """
        blocking_overlapping = (
            Reservation.objects.filter(hotel=hotel)
            .filter(overlap_q(check_in, check_out))
            .filter(blocking_q(now))
        )
        if exclude_reservation_id is not None:
            blocking_overlapping = blocking_overlapping.exclude(
                pk=exclude_reservation_id
            )
        qs = ReservationRoomLine.objects.filter(
            hotel=hotel,
            room_type=room_type,
            reservation__in=blocking_overlapping,
        )
        return qs.aggregate(total=Sum("quantity"))["total"] or 0

    @classmethod
    def availability_for_type(
        cls,
        hotel,
        room_type,
        check_in,
        check_out,
        *,
        requested_quantity=0,
        exclude_reservation_id=None,
        now=None,
    ) -> TypeAvailability:
        total_rooms = Room.objects.filter(hotel=hotel, room_type=room_type).count()
        bookable = cls.bookable_rooms_count(hotel, room_type)
        blocked_rooms = total_rooms - bookable
        reserved = cls.reserved_quantity(
            hotel,
            room_type,
            check_in,
            check_out,
            exclude_reservation_id=exclude_reservation_id,
            now=now,
        )
        available = max(0, bookable - reserved)
        needed = requested_quantity or 1
        can_book = available >= needed
        reason = None
        if not can_book:
            if bookable == 0:
                reason = "no_bookable_rooms"
            elif available == 0:
                reason = "fully_booked"
            else:
                reason = "insufficient_rooms"
        return TypeAvailability(
            room_type_id=room_type.id,
            room_type_name=room_type.name,
            room_type_code=room_type.code,
            base_capacity=room_type.base_capacity,
            max_capacity=room_type.max_capacity,
            total_rooms=total_rooms,
            blocked_rooms=blocked_rooms,
            reserved_quantity=reserved,
            available_quantity=available,
            can_book=can_book,
            reason=reason,
        )

    @classmethod
    def check_availability(
        cls,
        hotel,
        check_in,
        check_out,
        *,
        room_type=None,
        exclude_reservation_id=None,
        now=None,
    ) -> list[TypeAvailability]:
        """Availability across one or all of the hotel's room types."""
        types = RoomType.objects.filter(hotel=hotel)
        if room_type is not None:
            types = types.filter(pk=room_type.pk)
        return [
            cls.availability_for_type(
                hotel,
                rt,
                check_in,
                check_out,
                exclude_reservation_id=exclude_reservation_id,
                now=now,
            )
            for rt in types
        ]

    @classmethod
    def ensure_can_book(
        cls,
        hotel,
        requested,
        check_in,
        check_out,
        *,
        exclude_reservation_id=None,
    ) -> None:
        """Raise :class:`NoAvailability` unless every requested line fits.

        MUST be called inside a transaction. Locks the involved room types (in a
        stable id order to avoid deadlocks) before re-computing availability, so
        two concurrent bookings of the same type cannot both pass this check and
        overbook the hotel.

        ``requested`` maps ``room_type_id -> quantity``.
        """
        from apps.common.exceptions import NoAvailability

        now = timezone.now()
        # Lock the room type rows in a deterministic order (serialization point).
        locked_ids = sorted(requested.keys())
        list(
            RoomType.objects.select_for_update()
            .filter(hotel=hotel, pk__in=locked_ids)
            .order_by("pk")
        )
        for rt in RoomType.objects.filter(hotel=hotel, pk__in=locked_ids):
            qty = requested[rt.id]
            avail = cls.availability_for_type(
                hotel,
                rt,
                check_in,
                check_out,
                requested_quantity=qty,
                exclude_reservation_id=exclude_reservation_id,
                now=now,
            )
            if not avail.can_book:
                raise NoAvailability(
                    {
                        "room_type": rt.id,
                        "room_type_name": rt.name,
                        "requested": qty,
                        "available": avail.available_quantity,
                        "reason": avail.reason,
                    }
                )
