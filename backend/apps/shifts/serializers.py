"""Serializers for shifts / handover / daily close (Phase 12).

Write serializers validate SHAPE only; every rule (single open shift, cash
difference reason, recipient guard, day-close validations) lives in the
domain services. Money is Decimal, serialized as strings.
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    DailyClose,
    HandoverStatus,
    Shift,
    ShiftHandover,
    ShiftStatus,
)


def _status_log_fields():
    return ["id", "previous_status", "new_status", "note", "changed_by_name", "created_at"]


class _LogSerializerBase(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    previous_status = serializers.CharField(read_only=True)
    new_status = serializers.CharField(read_only=True)
    note = serializers.CharField(read_only=True)
    changed_by_name = serializers.CharField(
        source="changed_by.full_name", read_only=True, default=""
    )
    created_at = serializers.DateTimeField(read_only=True)


# --- Shifts -------------------------------------------------------------------


class ShiftListSerializer(serializers.ModelSerializer):
    responsible_name = serializers.CharField(
        source="responsible_user.full_name", read_only=True, default=""
    )

    class Meta:
        model = Shift
        fields = [
            "id", "shift_number", "business_date", "status",
            "responsible_user", "responsible_name", "opened_at", "closed_at",
            "opening_cash_amount", "expected_cash_amount",
            "actual_cash_amount", "cash_difference",
        ]
        read_only_fields = fields


class ShiftSerializer(serializers.ModelSerializer):
    responsible_name = serializers.CharField(
        source="responsible_user.full_name", read_only=True, default=""
    )
    opened_by_name = serializers.CharField(
        source="opened_by.full_name", read_only=True, default=""
    )
    status_logs = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            "id", "shift_number", "business_date", "status",
            "responsible_user", "responsible_name", "opened_by",
            "opened_by_name", "opened_at", "closed_at", "cancelled_at",
            "cancellation_reason", "opening_cash_amount",
            "expected_cash_amount", "actual_cash_amount", "cash_difference",
            "difference_reason", "opening_notes", "closing_notes",
            "internal_notes", "status_logs", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_status_logs(self, shift):
        logs = shift.status_logs.select_related("changed_by")[:10]
        return [
            {
                "id": log.id,
                "previous_status": log.previous_status,
                "new_status": log.new_status,
                "note": log.note,
                "changed_by_name": log.changed_by.full_name if log.changed_by else "",
                "created_at": log.created_at,
            }
            for log in logs
        ]


class ShiftOpenSerializer(serializers.Serializer):
    responsible_user = serializers.IntegerField(required=False, allow_null=True)
    opening_cash_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"),
        min_value=Decimal("0.00"),
    )
    opening_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    internal_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    business_date = serializers.DateField(required=False, allow_null=True)


class ShiftUpdateSerializer(serializers.Serializer):
    opening_cash_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.00")
    )
    opening_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    internal_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class ShiftCloseSerializer(serializers.Serializer):
    actual_cash_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00")
    )
    difference_reason = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    closing_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


# --- Handover -----------------------------------------------------------------


class HandoverListSerializer(serializers.ModelSerializer):
    from_shift_number = serializers.CharField(
        source="from_shift.shift_number", read_only=True, default=""
    )
    to_user_name = serializers.CharField(
        source="to_user.full_name", read_only=True, default=""
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = ShiftHandover
        fields = [
            "id", "handover_number", "from_shift", "from_shift_number",
            "to_user", "to_user_name", "status", "created_by_name",
            "submitted_at", "accepted_at", "created_at",
        ]
        read_only_fields = fields


class HandoverSerializer(serializers.ModelSerializer):
    from_shift_number = serializers.CharField(
        source="from_shift.shift_number", read_only=True, default=""
    )
    to_user_name = serializers.CharField(
        source="to_user.full_name", read_only=True, default=""
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=""
    )
    status_logs = serializers.SerializerMethodField()

    class Meta:
        model = ShiftHandover
        fields = [
            "id", "handover_number", "from_shift", "from_shift_number",
            "to_user", "to_user_name", "status", "submitted_at",
            "accepted_at", "rejected_at", "cancelled_at", "rejection_reason",
            "cancellation_reason", "summary_notes", "pending_tasks_notes",
            "cash_notes", "guest_notes", "maintenance_notes",
            "lost_found_notes", "created_by_name", "status_logs",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_status_logs(self, handover):
        logs = handover.status_logs.select_related("changed_by")[:10]
        return [
            {
                "id": log.id,
                "previous_status": log.previous_status,
                "new_status": log.new_status,
                "note": log.note,
                "changed_by_name": log.changed_by.full_name if log.changed_by else "",
                "created_at": log.created_at,
            }
            for log in logs
        ]


class HandoverCreateSerializer(serializers.Serializer):
    from_shift = serializers.IntegerField()
    to_user = serializers.IntegerField()
    summary_notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    pending_tasks_notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    cash_notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    guest_notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    maintenance_notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    lost_found_notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class HandoverUpdateSerializer(serializers.Serializer):
    to_user = serializers.IntegerField(required=False, allow_null=True)
    summary_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    pending_tasks_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    cash_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    guest_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    maintenance_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    lost_found_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


# --- Daily close ---------------------------------------------------------------


class DailyCloseSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(
        source="closed_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = DailyClose
        fields = [
            "id", "close_number", "business_date", "status", "closed_by",
            "closed_by_name", "closed_at", "notes", "snapshot_json",
            "totals_json", "created_at", "updated_at",
        ]
        read_only_fields = fields


class DailyCloseListSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(
        source="closed_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = DailyClose
        fields = [
            "id", "close_number", "business_date", "status",
            "closed_by_name", "closed_at", "totals_json",
        ]
        read_only_fields = fields


class DailyCloseActionSerializer(serializers.Serializer):
    business_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
