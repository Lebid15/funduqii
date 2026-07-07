"""DRF serializers for floors, room types and rooms (Phase 5).

Hotel scoping and cross-tenant safety are enforced here: a room may only
reference a floor and room type from the SAME hotel as the request context, and
``code`` / ``number`` uniqueness is checked per hotel.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.common.exceptions import CrossTenantReference

from .models import Floor, Room, RoomStatus, RoomType


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
    """Read representation with resolved floor/type context."""

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_status_changed_by(self, obj):
        return obj.status_changed_by.email if obj.status_changed_by_id else None


class RoomWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["number", "display_name", "floor", "room_type", "is_active"]

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
        return attrs


class RoomStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RoomStatus.choices)
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
