"""Services for rooms (Phase 5).

Room status changes go through one controlled path so every change is validated
(note required for certain statuses) and recorded in ``RoomStatusLog`` — the
lightweight per-room status history (not a general audit log).
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ResourceInUse, StatusNoteRequired

from .models import NOTE_REQUIRED_STATUSES, Floor, Room, RoomStatusLog


@transaction.atomic
def change_room_status(room: Room, new_status: str, *, note: str, user) -> Room:
    """Move a room to ``new_status``, validating and logging the change."""
    if new_status in NOTE_REQUIRED_STATUSES and not (note or "").strip():
        raise StatusNoteRequired({"status": new_status})

    previous = room.status
    if previous == new_status and (note or "") == room.status_note:
        return room

    actor = user if getattr(user, "is_authenticated", False) else None
    RoomStatusLog.objects.create(
        hotel=room.hotel,
        room=room,
        previous_status=previous,
        new_status=new_status,
        note=note or "",
        changed_by=actor,
    )
    room.status = new_status
    room.status_note = note or ""
    room.status_changed_at = timezone.now()
    room.status_changed_by = actor
    room.save(
        update_fields=[
            "status",
            "status_note",
            "status_changed_at",
            "status_changed_by",
            "updated_at",
        ]
    )
    # Housekeeping final closure: every real status move shows up in the
    # activity feed (lazy import keeps app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        room.hotel,
        event_type="room.status_changed",
        category="room",
        severity="info",
        title=f"Room {room.number}: {previous} → {new_status}",
        message=note or "",
        actor=actor,
        related_object=room,
        related_url="/hotel/rooms",
    )
    return room


def ensure_deletable_floor(floor) -> None:
    if floor.rooms.exists():
        raise ResourceInUse({"reason": "floor_has_rooms"})


def ensure_deletable_room_type(room_type) -> None:
    if room_type.rooms.exists():
        raise ResourceInUse({"reason": "room_type_has_rooms"})


# --- Operational board (owner task) -----------------------------------------
# READ-ONLY aggregation for /hotel/rooms: every room with a COMPUTED display
# status, its current in-house stay and next upcoming reservation, plus hotel
# and per-floor summaries. `occupied` / `reserved` stay derived — they are
# never stored on the room (Phase 5 rule).

# Display priority (owner spec): the manual states win, then occupancy, then
# upcoming reservations, else available.
_ATTENTION_STATUSES = ("dirty", "cleaning", "maintenance", "out_of_service")


def _display_status(room, occupied_ids, reserved_ids) -> str:
    if room.status != "available":
        return room.status
    if room.id in occupied_ids:
        return "occupied"
    if room.id in reserved_ids:
        return "reserved"
    return "available"


def operational_board(hotel) -> dict:
    """Build the full rooms operational-board DTO for one hotel (pure read)."""
    from apps.reservations.models import BLOCKING_STATUSES, ReservationRoomLine
    from apps.shifts.services import get_business_date
    from apps.stays.models import Stay, StayStatus

    today = get_business_date(hotel)

    rooms = list(
        Room.objects.filter(hotel=hotel).select_related("floor", "room_type")
    )

    # Current in-house stay per room (a room holds at most one).
    stays = Stay.objects.filter(
        hotel=hotel, status=StayStatus.IN_HOUSE
    ).select_related("primary_guest", "reservation")
    stay_by_room: dict[int, Stay] = {s.room_id: s for s in stays}

    # Upcoming/active blocking reservations per room, earliest first.
    lines = (
        ReservationRoomLine.objects.filter(
            hotel=hotel,
            room__isnull=False,
            reservation__status__in=BLOCKING_STATUSES,
            reservation__check_out_date__gte=today,
        )
        .select_related("reservation")
        .order_by("reservation__check_in_date", "reservation_id")
    )
    lines_by_room: dict[int, list] = {}
    for line in lines:
        lines_by_room.setdefault(line.room_id, []).append(line)

    occupied_ids = set(stay_by_room)
    reserved_ids = set(lines_by_room)

    def _next_reservation(room_id: int):
        stay = stay_by_room.get(room_id)
        for line in lines_by_room.get(room_id, []):
            res = line.reservation
            # Skip the reservation the current stay came from — it is not
            # an UPCOMING booking for this room.
            if stay is not None and stay.reservation_id == res.id:
                continue
            return {
                "id": res.id,
                "reservation_number": res.reservation_number,
                "guest_name": res.primary_guest_name,
                "status": res.status,
                "check_in_date": str(res.check_in_date),
                "check_out_date": str(res.check_out_date),
            }
        return None

    room_rows = []
    for room in rooms:
        stay = stay_by_room.get(room.id)
        room_rows.append(
            {
                "id": room.id,
                "number": room.number,
                "display_name": room.display_name,
                "floor": room.floor_id,
                "floor_name": room.floor.name,
                "room_type": room.room_type_id,
                "room_type_name": room.room_type.name,
                "room_type_code": room.room_type.code,
                "base_capacity": room.room_type.base_capacity,
                "max_capacity": room.room_type.max_capacity,
                "base_rate": (
                    str(room.room_type.base_rate)
                    if room.room_type.base_rate is not None
                    else None
                ),
                "is_active": room.is_active,
                "operational_status": room.status,
                "display_status": _display_status(room, occupied_ids, reserved_ids),
                "status_note": room.status_note,
                "status_changed_at": (
                    room.status_changed_at.isoformat()
                    if room.status_changed_at
                    else None
                ),
                "current_stay": (
                    {
                        "id": stay.id,
                        "guest_name": stay.primary_guest.full_name,
                        "planned_check_out_date": str(stay.planned_check_out_date),
                        "reservation_id": stay.reservation_id,
                        "reservation_number": (
                            stay.reservation.reservation_number
                            if stay.reservation
                            else None
                        ),
                    }
                    if stay
                    else None
                ),
                "next_reservation": _next_reservation(room.id),
            }
        )

    def _empty_counts() -> dict:
        return {
            "total": 0,
            "available": 0,
            "occupied": 0,
            "reserved": 0,
            "dirty": 0,
            "cleaning": 0,
            "maintenance": 0,
            "out_of_service": 0,
            "attention": 0,
        }

    # Summaries count NON-archived rooms only (archived rooms still appear in
    # `rooms` so the board's "show archived" toggle works).
    summary = _empty_counts()
    floor_counts: dict[int, dict] = {}
    for row in room_rows:
        if row["display_status"] == "archived":
            continue
        bucket = floor_counts.setdefault(row["floor"], _empty_counts())
        for counts in (summary, bucket):
            counts["total"] += 1
            counts[row["display_status"]] += 1
            if row["display_status"] in _ATTENTION_STATUSES:
                counts["attention"] += 1

    floors = []
    for floor in Floor.objects.filter(hotel=hotel).order_by("sort_order", "id"):
        counts = floor_counts.get(floor.id, _empty_counts())
        total = counts["total"]
        floors.append(
            {
                "id": floor.id,
                "name": floor.name,
                "number": floor.number,
                "is_active": floor.is_active,
                **counts,
                "availability_rate": (
                    round(counts["available"] * 100 / total) if total else 0
                ),
            }
        )

    return {"summary": summary, "floors": floors, "rooms": room_rows}
