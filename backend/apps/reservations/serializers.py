"""DRF serializers for reservations & availability (Phase 6).

Hotel scoping and cross-tenant safety are enforced here: a reservation line may
only reference an ACTIVE room type from the SAME hotel as the request context.
Dates, quantities and capacity are validated here; overbooking is enforced in
the services/availability layer inside a transaction.
"""
from __future__ import annotations

import re

from django.utils import timezone

from rest_framework import serializers

from apps.common.exceptions import CrossTenantReference
from apps.rooms.models import Room, RoomStatus, RoomType

from .availability import TypeAvailability
from .models import (
    BookingKind,
    ExpectedPaymentMethod,
    Reservation,
    ReservationRoomLine,
    ReservationSource,
    ReservationStatus,
)

_PHONE_RE = re.compile(r"^[0-9+\-\s()]{4,32}$")
_WRITE_STATUSES = (ReservationStatus.HELD, ReservationStatus.CONFIRMED)
# Room statuses that cannot receive a specific assignment (Phase 6.1).
_NON_ASSIGNABLE_ROOM_STATUSES = (
    RoomStatus.MAINTENANCE,
    RoomStatus.OUT_OF_SERVICE,
    RoomStatus.ARCHIVED,
)


class ReservationLineReadSerializer(serializers.ModelSerializer):
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)
    room_type_code = serializers.CharField(source="room_type.code", read_only=True)
    max_capacity = serializers.IntegerField(
        source="room_type.max_capacity", read_only=True
    )
    room_number = serializers.SerializerMethodField()

    class Meta:
        model = ReservationRoomLine
        fields = [
            "id",
            "room_type",
            "room_type_name",
            "room_type_code",
            "max_capacity",
            "room",
            "room_number",
            "quantity",
            "adults",
            "children",
            "notes",
        ]
        read_only_fields = fields

    def get_room_number(self, obj):
        return obj.room.number if obj.room_id else None


class ReservationSerializer(serializers.ModelSerializer):
    """Read representation with nested lines and computed fields."""

    lines = ReservationLineReadSerializer(many=True, read_only=True)
    nights = serializers.IntegerField(read_only=True)
    total_guests = serializers.IntegerField(read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id",
            "reservation_number",
            "status",
            "source",
            "booking_kind",
            "check_in_date",
            "check_out_date",
            "expected_arrival_time",
            "nights",
            "primary_guest_name",
            "primary_guest_phone",
            "primary_guest_email",
            "primary_guest_nationality",
            "primary_guest_document_type",
            "primary_guest_document_number",
            "adults",
            "children",
            "total_guests",
            "notes",
            "special_requests",
            "booking_channel_name",
            "expected_payment_method",
            "no_show_reason",
            "cancellation_reason",
            "cancelled_at",
            "hold_expires_at",
            "created_by",
            "created_at",
            "updated_at",
            "lines",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by_id else None


class ReservationLineWriteSerializer(serializers.Serializer):
    room_type = serializers.IntegerField()
    # Phase 6.1: an optional specific room assignment.
    room = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    adults = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    children = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class ReservationWriteSerializer(serializers.ModelSerializer):
    """Create/update payload. Resolves and validates lines against the hotel."""

    lines = ReservationLineWriteSerializer(many=True, required=False)
    status = serializers.ChoiceField(
        choices=[(s.value, s.label) for s in _WRITE_STATUSES],
        required=False,
        default=ReservationStatus.CONFIRMED,
    )
    source = serializers.ChoiceField(
        choices=ReservationSource.choices,
        required=False,
        default=ReservationSource.DIRECT,
    )
    # Optional on write: when omitted it is derived from the check-in date
    # (today => instant, later => future).
    booking_kind = serializers.ChoiceField(
        choices=BookingKind.choices, required=False
    )
    expected_payment_method = serializers.ChoiceField(
        choices=ExpectedPaymentMethod.choices,
        required=False,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = Reservation
        fields = [
            "status",
            "source",
            "booking_kind",
            "check_in_date",
            "check_out_date",
            "expected_arrival_time",
            "primary_guest_name",
            "primary_guest_phone",
            "primary_guest_email",
            "primary_guest_nationality",
            "primary_guest_document_type",
            "primary_guest_document_number",
            "adults",
            "children",
            "notes",
            "special_requests",
            "booking_channel_name",
            "expected_payment_method",
            "hold_expires_at",
            "lines",
        ]

    # --- field-level ---------------------------------------------------------

    def validate_primary_guest_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("A primary guest name is required.")
        return value.strip()

    def validate_primary_guest_phone(self, value):
        if value and not _PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate_adults(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("At least one adult is required.")
        return value

    # --- object-level --------------------------------------------------------

    def _resolve_lines(self, raw_lines):
        """Turn ``[{room_type: id, room: id?, ...}]`` into validated line dicts.

        Enforces cross-tenant safety, that each room type is active, and — when a
        specific room is assigned (Phase 6.1) — that the room belongs to the same
        hotel and room type, is bookable, and that quantity is 1.
        """
        hotel = self.context["request"].hotel
        resolved = []
        for raw in raw_lines:
            rt = RoomType.objects.filter(pk=raw["room_type"]).first()
            if rt is None:
                raise serializers.ValidationError(
                    {"lines": "A referenced room type does not exist."}
                )
            if rt.hotel_id != hotel.id:
                raise CrossTenantReference({"field": "room_type"})
            if not rt.is_active:
                raise serializers.ValidationError(
                    {"lines": f"Room type '{rt.code}' is not active."}
                )
            room = self._resolve_room(raw.get("room"), rt, raw.get("quantity"), hotel)
            resolved.append(
                {
                    "room_type": rt,
                    "room": room,
                    "quantity": raw["quantity"],
                    "adults": raw.get("adults"),
                    "children": raw.get("children"),
                    "notes": raw.get("notes", ""),
                }
            )
        return resolved

    def _resolve_room(self, room_id, room_type, quantity, hotel):
        """Validate an optional specific room assignment (Phase 6.1)."""
        if not room_id:
            return None
        room = Room.objects.filter(pk=room_id).first()
        if room is None:
            raise serializers.ValidationError({"lines": "The assigned room does not exist."})
        if room.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "room"})
        if room.room_type_id != room_type.id:
            raise serializers.ValidationError(
                {"lines": "The assigned room does not match the room type."}
            )
        if not room.is_active or room.status in _NON_ASSIGNABLE_ROOM_STATUSES:
            raise serializers.ValidationError(
                {"lines": f"Room {room.number} is not assignable."}
            )
        if quantity != 1:
            raise serializers.ValidationError(
                {"lines": "A line with an assigned room must have quantity 1."}
            )
        return room

    def validate(self, attrs):
        creating = self.instance is None
        check_in = attrs.get(
            "check_in_date", getattr(self.instance, "check_in_date", None)
        )
        check_out = attrs.get(
            "check_out_date", getattr(self.instance, "check_out_date", None)
        )
        if check_in and check_out and check_in >= check_out:
            raise serializers.ValidationError(
                {"check_out_date": "Check-out must be after check-in."}
            )

        # Phase 8.1 — the only two booking kinds are instant/future. When the
        # caller does not send one, derive it from the check-in date.
        booking_kind = attrs.get(
            "booking_kind", getattr(self.instance, "booking_kind", "")
        )
        if not booking_kind and check_in:
            booking_kind = (
                BookingKind.INSTANT
                if check_in <= timezone.localdate()
                else BookingKind.FUTURE
            )
            attrs["booking_kind"] = booking_kind
        if (
            booking_kind == BookingKind.INSTANT
            and check_in
            and check_in > timezone.localdate()
        ):
            raise serializers.ValidationError(
                {"booking_kind": "An instant booking must start today."}
            )

        status = attrs.get("status", getattr(self.instance, "status", None))
        if status == ReservationStatus.HELD:
            hold_expires = attrs.get(
                "hold_expires_at", getattr(self.instance, "hold_expires_at", None)
            )
            if hold_expires is None:
                raise serializers.ValidationError(
                    {"hold_expires_at": "A hold expiry time is required for held reservations."}
                )

        raw_lines = attrs.get("lines")
        if creating and not raw_lines:
            raise serializers.ValidationError(
                {"lines": "At least one room line is required."}
            )
        if raw_lines is not None:
            resolved = self._resolve_lines(raw_lines)
            attrs["lines"] = resolved
            self._validate_capacity(attrs, resolved)
        return attrs

    def _validate_capacity(self, attrs, resolved):
        adults = attrs.get("adults", getattr(self.instance, "adults", 1) or 1)
        children = attrs.get("children", getattr(self.instance, "children", 0) or 0)
        total_guests = adults + children
        capacity = sum(
            line["quantity"] * line["room_type"].max_capacity for line in resolved
        )
        if total_guests > capacity:
            raise serializers.ValidationError(
                {
                    "adults": (
                        "Total guests exceed the maximum capacity of the "
                        "selected rooms."
                    )
                }
            )


class AvailabilityQuerySerializer(serializers.Serializer):
    check_in_date = serializers.DateField()
    check_out_date = serializers.DateField()
    room_type = serializers.IntegerField(required=False)
    adults = serializers.IntegerField(min_value=0, required=False)
    children = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs):
        if attrs["check_in_date"] >= attrs["check_out_date"]:
            raise serializers.ValidationError(
                {"check_out_date": "Check-out must be after check-in."}
            )
        return attrs


class TypeAvailabilitySerializer(serializers.Serializer):
    """Serializes a :class:`TypeAvailability` dataclass result."""

    def to_representation(self, instance: TypeAvailability) -> dict:
        return instance.as_dict()


class CancelReservationSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("A cancellation reason is required.")
        return value.strip()


class ReservationStatusLogSerializer(serializers.Serializer):
    previous_status = serializers.CharField()
    new_status = serializers.CharField()
    note = serializers.CharField()
    changed_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_changed_by(self, obj):
        return obj.changed_by.email if obj.changed_by_id else None
