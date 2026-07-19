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
    LostFoundClaimProofType,
    LostFoundItem,
    LostFoundItemStatusLog,
    LostFoundStatus,
    LostReport,
    LostReportStatus,
    LostReportStatusLog,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceRequestStatusLog,
    MaintenanceStatus,
    OperationPriority,
    RoomBlockStatus,
)
# The SENSITIVE lost-&-found categories (money / jewelry / documents) live in
# services and are the single source of truth for "needs stronger proof". The
# services module never imports serializers, so this module-level import forms
# NO circular dependency — reuse it rather than re-declaring the set.
from .services import SENSITIVE_LOST_FOUND_CATEGORIES

# --- Disclosure gates (WP6) ---------------------------------------------------
# Restricted disclosure of sensitive/internal fields, mirroring the guests
# ``to_representation`` precedent (context request + hotel-permission check,
# FAIL-CLOSED when the request/permission is absent). No new permission codes:
# existing RBAC codes gate each field.


def _has_perm(request, code: str) -> bool:
    """Fail-closed hotel-permission check for the serializer disclosure gates.

    A serializer used WITHOUT a request context (or without ``request.user`` /
    ``request.hotel``) is NEVER treated as authorized — the gated field is
    dropped, not shown. Mirrors ``guests.serializers.can_view_sensitive``.
    """
    from apps.rbac.services import has_hotel_permission

    if request is None:
        return False
    user = getattr(request, "user", None)
    hotel = getattr(request, "hotel", None)
    if user is None or hotel is None:
        return False
    return has_hotel_permission(user, hotel, code)


def _can_see_internal_notes(request, section: str) -> bool:
    """Internal notes are an operational back-channel exposed ONLY to a caller
    who can ACT on the record — the section's ``update`` OR ``status_update``
    permission. Fail-closed when the request/permission is absent. Never present
    in any list serializer / card payload (only the detail serializers)."""
    return _has_perm(request, f"{section}.update") or _has_perm(
        request, f"{section}.status_update"
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # WP6 disclosure gate: drop ``internal_notes`` unless the caller can act
        # on the record (housekeeping.update / .status_update). Fail-closed when
        # there is no request context.
        if not _can_see_internal_notes(self.context.get("request"), "housekeeping"):
            data.pop("internal_notes", None)
        return data


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
        # ``description`` (the model's TextField — the card renders a short form
        # client-side) and ``started_at`` (the maintenance start timestamp) let
        # the maintenance CARD show its short description + start/resolve time
        # (owner card spec §11/§14). Both are DIRECT columns on the model, so
        # they add NO per-row query. Neither is disclosure-gated (WP6 gated only
        # ``internal_notes`` — deliberately still absent here); ``resolved_at``
        # is the resolve half of the start/resolve pair already present.
        fields = [
            "id", "request_number", "room", "room_number", "stay", "title",
            "description", "category", "priority", "status",
            "affects_room_availability", "room_block_status", "assigned_to",
            "assigned_to_name", "reported_at", "started_at", "resolved_at",
            "closed_at",
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # WP6 disclosure gate: drop ``internal_notes`` unless the caller can act
        # on the record (maintenance.update / .status_update). Fail-closed when
        # there is no request context.
        if not _can_see_internal_notes(self.context.get("request"), "maintenance"):
            data.pop("internal_notes", None)
        return data


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
    # WP7 handover proof (required by the SERVICE only for sensitive categories).
    # Shape only here: a closed proof-type choice + a SHORT bounded reference.
    # The privacy rules (identity_last4 <= 4, sensitive-category requirement)
    # live in the domain service (``_resolve_claim_proof``).
    claim_proof_type = serializers.ChoiceField(
        choices=LostFoundClaimProofType.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    claim_proof_reference = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )


class LostFoundDisposeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostFoundCloseSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostFoundItemListSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    guest_name = serializers.CharField(source="guest.full_name", read_only=True, default="")
    found_by_name = serializers.CharField(
        source="found_by.full_name", read_only=True, default=""
    )
    # Discriminator for a MERGED found-item + lost-report view on the frontend.
    record_type = serializers.SerializerMethodField()

    class Meta:
        model = LostFoundItem
        # The Lost-&-Found CARD needs the item ``description``, the FINDER
        # (``found_by_name`` from ``found_by.full_name``, like the detail
        # serializer) and the CLAIMANT NAME (``claimed_by_name``) per the owner
        # card spec §11/§14. NONE of these are disclosure-gated: WP6 kept names
        # and gates ONLY the phone (``claimed_by_phone``) + the WP7 proof VALUE
        # (``claim_proof_reference``) — both deliberately still ABSENT from this
        # list. ``description``/``claimed_by_name`` are direct columns;
        # ``found_by`` is select_related in the list view, so NO per-row query.
        fields = [
            "id", "item_number", "title", "description", "category", "status",
            "found_at", "found_location", "room", "room_number", "stay",
            "guest", "guest_name", "found_by_name", "stored_location",
            "claimed_by_name", "returned_at", "record_type",
        ]
        read_only_fields = fields

    def get_record_type(self, obj) -> str:
        return "found_item"


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
            "claimed_by_name", "claimed_by_phone", "claim_proof_type",
            "claim_proof_reference", "claimed_at", "returned_at",
            "disposed_at", "closed_at", "notes", "internal_notes",
            "status_logs", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_status_logs(self, item):
        logs = item.status_logs.select_related("changed_by")[:10]
        return LostFoundStatusLogSerializer(logs, many=True).data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        # WP6 disclosure gate: internal notes only for a caller who can act on
        # the record (lost_found.update / .status_update); fail-closed.
        if not _can_see_internal_notes(request, "lost_found"):
            data.pop("internal_notes", None)
        # WP6 phone gate: ``claimed_by_phone`` is captured during the claim /
        # return flow (both performed under lost_found.status_update), so only a
        # holder of that permission sees it. Fail-closed without a request
        # context. It is already ABSENT from the list serializer / card.
        # WP7 proof-reference gate: ``claim_proof_reference`` is the sensitive
        # ownership-proof VALUE — gated behind the SAME permission as the phone,
        # fail-closed, and never present in any list serializer / card. The
        # ``claim_proof_type`` marker is NOT sensitive and stays visible.
        if not _has_perm(request, "lost_found.status_update"):
            data.pop("claimed_by_phone", None)
            data.pop("claim_proof_reference", None)
        return data


# --- Lost report (LR — the "I lost X" cycle) ---------------------------------


class LostReportStatusLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = LostReportStatusLog
        fields = _status_log_fields()
        read_only_fields = fields


class LostReportCreateSerializer(serializers.Serializer):
    category = serializers.ChoiceField(
        choices=LostFoundCategory.choices,
        required=False,
        default=LostFoundCategory.OTHER,
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")
    distinctive_marks = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    last_seen_location = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    lost_at = serializers.DateTimeField(required=False, allow_null=True)
    # reporter_name is OPTIONAL at the SHAPE layer so the domain service raises
    # the neutral 422 ``claimant_required`` (rather than a bare field-required).
    reporter_name = serializers.CharField(
        max_length=180, required=False, allow_blank=True, default=""
    )
    reporter_phone = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )
    guest = serializers.IntegerField(required=False, allow_null=True)
    stay = serializers.IntegerField(required=False, allow_null=True)
    reservation = serializers.IntegerField(required=False, allow_null=True)
    internal_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class LostReportUpdateSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=LostFoundCategory.choices, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    distinctive_marks = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    last_seen_location = serializers.CharField(
        max_length=160, required=False, allow_blank=True
    )
    lost_at = serializers.DateTimeField(required=False, allow_null=True)
    reporter_name = serializers.CharField(max_length=180, required=False)
    reporter_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    guest = serializers.IntegerField(required=False, allow_null=True)
    stay = serializers.IntegerField(required=False, allow_null=True)
    reservation = serializers.IntegerField(required=False, allow_null=True)
    internal_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class LostReportStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LostReportStatus.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostReportMatchSerializer(serializers.Serializer):
    found_item = serializers.IntegerField()


class LostReportReasonSerializer(serializers.Serializer):
    # Reason is OPTIONAL at the SHAPE layer so the domain service raises the
    # neutral typed error (lost_report_reason_required / cancellation_reason_
    # required) instead of a bare field-required. Used by unmatch / close-unfound
    # / cancel.
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class LostReportHandoverSerializer(serializers.Serializer):
    recipient_name = serializers.CharField(
        max_length=180, required=False, allow_blank=True, default=""
    )
    recipient_phone = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    # WP7 proof (enforced by the SERVICE only for sensitive categories, reusing
    # ``return_lost_found_item``'s controls). Shape only here.
    claim_proof_type = serializers.ChoiceField(
        choices=LostFoundClaimProofType.choices,
        required=False,
        allow_blank=True,
        default="",
    )
    claim_proof_reference = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )


class LostReportListSerializer(serializers.ModelSerializer):
    # Card/list: EXCLUDES ``reporter_phone`` + ``internal_notes`` ENTIRELY
    # (never rendered at all, not merely gated). Only the safe operational
    # context is surfaced.
    guest_name = serializers.CharField(source="guest.full_name", read_only=True, default="")
    reservation_number = serializers.CharField(
        source="reservation.reservation_number", read_only=True, default=""
    )
    room_number = serializers.CharField(source="stay.room.number", read_only=True, default="")
    matched_found_item_summary = serializers.SerializerMethodField()
    # Discriminator for a MERGED found-item + lost-report view on the frontend.
    record_type = serializers.SerializerMethodField()

    class Meta:
        model = LostReport
        fields = [
            "id", "report_number", "description", "category", "status",
            "last_seen_location", "reporter_name", "lost_at",
            "stay", "guest", "guest_name", "reservation", "reservation_number",
            "room_number", "matched_found_item", "matched_found_item_summary",
            "created_at", "updated_at", "matched_at", "returned_at",
            "record_type",
        ]
        read_only_fields = fields

    def get_matched_found_item_summary(self, report) -> dict | None:
        item = report.matched_found_item
        if item is None:
            return None
        # Safe summary only — the found item's own sensitive fields (phone /
        # proof / internal notes / claimant) are NEVER surfaced through a
        # lost-report payload. ``requires_strong_claim_proof`` is a NON-sensitive
        # boolean derived from the (non-sensitive) category so the frontend can
        # signal the stronger handover requirement before the handover call.
        return {
            "item_number": item.item_number,
            "title": item.title,
            "category": item.category,
            "requires_strong_claim_proof": item.category in SENSITIVE_LOST_FOUND_CATEGORIES,
        }

    def get_record_type(self, report) -> str:
        return "lost_report"


class LostReportSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source="guest.full_name", read_only=True, default="")
    reservation_number = serializers.CharField(
        source="reservation.reservation_number", read_only=True, default=""
    )
    room_number = serializers.CharField(source="stay.room.number", read_only=True, default="")
    matched_found_item_summary = serializers.SerializerMethodField()
    status_logs = serializers.SerializerMethodField()

    class Meta:
        model = LostReport
        fields = [
            "id", "report_number", "category", "status", "description",
            "distinctive_marks", "last_seen_location", "lost_at",
            "reporter_name", "reporter_phone", "stay", "guest", "guest_name",
            "reservation", "reservation_number", "room_number",
            "matched_found_item", "matched_found_item_summary", "internal_notes",
            "matched_at", "returned_at", "closed_at", "cancelled_at",
            "cancellation_reason", "unfound_reason", "status_logs",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_matched_found_item_summary(self, report) -> dict | None:
        item = report.matched_found_item
        if item is None:
            return None
        # Safe summary only — no phone / proof / internal notes / claimant. Only
        # the (non-sensitive) category and the derived boolean are exposed.
        return {
            "item_number": item.item_number,
            "title": item.title,
            "category": item.category,
            "requires_strong_claim_proof": item.category in SENSITIVE_LOST_FOUND_CATEGORIES,
        }

    def get_status_logs(self, report):
        logs = report.status_logs.select_related("changed_by")[:10]
        return LostReportStatusLogSerializer(logs, many=True).data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        # Disclosure gates (mirror WP6, fail-closed):
        # * internal_notes — only a caller who can ACT on the record
        #   (lost_found.update OR lost_found.status_update).
        if not _can_see_internal_notes(request, "lost_found"):
            data.pop("internal_notes", None)
        # * reporter_phone — SENSITIVE contact captured for the handover flow
        #   (performed under lost_found.status_update), so only a holder of that
        #   permission sees it. Fail-closed; already ABSENT from the list/card.
        if not _has_perm(request, "lost_found.status_update"):
            data.pop("reporter_phone", None)
        return data
