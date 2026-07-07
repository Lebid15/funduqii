"""Services for rooms (Phase 5).

Room status changes go through one controlled path so every change is validated
(note required for certain statuses) and recorded in ``RoomStatusLog`` — the
lightweight per-room status history (not a general audit log).
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ResourceInUse, StatusNoteRequired

from .models import NOTE_REQUIRED_STATUSES, Room, RoomStatusLog


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
    return room


def ensure_deletable_floor(floor) -> None:
    if floor.rooms.exists():
        raise ResourceInUse({"reason": "floor_has_rooms"})


def ensure_deletable_room_type(room_type) -> None:
    if room_type.rooms.exists():
        raise ResourceInUse({"reason": "room_type_has_rooms"})
