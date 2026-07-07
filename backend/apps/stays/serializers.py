"""DRF serializers for stays / front desk (Phase 7)."""
from __future__ import annotations

from rest_framework import serializers

from .models import Stay, StayGuest, StayStatusLog


class StayGuestReadSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source="guest.full_name", read_only=True)

    class Meta:
        model = StayGuest
        fields = ["id", "guest", "guest_name", "role"]
        read_only_fields = fields


class StaySerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True)
    room_type_name = serializers.CharField(
        source="room.room_type.name", read_only=True
    )
    primary_guest_name = serializers.CharField(
        source="primary_guest.full_name", read_only=True
    )
    reservation_number = serializers.CharField(
        source="reservation.reservation_number", read_only=True, default=None
    )
    nights = serializers.IntegerField(read_only=True)
    guests = StayGuestReadSerializer(many=True, read_only=True)
    checked_in_by = serializers.SerializerMethodField()
    checked_out_by = serializers.SerializerMethodField()

    class Meta:
        model = Stay
        fields = [
            "id",
            "reservation",
            "reservation_number",
            "reservation_line",
            "room",
            "room_number",
            "room_type_name",
            "primary_guest",
            "primary_guest_name",
            "status",
            "planned_check_in_date",
            "planned_check_out_date",
            "actual_check_in_at",
            "actual_check_out_at",
            "nights",
            "check_in_notes",
            "check_out_notes",
            "checkout_reason",
            "checked_in_by",
            "checked_out_by",
            "guests",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_checked_in_by(self, obj):
        return obj.checked_in_by.email if obj.checked_in_by_id else None

    def get_checked_out_by(self, obj):
        return obj.checked_out_by.email if obj.checked_out_by_id else None


class CheckInSerializer(serializers.Serializer):
    reservation = serializers.IntegerField()
    reservation_line = serializers.IntegerField(required=False, allow_null=True)
    room = serializers.IntegerField(required=False, allow_null=True)
    primary_guest = serializers.IntegerField()
    companions = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    check_in_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class CheckOutSerializer(serializers.Serializer):
    check_out_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    checkout_reason = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class StayNotesSerializer(serializers.ModelSerializer):
    """Limited PATCH — internal notes only (never status, room, dates)."""

    class Meta:
        model = Stay
        fields = ["check_in_notes", "check_out_notes"]


class StayStatusLogSerializer(serializers.Serializer):
    previous_status = serializers.CharField()
    new_status = serializers.CharField()
    note = serializers.CharField()
    changed_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_changed_by(self, obj):
        return obj.changed_by.email if obj.changed_by_id else None
