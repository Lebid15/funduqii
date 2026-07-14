"""DRF serializers for stays / front desk (Phase 7)."""
from __future__ import annotations

from rest_framework import serializers

from apps.reservations.serializers import ReservationWriteSerializer

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
    primary_guest_is_vip = serializers.BooleanField(
        source="primary_guest.is_vip", read_only=True
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
            "primary_guest_is_vip",
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


class StayDateChangeSerializer(serializers.Serializer):
    """Extend / shorten an in-house stay (the services enforce direction)."""

    new_check_out_date = serializers.DateField()
    reason = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class StayMoveRoomSerializer(serializers.Serializer):
    """Room move — the reason is mandatory."""

    room = serializers.IntegerField()
    reason = serializers.CharField(max_length=255, allow_blank=False)


class StayStatusLogSerializer(serializers.Serializer):
    previous_status = serializers.CharField()
    new_status = serializers.CharField()
    note = serializers.CharField()
    changed_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_changed_by(self, obj):
        return obj.changed_by.email if obj.changed_by_id else None


# --- RESERVATIONS-FORM-REWORK: immediate atomic check-in ---------------------


class ImmediateDepositSerializer(serializers.Serializer):
    """Optional pre-arrival deposit for an immediate check-in.

    The base ``amount`` is in the folio/base currency. A foreign-currency deposit
    instead supplies ``original_amount`` + ``exchange_rate`` and the finance
    service DERIVES the base amount (single ledger — invariants #1/#4). The base
    ``amount`` alone drives the derived folio balance; nothing is stored twice.
    """

    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    method = serializers.CharField(max_length=32)
    currency = serializers.CharField(
        max_length=3, required=False, allow_blank=True, default=""
    )
    original_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    exchange_rate = serializers.DecimalField(
        max_digits=18, decimal_places=8, required=False, allow_null=True
    )
    rate_basis = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )
    payer_name = serializers.CharField(
        max_length=180, required=False, allow_blank=True, default=""
    )
    reference = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_method(self, value):
        from apps.finance.models import PaymentMethod

        if value not in {code for code, _ in PaymentMethod.choices}:
            raise serializers.ValidationError("Unsupported payment method.")
        return value

    def validate(self, attrs):
        if attrs.get("amount") is None and attrs.get("original_amount") is None:
            raise serializers.ValidationError(
                "Provide an amount (or original_amount for a foreign-currency "
                "deposit)."
            )
        return attrs


class ImmediateCheckInSerializer(serializers.Serializer):
    """Validate the composed immediate-check-in payload.

    ``reservation`` REUSES the reservations write serializer, so lines / primary
    guest / occupants / capacity are resolved and hotel-scoped exactly as a normal
    reservation create. ``room`` is the physical room to admit into; ``line_index``
    picks the reservation line when there is more than one; ``deposit`` is optional.
    """

    reservation = ReservationWriteSerializer()
    room = serializers.IntegerField(required=False, allow_null=True)
    line_index = serializers.IntegerField(
        required=False, allow_null=True, min_value=0
    )
    check_in_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    deposit = ImmediateDepositSerializer(required=False, allow_null=True)
