"""DRF serializers for floors, room types and rooms (Phase 5).

Hotel scoping and cross-tenant safety are enforced here: a room may only
reference a floor and room type from the SAME hotel as the request context, and
``code`` / ``number`` uniqueness is checked per hotel.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.common.exceptions import (
    BulkRequestTooLarge,
    CrossTenantReference,
    StatusNoteRequired,
)

from .models import NOTE_REQUIRED_STATUSES, Floor, Room, RoomStatus, RoomType
from .services import MAX_BULK_ROOMS


# --- Per-room feature overrides (Round 2 §6.1) ------------------------------
# Shared normalization + validation for a room's feature deltas, reused by the
# read serializer (RoomSerializer.validate) and the write serializer
# (RoomWriteSerializer.validate — the surface RoomDetailView.update actually
# uses). The effective merge itself lives ONLY on Room.effective_features.


def _clean_feature_list(value, field_name: str) -> list[str]:
    """A feature list is a list of non-empty strings: trim each, drop blanks,
    and dedupe WITHIN the list (order preserved). Anything else is a 400."""
    if not isinstance(value, list):
        raise serializers.ValidationError(
            {field_name: "Must be a list of feature strings."}
        )
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise serializers.ValidationError(
                {field_name: "Every feature must be a string."}
            )
        trimmed = item.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        cleaned.append(trimmed)
    return cleaned


def normalize_room_feature_overrides(
    additions, exclusions
) -> tuple[list[str], list[str]]:
    """Clean + validate a room's PERMANENT ``feature_additions`` /
    ``feature_exclusions`` overrides (§6.1). Returns the cleaned pair or raises
    a field-scoped ``ValidationError``.

    Per the owner's semantic decision, additions and exclusions are PERMANENT
    per-room overrides — they are NOT validated against the room type's current
    amenities. An exclusion MAY be *dormant*: it can name a feature that is not
    currently in the type. A dormant exclusion has no effect right now, is
    PRESERVED (never auto-cleaned or silently dropped), and REACTIVATES
    automatically if that feature later returns to the type.

    Rules enforced here:

    * each list is normalized by :func:`_clean_feature_list` (trim, drop
      blanks, dedupe WITHIN the list, order preserved);
    * a feature MUST NOT appear in BOTH lists (no contradiction).

    The effective merge lives solely on :attr:`Room.effective_features`, which
    ignores a dormant exclusion at read time (it only drops features actually
    present in the live type) and reactivates it if the feature returns.
    """
    additions = _clean_feature_list(additions, "feature_additions")
    exclusions = _clean_feature_list(exclusions, "feature_exclusions")

    exclusion_set = set(exclusions)
    conflicts = [f for f in additions if f in exclusion_set]
    if conflicts:
        raise serializers.ValidationError(
            {
                "feature_additions": (
                    "A feature cannot be both added and excluded: "
                    + ", ".join(conflicts)
                    + "."
                )
            }
        )
    return additions, exclusions


class FloorSerializer(serializers.ModelSerializer):
    room_count = serializers.SerializerMethodField()

    class Meta:
        model = Floor
        fields = [
            "id",
            "name",
            "number",
            "description",
            "sort_order",
            "is_active",
            "room_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "room_count", "created_at", "updated_at"]

    def get_room_count(self, obj):
        return obj.rooms.count()

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("A floor name is required.")
        return value


class RoomTypeSerializer(serializers.ModelSerializer):
    room_count = serializers.SerializerMethodField()

    class Meta:
        model = RoomType
        fields = [
            "id",
            "name",
            "code",
            "description",
            "base_capacity",
            "max_capacity",
            "bed_type",
            "amenities",
            "base_rate",
            "is_active",
            "sort_order",
            # Phase 15 — what the public website shows for this type.
            "public_is_visible",
            "public_name",
            "public_description",
            "public_base_price",
            "public_sort_order",
            "room_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "room_count", "created_at", "updated_at"]

    def get_room_count(self, obj):
        return obj.rooms.count()

    def validate_amenities(self, value):
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise serializers.ValidationError("amenities must be a list of strings.")
        return value

    def validate(self, attrs):
        base = attrs.get(
            "base_capacity",
            getattr(self.instance, "base_capacity", 1),
        )
        mx = attrs.get("max_capacity", getattr(self.instance, "max_capacity", 1))
        if base < 1 or mx < 1:
            raise serializers.ValidationError(
                {"base_capacity": "Capacity must be at least 1."}
            )
        if mx < base:
            raise serializers.ValidationError(
                {"max_capacity": "Max capacity must be ≥ base capacity."}
            )
        # `code` unique within the hotel.
        code = attrs.get("code", getattr(self.instance, "code", None))
        hotel = self.context["request"].hotel
        if code:
            qs = RoomType.objects.filter(hotel=hotel, code=code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"code": "This code is already used in this hotel."}
                )
        return attrs


class RoomSerializer(serializers.ModelSerializer):
    """Detail representation with resolved floor/type context and the §6.1
    per-room feature fields that back the three-section editor (inherited /
    added / excluded) plus the merged effective display.

    Room writes flow through :class:`RoomWriteSerializer` (the serializer
    ``RoomDetailView.update`` instantiates), so ``feature_additions`` /
    ``feature_exclusions`` are validated there too via the same shared helper;
    this serializer keeps the fields writable and validated for completeness.
    """

    floor_name = serializers.CharField(source="floor.name", read_only=True)
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)
    room_type_code = serializers.CharField(source="room_type.code", read_only=True)
    base_capacity = serializers.IntegerField(
        source="room_type.base_capacity", read_only=True
    )
    max_capacity = serializers.IntegerField(
        source="room_type.max_capacity", read_only=True
    )
    status_changed_by = serializers.SerializerMethodField()
    # §6.1 feature contract. `effective_features` = live type defaults −
    # exclusions + additions (the SOLE merge, on the model). `inherited_features`
    # = the room type's raw amenities (what the room would show with no
    # overrides). Reset-to-type = client sends both override lists empty.
    effective_features = serializers.ReadOnlyField()
    inherited_features = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            "id",
            "number",
            "display_name",
            "floor",
            "floor_name",
            "room_type",
            "room_type_name",
            "room_type_code",
            "base_capacity",
            "max_capacity",
            "status",
            "status_note",
            "status_changed_at",
            "status_changed_by",
            "is_active",
            "feature_additions",
            "feature_exclusions",
            "effective_features",
            "inherited_features",
            "created_at",
            "updated_at",
        ]
        # Everything is read-only EXCEPT the two override lists.
        read_only_fields = [
            "id",
            "number",
            "display_name",
            "floor",
            "floor_name",
            "room_type",
            "room_type_name",
            "room_type_code",
            "base_capacity",
            "max_capacity",
            "status",
            "status_note",
            "status_changed_at",
            "status_changed_by",
            "is_active",
            "effective_features",
            "inherited_features",
            "created_at",
            "updated_at",
        ]

    def get_status_changed_by(self, obj):
        return obj.status_changed_by.email if obj.status_changed_by_id else None

    def get_inherited_features(self, obj):
        return list(obj.room_type.amenities or [])

    def validate(self, attrs):
        # Only relevant if this serializer is ever used for a write; the live
        # write path is RoomWriteSerializer. Overrides are PERMANENT per-room
        # deltas (§6.1) — validated for per-list cleaning + no-contradiction
        # only, never against the type's current amenities (dormant exclusions
        # are allowed and preserved).
        if "feature_additions" in attrs or "feature_exclusions" in attrs:
            additions, exclusions = normalize_room_feature_overrides(
                attrs.get(
                    "feature_additions",
                    getattr(self.instance, "feature_additions", []),
                ),
                attrs.get(
                    "feature_exclusions",
                    getattr(self.instance, "feature_exclusions", []),
                ),
            )
            attrs["feature_additions"] = additions
            attrs["feature_exclusions"] = exclusions
        return attrs


class RoomWriteSerializer(serializers.ModelSerializer):
    # Write-only, CREATE-only: the initial operational status of the new room.
    # A room is never created as archived, and maintenance/out_of_service still
    # require a note (same rule as change_room_status). On UPDATE these inputs
    # are dropped — status changes go through the dedicated status endpoint, so
    # an update can never rewrite `status` / `status_note` here.
    initial_status = serializers.ChoiceField(
        choices=RoomStatus.choices,
        required=False,
        default=RoomStatus.AVAILABLE,
        write_only=True,
    )
    status_note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default="", write_only=True
    )
    # §6.1 per-room feature deltas. Editable on UPDATE (PATCH/PUT); on CREATE
    # they are ignored so a new room always starts with empty overrides
    # (mirrors its type) — the three-section editor targets an existing room.
    feature_additions = serializers.JSONField(required=False)
    feature_exclusions = serializers.JSONField(required=False)

    class Meta:
        model = Room
        fields = [
            "number",
            "display_name",
            "floor",
            "room_type",
            "is_active",
            "initial_status",
            "status_note",
            "feature_additions",
            "feature_exclusions",
        ]

    def validate_number(self, value):
        if not value.strip():
            raise serializers.ValidationError("A room number is required.")
        return value

    def validate(self, attrs):
        hotel = self.context["request"].hotel
        floor = attrs.get("floor") or getattr(self.instance, "floor", None)
        room_type = attrs.get("room_type") or getattr(self.instance, "room_type", None)

        # Cross-tenant safety: floor and room type must be this hotel's.
        if floor is not None and floor.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "floor"})
        if room_type is not None and room_type.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "room_type"})

        number = attrs.get("number", getattr(self.instance, "number", None))
        if number:
            qs = Room.objects.filter(hotel=hotel, number=number)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"number": "This room number already exists in this hotel."}
                )

        # Initial-status rules apply on CREATE only.
        if self.instance is None:
            initial_status = attrs.get("initial_status") or RoomStatus.AVAILABLE
            if initial_status == RoomStatus.ARCHIVED:
                raise serializers.ValidationError(
                    {"initial_status": "Rooms cannot be created as archived."}
                )
            if initial_status in NOTE_REQUIRED_STATUSES and not (
                attrs.get("status_note") or ""
            ).strip():
                raise StatusNoteRequired({"status": initial_status})

        # §6.1 feature overrides — PERMANENT per-room deltas, normalized +
        # validated together (whenever either list is submitted): per-list
        # string cleaning + the no-contradiction rule only. Exclusions are NOT
        # checked against the type's current amenities — a dormant exclusion (a
        # feature not currently in the type) is accepted, preserved, and
        # reactivates if the feature returns. A partial PATCH of one list
        # re-checks it against the stored other list.
        if "feature_additions" in attrs or "feature_exclusions" in attrs:
            additions, exclusions = normalize_room_feature_overrides(
                attrs.get(
                    "feature_additions",
                    getattr(self.instance, "feature_additions", []) or [],
                ),
                attrs.get(
                    "feature_exclusions",
                    getattr(self.instance, "feature_exclusions", []) or [],
                ),
            )
            attrs["feature_additions"] = additions
            attrs["feature_exclusions"] = exclusions
        return attrs

    def create(self, validated_data):
        # New rooms always start with empty overrides (§6.1): drop any submitted
        # feature deltas so create stays a mirror-the-type operation. (Single
        # create actually runs through services.create_room, which never reads
        # these keys — this keeps serializer.create() consistent for safety.)
        validated_data.pop("feature_additions", None)
        validated_data.pop("feature_exclusions", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Status changes never flow through the write serializer; drop the
        # create-only inputs so a PUT/PATCH can never wipe `status_note`.
        validated_data.pop("initial_status", None)
        validated_data.pop("status_note", None)
        return super().update(instance, validated_data)


class RoomStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RoomStatus.choices)
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class RoomBulkRowSerializer(serializers.Serializer):
    """One room in a bulk-create request. Structural validation only — tenancy,
    duplicate and quota checks run in :func:`services.bulk_create_rooms`."""

    number = serializers.CharField(max_length=32)
    display_name = serializers.CharField(
        max_length=140, required=False, allow_blank=True, default=""
    )
    floor = serializers.IntegerField()
    room_type = serializers.IntegerField()
    is_active = serializers.BooleanField(required=False, default=True)
    initial_status = serializers.ChoiceField(
        choices=RoomStatus.choices, required=False, default=RoomStatus.AVAILABLE
    )
    status_note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )

    def validate_number(self, value):
        if not value.strip():
            raise serializers.ValidationError("A room number is required.")
        return value


class RoomBulkCreateSerializer(serializers.Serializer):
    rooms = serializers.ListField(child=RoomBulkRowSerializer(), min_length=1)

    def validate_rooms(self, value):
        # Over-max is a stable, typed error (not a generic list ValidationError)
        # so the frontend can distinguish it. `MAX_BULK_ROOMS` has a single
        # source of truth in services.
        if len(value) > MAX_BULK_ROOMS:
            raise BulkRequestTooLarge(
                {"limit": MAX_BULK_ROOMS, "requested": len(value)}
            )
        return value
