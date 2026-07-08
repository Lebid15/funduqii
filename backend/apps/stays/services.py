"""Front-desk services (Phase 7): the ONE controlled path for check-in and
check-out. Views never mutate stays directly — they call these services.

Rules enforced here (backend is the source of truth):
- Check-in only from a **confirmed** reservation, into an **available** physical
  room that is not occupied and not held by another reservation.
- Occupancy is derived from an active stay — no manual `room.status = occupied`.
- Check-out is operational only (no money). The room becomes **dirty** on
  check-out (documented decision), via the Phase 5 controlled status service.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    AlreadyCheckedIn,
    CrossTenantReference,
    InvalidCheckIn,
    InvalidCheckOut,
    RoomAssignmentConflict,
    RoomNotReady,
    RoomOccupied,
)
from apps.reservations.availability import AvailabilityService
from apps.reservations.models import ReservationStatus
from apps.rooms.models import Room, RoomStatus
from apps.rooms.services import change_room_status

from .models import Stay, StayGuest, StayGuestRole, StayStatus, StayStatusLog

# A room may only be checked into when it is manually `available`. dirty/cleaning
# (and the hard-blocked maintenance/out_of_service/archived) are refused —
# housekeeping must ready the room first (documented decision; an override could
# be added behind a permission later).
CHECK_IN_READY_STATUS = RoomStatus.AVAILABLE


def _log(stay, previous, new, *, note="", user=None):
    actor = user if getattr(user, "is_authenticated", False) else None
    StayStatusLog.objects.create(
        hotel=stay.hotel,
        stay=stay,
        previous_status=previous or "",
        new_status=new,
        note=note or "",
        changed_by=actor,
    )


class CheckInService:
    """Admit a confirmed reservation into a specific room, creating a Stay."""

    @staticmethod
    @transaction.atomic
    def execute(
        hotel,
        *,
        reservation,
        reservation_line=None,
        room=None,
        primary_guest,
        companions=(),
        check_in_notes="",
        user=None,
    ) -> Stay:
        if reservation.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "reservation"})
        if reservation.status != ReservationStatus.CONFIRMED:
            raise InvalidCheckIn(
                {"reason": "reservation_not_confirmed", "status": reservation.status}
            )

        if reservation_line is not None:
            if reservation_line.reservation_id != reservation.id:
                raise InvalidCheckIn({"reason": "line_not_in_reservation"})
            # A line's pinned room wins; a passed room must match it.
            if reservation_line.room_id:
                if room is not None and room.id != reservation_line.room_id:
                    raise InvalidCheckIn({"reason": "room_does_not_match_line"})
                room = reservation_line.room

        if room is None:
            raise InvalidCheckIn({"reason": "room_required"})

        # Lock the room row for the duration of the check-in.
        room = Room.objects.select_for_update().get(pk=room.pk)
        if room.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "room"})
        if not room.is_active or room.status != CHECK_IN_READY_STATUS:
            raise RoomNotReady({"room": room.id, "status": room.status})
        if Stay.objects.filter(
            hotel=hotel, room=room, status=StayStatus.IN_HOUSE
        ).exists():
            raise RoomOccupied({"room": room.id})
        # Not the same line+room checked in twice.
        if reservation_line is not None and Stay.objects.filter(
            hotel=hotel,
            reservation_line=reservation_line,
            room=room,
            status=StayStatus.IN_HOUSE,
        ).exists():
            raise AlreadyCheckedIn({"line": reservation_line.id, "room": room.id})
        # The room must not be specifically held by a DIFFERENT reservation.
        if AvailabilityService.room_is_assigned_in_range(
            hotel,
            room,
            reservation.check_in_date,
            reservation.check_out_date,
            exclude_reservation_id=reservation.id,
        ):
            raise RoomAssignmentConflict({"room": room.id})

        if primary_guest.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "primary_guest"})
        for companion in companions:
            if companion.hotel_id != hotel.id:
                raise CrossTenantReference({"field": "companion"})

        actor = user if getattr(user, "is_authenticated", False) else None
        stay = Stay.objects.create(
            hotel=hotel,
            reservation=reservation,
            reservation_line=reservation_line,
            room=room,
            primary_guest=primary_guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=reservation.check_in_date,
            planned_check_out_date=reservation.check_out_date,
            actual_check_in_at=timezone.now(),
            checked_in_by=actor,
            check_in_notes=check_in_notes or "",
        )
        StayGuest.objects.create(
            hotel=hotel, stay=stay, guest=primary_guest, role=StayGuestRole.PRIMARY
        )
        seen = {primary_guest.id}
        for companion in companions:
            if companion.id in seen:
                continue
            seen.add(companion.id)
            StayGuest.objects.create(
                hotel=hotel, stay=stay, guest=companion, role=StayGuestRole.COMPANION
            )
        _log(stay, "", StayStatus.IN_HOUSE, note="checked in", user=user)
        # Phase 14: activity + notifications (lazy import).
        from apps.notifications.services import record_activity

        record_activity(
            hotel,
            event_type="stay.checked_in",
            category="stay",
            severity="success",
            title=f"Check-in: room {room.number}",
            message=f"{primary_guest.full_name} · {reservation.reservation_number}",
            actor=user,
            related_object=stay,
            related_url="/hotel/front-desk",
        )
        return stay


class CheckOutService:
    """Close an in-house stay. Operational only — no money, no folio."""

    @staticmethod
    @transaction.atomic
    def execute(stay, *, check_out_notes="", checkout_reason="", user=None) -> Stay:
        if stay.status != StayStatus.IN_HOUSE:
            raise InvalidCheckOut({"status": stay.status})

        actor = user if getattr(user, "is_authenticated", False) else None
        previous = stay.status
        stay.status = StayStatus.CHECKED_OUT
        stay.actual_check_out_at = timezone.now()
        stay.checked_out_by = actor
        stay.check_out_notes = check_out_notes or ""
        stay.checkout_reason = checkout_reason or ""
        stay.save(
            update_fields=[
                "status",
                "actual_check_out_at",
                "checked_out_by",
                "check_out_notes",
                "checkout_reason",
                "updated_at",
            ]
        )
        # Documented decision: a vacated room becomes `dirty` for housekeeping.
        if stay.room.status == RoomStatus.AVAILABLE:
            change_room_status(stay.room, RoomStatus.DIRTY, note="", user=user)
        # Phase 10: auto-raise ONE check-out cleaning task (idempotent; same
        # transaction — it has no external dependencies that could fail).
        # Imported lazily to keep app loading order simple.
        from apps.operations.services import create_checkout_cleaning_task

        create_checkout_cleaning_task(stay, user=user)
        _log(stay, previous, StayStatus.CHECKED_OUT, note="checked out", user=user)
        from apps.notifications.services import record_activity

        record_activity(
            stay.hotel,
            event_type="stay.checked_out",
            category="stay",
            severity="info",
            title=f"Check-out: room {stay.room.number}",
            message=stay.primary_guest.full_name,
            actor=user,
            related_object=stay,
            related_url="/hotel/front-desk",
        )
        return stay
