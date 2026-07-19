"""Serializers for housekeeping / maintenance / lost & found (Phase 10).

Write serializers validate SHAPE only; every rule (same-hotel refs, workflow
transitions, room-status safety) lives in the domain services.
"""
from __future__ import annotations

from rest_framework import serializers

from .models import (
    HousekeepingServiceOutcome,
    HousekeepingStatus,
    HousekeepingTask,
    HousekeepingTaskStatusLog,
    HousekeepingTaskType,
    LostFoundCategory,
    LostFoundItem,
    LostFoundItemStatusLog,
    LostFoundStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceRequestStatusLog,
    MaintenanceStatus,
    OperationPriority,
    RoomBlockStatus,
)

# --- Shared -------------------------------------------------------------------


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class AssignSerializer(serializers.Serializer):
    assigned_to = serializers.IntegerField(allow_null=True)


def _status_log_fields():
    return ["id", "previous_status", "new_status", "note", "changed_by_name", "created_at"]


class HousekeepingStatusLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = HousekeepingTaskStatusLog
        fields = _status_log_fields()
        read_only_fields = fields


class MaintenanceStatusLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = MaintenanceRequestStatusLog
        fields = _status_log_fields()
        read_only_fields = fields


class LostFoundStatusLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = LostFoundItemStatusLog
        fields = _status_log_fields()
        read_only_fields = fields


# --- Housekeeping ----------------------------------------------------------------


class HousekeepingCreateSerializer(serializers.Serializer):
    room = serializers.IntegerField()
    stay = serializers.IntegerField(required=False, allow_null=True)
    task_type = serializers.ChoiceField(
        choices=HousekeepingTaskType.choices,
        required=False,
        default=HousekeepingTaskType.DAILY_CLEANING,
    )
    priority = serializers.ChoiceField(
        choices=OperationPriority.choices,
        required=False,
        default=OperationPriority.NORMAL,
    )
    assigned_to = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    internal_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class HousekeepingUpdateSerializer(serializers.Serializer):
    task_type = serializers.ChoiceField(choices=HousekeepingTaskType.choices, required=False)
    priority = serializers.ChoiceField(choices=OperationPriority.choices, required=False)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    internal_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class HousekeepingStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=HousekeepingStatus.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class HousekeepingCompleteSerializer(serializers.Serializer):
    mark_room_available = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    # The terminal service result. Validated against the FOUR outcomes only —
    # `come_back_later` is deliberately NOT a choice here (it is a separate
    # non-terminal action), so sending it as an outcome is rejected 400.
    service_outcome = serializers.ChoiceField(
        choices=HousekeepingServiceOutcome.choices,
        required=False,
        default=HousekeepingServiceOutcome.CLEANED,
    )


class HousekeepingComeBackLaterSerializer(serializers.Serializer):
    # Non-terminal defer event; only an optional note. No outcome, no status.
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class HousekeepingTaskListSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    # Unit context for the cleaning CARD. ``room`` is SET_NULL (a historical
    # task may outlive its room), so every room-sourced field carries a blank
    # default; ``room_type``/``floor`` are PROTECT FKs on ``Room`` so they are
    # always present when the room is. ``floor_number`` is the card's fallback
    # label when ``floor_name`` is blank.
    room_type_name = serializers.CharField(
        source="room.room_type.name", read_only=True, default=""
    )
    floor_name = serializers.CharField(
        source="room.floor.name", read_only=True, default=""
    )
    floor_number = serializers.CharField(
        source="room.floor.number", read_only=True, default=""
    )
    assigned_to_name = serializers.CharField(
        source="assigned_to.full_name", read_only=True, default=""
    )
    # Derived, O(1) from PAGE-level batch maps built once in the list view — never
    # a per-row query (see ``HousekeepingListCreateView.list``). Occupancy stays
    # DERIVED from an in-house ``Stay`` (there is no ``occupied`` room status).
    is_occupied = serializers.SerializerMethodField()
    # Compact HK-only arrival hint: presence + date/time ONLY. It deliberately
    # OMITS the reservation number — a housekeeping-only role must never see the
    # full booking reference; the card just needs to know an arrival is coming
    # to this unit and when.
    upcoming_arrival = serializers.SerializerMethodField()

    class Meta:
        model = HousekeepingTask
        fields = [
            "id", "task_number", "room", "room_number", "room_type_name",
            "floor_name", "floor_number", "stay", "task_type",
            "status", "priority", "assigned_to", "assigned_to_name",
            "requested_at", "started_at", "completed_at", "service_outcome",
            "is_occupied", "upcoming_arrival",
        ]
        read_only_fields = fields

    def get_is_occupied(self, task) -> bool:
        # The map is a set of room_ids with an in-house stay on THIS page's
        # rooms. Absent context (serializer reused elsewhere) => not occupied.
        occupied = self.context.get("occupied_room_ids") or set()
        return task.room_id in occupied

    def get_upcoming_arrival(self, task) -> dict:
        arrivals = self.context.get("upcoming_arrival_map") or {}
        info = arrivals.get(task.room_id)
        if not info:
            return {
                "has_upcoming": False,
                "arrival_date": None,
                "arrival_time": None,
            }
        # ISO strings keep the wire contract stable and free of the reservation
        # number. ``arrival_time`` is optional on the booking (may be null).
        arrival_date = info["arrival_date"]
        arrival_time = info["arrival_time"]
        return {
            "has_upcoming": True,
            "arrival_date": arrival_date.isoformat() if arrival_date else None,
            "arrival_time": arrival_time.isoformat() if arrival_time else None,
        }


class HousekeepingTaskSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    room_status = serializers.CharField(source="room.status", read_only=True, default="")
    assigned_to_name = serializers.CharField(
        source="assigned_to.full_name", read_only=True, default=""
    )
    status_logs = serializers.SerializerMethodField()

    class Meta:
        model = HousekeepingTask
        fields = [
            "id", "task_number", "room", "room_number", "room_status", "stay",
            "task_type", "status", "priority", "assigned_to", "assigned_to_name",
            "requested_at", "started_at", "completed_at", "service_outcome",
            "cancelled_at", "cancellation_reason", "notes", "internal_notes",
            "status_logs", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_status_logs(self, task):
        logs = task.status_logs.select_related("changed_by")[:10]
        return HousekeepingStatusLogSerializer(logs, many=True).data


# --- Maintenance ------------------------------------------------------------------


class MaintenanceCreateSerializer(serializers.Serializer):
    room = serializers.IntegerField(required=False, allow_null=True)
    stay = serializers.IntegerField(required=False, allow_null=True)
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    category = serializers.ChoiceField(
        choices=MaintenanceCategory.choices,
        required=False,
        default=MaintenanceCategory.OTHER,
    )
    priority = serializers.ChoiceField(
        choices=OperationPriority.choices,
        required=False,
        default=OperationPriority.NORMAL,
    )
    affects_room_availability = serializers.BooleanField(required=False, default=False)
    room_block_status = serializers.ChoiceField(
        choices=RoomBlockStatus.choices, required=False, default=RoomBlockStatus.NONE
    )
    assigned_to = serializers.IntegerField(required=False, allow_null=True)
    internal_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )

    def validate(self, data):
        affects = data.get("affects_room_availability", False)
        block = data.get("room_block_status", RoomBlockStatus.NONE)
        if affects and block == RoomBlockStatus.NONE:
            raise serializers.ValidationError(
                {"room_block_status": "Required when the request affects availability."}
            )
        if not affects:
            # A non-affecting request never carries a block status.
            data["room_block_status"] = RoomBlockStatus.NONE
        if affects and not data.get("room"):
            raise serializers.ValidationError(
                {"room": "A room is required when the request affects availability."}
            )
        return data


class MaintenanceUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    category = serializers.ChoiceField(choices=MaintenanceCategory.choices, required=False)
    priority = serializers.ChoiceField(choices=OperationPriority.choices, required=False)
    affects_room_availability = serializers.BooleanField(required=False)
    room_block_status = serializers.ChoiceField(
        choices=RoomBlockStatus.choices, required=False
    )
    internal_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class MaintenanceStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=MaintenanceStatus.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class MaintenanceResolveSerializer(serializers.Serializer):
    resolution_notes = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class MaintenanceCloseSerializer(serializers.Serializer):
    room_next_status = serializers.ChoiceField(
        choices=[("keep", "Keep"), ("dirty", "Dirty"), ("available", "Available")],
        required=False,
        default="keep",
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class MaintenanceRequestListSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    assigned_to_name = serializers.CharField(
        source="assigned_to.full_name", read_only=True, default=""
    )

    class Meta:
        model = MaintenanceRequest
        fields = [
            "id", "request_number", "room", "room_number", "stay", "title",
            "category", "priority", "status", "affects_room_availability",
            "room_block_status", "assigned_to", "assigned_to_name",
            "reported_at", "resolved_at", "closed_at",
        ]
        read_only_fields = fields


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    room_status = serializers.CharField(source="room.status", read_only=True, default="")
    assigned_to_name = serializers.CharField(
        source="assigned_to.full_name", read_only=True, default=""
    )
    status_logs = serializers.SerializerMethodField()

    class Meta:
        model = MaintenanceRequest
        fields = [
            "id", "request_number", "room", "room_number", "room_status", "stay",
            "title", "description", "category", "priority", "status",
            "affects_room_availability", "room_block_status", "assigned_to",
            "assigned_to_name", "reported_at", "started_at", "resolved_at",
            "closed_at", "cancelled_at", "cancellation_reason",
            "resolution_notes", "internal_notes", "status_logs",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_status_logs(self, request_obj):
        logs = request_obj.status_logs.select_related("changed_by")[:10]
        return MaintenanceStatusLogSerializer(logs, many=True).data


# --- Lost & Found -----------------------------------------------------------------


class LostFoundCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    category = serializers.ChoiceField(
        choices=LostFoundCategory.choices,
        required=False,
        default=LostFoundCategory.OTHER,
    )
    status = serializers.ChoiceField(
        choices=[(LostFoundStatus.FOUND, "Found"), (LostFoundStatus.STORED, "Stored")],
        required=False,
        default=LostFoundStatus.FOUND,
    )
    found_at = serializers.DateTimeField(required=False, allow_null=True)
    found_location = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    room = serializers.IntegerField(required=False, allow_null=True)
    stay = serializers.IntegerField(required=False, allow_null=True)
    guest = serializers.IntegerField(required=False, allow_null=True)
    stored_location = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    internal_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class LostFoundUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    category = serializers.ChoiceField(choices=LostFoundCategory.choices, required=False)
    found_location = serializers.CharField(max_length=160, required=False, allow_blank=True)
    room = serializers.IntegerField(required=False, allow_null=True)
    stay = serializers.IntegerField(required=False, allow_null=True)
    guest = serializers.IntegerField(required=False, allow_null=True)
    stored_location = serializers.CharField(max_length=160, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    internal_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class LostFoundStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LostFoundStatus.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostFoundClaimSerializer(serializers.Serializer):
    claimed_by_name = serializers.CharField(
        max_length=180, required=False, allow_blank=True, default=""
    )
    claimed_by_phone = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostFoundDisposeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostFoundCloseSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostFoundItemListSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    guest_name = serializers.CharField(source="guest.full_name", read_only=True, default="")

    class Meta:
        model = LostFoundItem
        fields = [
            "id", "item_number", "title", "category", "status", "found_at",
            "found_location", "room", "room_number", "stay", "guest",
            "guest_name", "stored_location", "returned_at",
        ]
        read_only_fields = fields


class LostFoundItemSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    guest_name = serializers.CharField(source="guest.full_name", read_only=True, default="")
    found_by_name = serializers.CharField(
        source="found_by.full_name", read_only=True, default=""
    )
    status_logs = serializers.SerializerMethodField()

    class Meta:
        model = LostFoundItem
        fields = [
            "id", "item_number", "title", "description", "category", "status",
            "found_at", "found_location", "room", "room_number", "stay",
            "guest", "guest_name", "found_by_name", "stored_location",
            "claimed_by_name", "claimed_by_phone", "claimed_at", "returned_at",
            "disposed_at", "closed_at", "notes", "internal_notes",
            "status_logs", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_status_logs(self, item):
        logs = item.status_logs.select_related("changed_by")[:10]
        return LostFoundStatusLogSerializer(logs, many=True).data
