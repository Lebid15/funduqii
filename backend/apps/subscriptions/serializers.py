"""DRF serializers for the subscription change-request API (§8.5).

Shared by BOTH the hotel-facing endpoints (apps.hotels) and the platform-owner
endpoints (apps.platform), so the request read contract is defined once. The
hotel serializer is deliberately narrower (no internal actor emails); the
platform serializer adds hotel + actor context for the owner review UI.
"""
from __future__ import annotations

from rest_framework import serializers

from .entitlements import normalize_feature_codes
from .models import (
    ChangeRequestKind,
    SubscriptionChangeRequest,
    SubscriptionPlan,
)

# The kinds a HOTEL may initiate (downgrades are not hotel-initiated).
HOTEL_REQUEST_KINDS = [
    ChangeRequestKind.NEW_SUBSCRIPTION,
    ChangeRequestKind.RENEWAL,
    ChangeRequestKind.PLAN_CHANGE,
]


# --- Available plans with per-hotel state (§8.4) -----------------------------


class AvailablePlanSerializer(serializers.Serializer):
    """One plan row for the hotel's plan grid: flat plan fields + per-hotel
    ``state`` / ``requestable`` / ``request_kind``."""

    def to_representation(self, row):
        plan: SubscriptionPlan = row["plan"]
        return {
            "id": plan.id,
            "name": plan.name,
            "slug": plan.slug,
            "description": plan.description,
            "price": str(plan.price),
            "price_yearly": (
                str(plan.price_yearly) if plan.price_yearly is not None else None
            ),
            "currency": plan.currency,
            "billing_cycle": plan.billing_cycle,
            "trial_days": plan.trial_days,
            "room_limit": plan.room_limit,
            "user_limit": plan.user_limit,
            "max_public_bookings_per_month": plan.max_public_bookings_per_month,
            "feature_codes": normalize_feature_codes(plan.feature_codes),
            "sort_order": plan.sort_order,
            "state": row["state"],
            "requestable": row["requestable"],
            "request_kind": row["request_kind"],
        }


# --- Change request read representation ---------------------------------------


class SubscriptionChangeRequestSerializer(serializers.ModelSerializer):
    """Hotel-safe read view of a change request (no internal actor emails)."""

    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    requested_plan_name = serializers.SerializerMethodField()
    current_plan_name = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionChangeRequest
        fields = [
            "id",
            "kind",
            "kind_display",
            "status",
            "status_display",
            "requested_plan",
            "requested_plan_name",
            "current_plan_name",
            "hotel_note",
            "admin_note",
            "decided_at",
            "executed_at",
            "resulting_subscription",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_requested_plan_name(self, obj):
        return obj.requested_plan.name if obj.requested_plan_id else None

    def get_current_plan_name(self, obj):
        sub = obj.current_subscription
        return sub.plan.name if sub is not None else None


class PlatformChangeRequestSerializer(SubscriptionChangeRequestSerializer):
    """Owner review view — adds hotel + actor context."""

    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    requested_by = serializers.SerializerMethodField()
    decided_by = serializers.SerializerMethodField()

    class Meta(SubscriptionChangeRequestSerializer.Meta):
        fields = SubscriptionChangeRequestSerializer.Meta.fields + [
            "hotel",
            "hotel_name",
            "requested_by",
            "decided_by",
        ]
        read_only_fields = fields

    def get_requested_by(self, obj):
        return obj.requested_by.email if obj.requested_by_id else None

    def get_decided_by(self, obj):
        return obj.decided_by.email if obj.decided_by_id else None


# --- Inputs -------------------------------------------------------------------


class SubmitChangeRequestSerializer(serializers.Serializer):
    """Hotel input to submit a request. Eligibility is re-validated in the
    service (the frontend never decides it)."""

    kind = serializers.ChoiceField(choices=HOTEL_REQUEST_KINDS)
    requested_plan = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.all(), required=False, allow_null=True
    )
    hotel_note = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=1000
    )

    def validate(self, attrs):
        kind = attrs["kind"]
        if kind != ChangeRequestKind.RENEWAL and not attrs.get("requested_plan"):
            raise serializers.ValidationError(
                {"requested_plan": "A target plan is required for this request."}
            )
        return attrs


class RejectRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class ExecuteRequestSerializer(serializers.Serializer):
    """Execute an accepted request, optionally recording a MANUAL payment
    (never a gateway) — same money model as the owner lifecycle actions."""

    notes = serializers.CharField(required=False, allow_blank=True, default="")
    payment_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    payment_method = serializers.ChoiceField(
        choices=["cash", "bank_transfer", "manual", "other"], required=False
    )
    payment_reference = serializers.CharField(
        required=False, allow_blank=True, default=""
    )

    def validate(self, attrs):
        if attrs.get("payment_amount") is not None and not attrs.get("payment_method"):
            raise serializers.ValidationError(
                {"payment_method": "A method is required to record a payment."}
            )
        return attrs
