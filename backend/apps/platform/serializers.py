"""DRF serializers for the platform-owner API (Phase 3).

Phase 3 introduces the project's first real CRUD surface, so — unlike the
hand-written dict serializers used for the Phase 2 auth probes — these use DRF
``ModelSerializer``s for validation, partial updates and consistent error
envelopes. All output stays snake_case to match the rest of the API.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.subscriptions.models import (
    HotelSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel, HotelStatus

from .services import get_primary_manager

# --- Subscription plans -----------------------------------------------------


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    is_in_use = serializers.BooleanField(read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price",
            "currency",
            "billing_cycle",
            "trial_days",
            "room_limit",
            "user_limit",
            "feature_codes",
            "is_active",
            "sort_order",
            "is_in_use",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_in_use", "created_at", "updated_at"]

    def validate_feature_codes(self, value):
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise serializers.ValidationError(
                "feature_codes must be a list of strings."
            )
        return value


# --- Hotels / tenants -------------------------------------------------------


class PrimaryManagerSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    is_active = serializers.BooleanField()


class SubscriptionSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    plan_id = serializers.IntegerField()
    plan_name = serializers.CharField(source="plan.name")
    status = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    trial_ends_at = serializers.DateTimeField()


class HotelSerializer(serializers.ModelSerializer):
    """Read representation of a hotel tenant, with owner-relevant context."""

    primary_manager = serializers.SerializerMethodField()
    current_subscription = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = [
            "id",
            "name",
            "slug",
            "status",
            "primary_manager",
            "current_subscription",
            "created_at",
            "updated_at",
        ]

    def get_primary_manager(self, hotel):
        user = get_primary_manager(hotel)
        if user is None:
            return None
        return PrimaryManagerSummarySerializer(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
            }
        ).data

    def get_current_subscription(self, hotel):
        # Imported here to avoid an import cycle at module load.
        from apps.subscriptions.services import get_current_subscription

        sub = get_current_subscription(hotel)
        if sub is None:
            return None
        return SubscriptionSummarySerializer(sub).data


class ManagerInputSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)
    password = serializers.CharField(min_length=8, write_only=True)


class HotelCreateSerializer(serializers.ModelSerializer):
    """Create a minimal hotel tenant, optionally with a primary manager."""

    manager = ManagerInputSerializer(required=False)

    class Meta:
        model = Hotel
        fields = ["name", "slug", "status", "manager"]
        extra_kwargs = {"status": {"required": False}}


class HotelUpdateSerializer(serializers.ModelSerializer):
    """Update only the basic tenant fields allowed in Phase 3."""

    class Meta:
        model = Hotel
        fields = ["name", "slug", "status"]
        extra_kwargs = {
            "name": {"required": False},
            "slug": {"required": False},
            "status": {"required": False},
        }


# --- Hotel subscriptions ----------------------------------------------------


class HotelSubscriptionSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)

    class Meta:
        model = HotelSubscription
        fields = [
            "id",
            "hotel",
            "hotel_name",
            "plan",
            "plan_name",
            "status",
            "starts_at",
            "ends_at",
            "trial_ends_at",
            "cancelled_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SubscriptionCreateSerializer(serializers.Serializer):
    """Create a subscription by starting a trial or activating a paid plan."""

    KIND_TRIAL = "trial"
    KIND_PAID = "paid"

    hotel = serializers.PrimaryKeyRelatedField(queryset=Hotel.objects.all())
    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.all())
    kind = serializers.ChoiceField(choices=[KIND_TRIAL, KIND_PAID])
    trial_days = serializers.IntegerField(required=False, min_value=0)
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["kind"] == self.KIND_PAID and not attrs["plan"].is_active:
            raise serializers.ValidationError(
                {"plan": "Cannot activate a paid subscription on an inactive plan."}
            )
        return attrs


class SubscriptionUpdateSerializer(serializers.Serializer):
    """Patch a subscription's status (cancel/expire) and/or notes."""

    ALLOWED_STATUSES = [SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED]

    status = serializers.ChoiceField(choices=ALLOWED_STATUSES, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


# --- Platform settings ------------------------------------------------------


class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import PlatformSettings

        model = PlatformSettings
        fields = [
            "platform_name",
            "support_email",
            "support_phone",
            "support_whatsapp",
            "website_url",
            "default_language",
            "default_currency",
            "default_trial_days",
            "allow_public_registration",
            "maintenance_mode",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]
