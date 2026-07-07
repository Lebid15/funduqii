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
* **Room assignment (Phase 6.1)** — a line may optionally pin a *specific* room.
  A room type's consumed inventory over a range is therefore
  ``(distinct specifically-assigned bookable rooms) + (unassigned quantity)``.
  A specific room cannot be assigned to two overlapping blocking reservations
  (back-to-back is fine); an assignment never exceeds the type's capacity.
* **Overbooking is prevented on the backend**, inside a transaction that locks
  the involved room types (and any specifically-requested rooms) before
  re-computing availability.
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
    def bookable_room_ids(hotel, room_type) -> set[int]:
        """IDs of physical rooms of ``room_type`` that can currently be booked."""
        return set(
            Room.objects.filter(
                hotel=hotel,
                room_type=room_type,
                is_active=True,
                floor__is_active=True,
                room_type__is_active=True,
            )
            .exclude(status__in=NON_BOOKABLE_ROOM_STATUSES)
            .values_list("id", flat=True)
        )

    @classmethod
    def bookable_rooms_count(cls, hotel, room_type) -> int:
        """Physical rooms of ``room_type`` that can currently hold a booking."""
        return len(cls.bookable_room_ids(hotel, room_type))

    @staticmethod
    def _blocking_overlapping(hotel, check_in, check_out, *, exclude_reservation_id, now):
        qs = (
            Reservation.objects.filter(hotel=hotel)
            .filter(overlap_q(check_in, check_out))
            .filter(blocking_q(now))
        )
        if exclude_reservation_id is not None:
            qs = qs.exclude(pk=exclude_reservation_id)
        return qs

    @classmethod
    def existing_usage(
        cls,
        hotel,
        room_type,
        check_in,
        check_out,
        *,
        bookable_ids=None,
        exclude_reservation_id=None,
        now=None,
    ) -> tuple[set[int], int]:
        """Return ``(assigned_room_ids, unassigned_quantity)`` for a room type.

        ``assigned_room_ids`` is the set of *specific* bookable rooms already
        pinned by blocking, overlapping lines; ``unassigned_quantity`` is the
        summed quantity of blocking, overlapping lines with no specific room.
        """
        if bookable_ids is None:
            bookable_ids = cls.bookable_room_ids(hotel, room_type)
        blocking = cls._blocking_overlapping(
            hotel, check_in, check_out,
            exclude_reservation_id=exclude_reservation_id, now=now,
        )
        lines = ReservationRoomLine.objects.filter(
            hotel=hotel, room_type=room_type, reservation__in=blocking
        )
        assigned = set(
            lines.filter(room__isnull=False).values_list("room_id", flat=True)
        ) & bookable_ids
        unassigned = (
            lines.filter(room__isnull=True).aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        return assigned, unassigned

    @classmethod
    def reserved_quantity(
        cls,
        hotel,
        room_type,
        check_in,
        check_out,
        *,
        exclude_reservation_id=None,
        now=None,
    ) -> int:
        """Rooms of ``room_type`` already consumed for the given range.

        = distinct specifically-assigned bookable rooms + unassigned quantity,
        over every blocking, overlapping line (optionally excluding one
        reservation, so a self-edit does not conflict with itself).
        """
        assigned, unassigned = cls.existing_usage(
            hotel, room_type, check_in, check_out,
            exclude_reservation_id=exclude_reservation_id, now=now,
        )
        return len(assigned) + unassigned

    @classmethod
    def room_is_assigned_in_range(
        cls, hotel, room, check_in, check_out, *, exclude_reservation_id=None, now=None
    ) -> bool:
        """True if ``room`` is specifically assigned to a blocking, overlapping line."""
        blocking = cls._blocking_overlapping(
            hotel, check_in, check_out,
            exclude_reservation_id=exclude_reservation_id, now=now,
        )
        return ReservationRoomLine.objects.filter(
            hotel=hotel, room=room, reservation__in=blocking
        ).exists()

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
        requested_lines,
        check_in,
        check_out,
        *,
        exclude_reservation_id=None,
    ) -> None:
        """Raise unless every requested line fits (capacity + room assignment).

        MUST be called inside a transaction. Locks the involved room types and
        any specifically-requested rooms (in a stable id order to avoid
        deadlocks) before re-computing availability, so two concurrent bookings
        of the same type/room cannot both pass and overbook the hotel.

        ``requested_lines`` is a list of dicts:
        ``{"room_type_id": int, "quantity": int, "room_id": int|None}``.
        Raises :class:`NoAvailability` on insufficient capacity and
        :class:`RoomAssignmentConflict` on a same-room overlap.
        """
        from apps.common.exceptions import NoAvailability, RoomAssignmentConflict

        now = timezone.now()

        # Serialization points: lock the room types, then any specific rooms,
        # each in a deterministic id order.
        type_ids = sorted({ln["room_type_id"] for ln in requested_lines})
        room_ids = sorted(
            {ln["room_id"] for ln in requested_lines if ln.get("room_id")}
        )
        list(
            RoomType.objects.select_for_update()
            .filter(hotel=hotel, pk__in=type_ids)
            .order_by("pk")
        )
        if room_ids:
            list(
                Room.objects.select_for_update()
                .filter(hotel=hotel, pk__in=room_ids)
                .order_by("pk")
            )

        # Group the request by room type.
        by_type: dict[int, list] = {}
        for ln in requested_lines:
            by_type.setdefault(ln["room_type_id"], []).append(ln)

        types = {rt.id: rt for rt in RoomType.objects.filter(hotel=hotel, pk__in=type_ids)}
        for rt_id, lines in by_type.items():
            rt = types.get(rt_id)
            if rt is None:
                raise NoAvailability({"room_type": rt_id, "reason": "unknown_room_type"})
            bookable = cls.bookable_room_ids(hotel, rt)
            n = len(bookable)
            existing_assigned, existing_unassigned = cls.existing_usage(
                hotel, rt, check_in, check_out,
                bookable_ids=bookable, exclude_reservation_id=exclude_reservation_id,
                now=now,
            )
            existing_reserved = len(existing_assigned) + existing_unassigned

            req_rooms = [ln["room_id"] for ln in lines if ln.get("room_id")]
            req_unassigned = sum(
                ln["quantity"] for ln in lines if not ln.get("room_id")
            )

            # Duplicate specific rooms within the same request are a conflict.
            if len(req_rooms) != len(set(req_rooms)):
                raise RoomAssignmentConflict(
                    {"room_type": rt.id, "reason": "duplicate_room_in_request"}
                )
            for rid in req_rooms:
                if rid not in bookable:
                    raise NoAvailability(
                        {"room_type": rt.id, "room": rid, "reason": "room_not_bookable"}
                    )
                if rid in existing_assigned:
                    raise RoomAssignmentConflict(
                        {"room_type": rt.id, "room": rid, "reason": "room_overlap"}
                    )

            new_demand = len(req_rooms) + req_unassigned
            if existing_reserved + new_demand > n:
                raise NoAvailability(
                    {
                        "room_type": rt.id,
                        "room_type_name": rt.name,
                        "requested": new_demand,
                        "available": max(0, n - existing_reserved),
                        "reason": "insufficient_rooms" if n else "no_bookable_rooms",
                    }
                )
