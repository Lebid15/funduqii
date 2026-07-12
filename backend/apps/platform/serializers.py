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
            "price_yearly",
            "currency",
            "billing_cycle",
            "trial_days",
            "room_limit",
            "user_limit",
            "max_public_bookings_per_month",
            "feature_codes",
            "is_active",
            "is_public",
            "sort_order",
            "notes",
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
    # Phase 16 — owner-panel context: publishing, usage counts, trial + audit.
    trial_used = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    contact_phone = serializers.SerializerMethodField()
    contact_email = serializers.SerializerMethodField()
    public_is_listed = serializers.SerializerMethodField()
    public_booking_enabled = serializers.SerializerMethodField()
    rooms_count = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()
    reservations_count = serializers.SerializerMethodField()
    status_changed_by = serializers.SerializerMethodField()

    class Meta:
        model = Hotel
        fields = [
            "id",
            "name",
            "slug",
            "status",
            "suspension_reason",
            "status_changed_at",
            "status_changed_by",
            "primary_manager",
            "current_subscription",
            "trial_used",
            "city",
            "country",
            "contact_phone",
            "contact_email",
            "public_is_listed",
            "public_booking_enabled",
            "rooms_count",
            "staff_count",
            "reservations_count",
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

    def _settings(self, hotel):
        # HotelSettings may not exist yet for a bare tenant.
        return getattr(hotel, "settings", None)

    def get_trial_used(self, hotel):
        from apps.subscriptions.services import hotel_has_used_trial

        return hotel_has_used_trial(hotel)

    def get_city(self, hotel):
        s = self._settings(hotel)
        return s.city if s else ""

    def get_country(self, hotel):
        s = self._settings(hotel)
        return s.country if s else ""

    def get_contact_phone(self, hotel):
        s = self._settings(hotel)
        return s.phone if s else ""

    def get_contact_email(self, hotel):
        s = self._settings(hotel)
        return s.email if s else ""

    def get_public_is_listed(self, hotel):
        s = self._settings(hotel)
        return bool(s and s.public_is_listed)

    def get_public_booking_enabled(self, hotel):
        s = self._settings(hotel)
        return bool(s and s.allow_public_booking)

    def get_rooms_count(self, hotel):
        return hotel.rooms.count()

    def get_staff_count(self, hotel):
        return hotel.memberships.filter(is_active=True).count()

    def get_reservations_count(self, hotel):
        return hotel.reservations.count()

    def get_status_changed_by(self, hotel):
        return hotel.status_changed_by.email if hotel.status_changed_by_id else None


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
    """Update only the basic tenant fields.

    Phase 16: ``status`` is no longer patchable here — status changes go
    exclusively through the audited actions (activate/suspend/unsuspend),
    which record the reason and the acting user.
    """

    class Meta:
        model = Hotel
        fields = ["name", "slug"]
        extra_kwargs = {
            "name": {"required": False},
            "slug": {"required": False},
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
            "effective_status",
            "starts_at",
            "ends_at",
            "trial_ends_at",
            "cancelled_at",
            "notes",
            "plan_snapshot",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    effective_status = serializers.SerializerMethodField()

    def get_effective_status(self, sub):
        from apps.subscriptions.enforcement import effective_status

        return effective_status(sub)


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


# --- Phase 16: subscription lifecycle inputs ---------------------------------


class StartTrialSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.all())
    trial_days = serializers.IntegerField(required=False, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ActivatePaidSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.all())
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    # Optional MANUAL payment record (cash/bank transfer) — never a gateway.
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
        if not attrs["plan"].is_active:
            raise serializers.ValidationError(
                {"plan": "Cannot activate a paid subscription on an inactive plan."}
            )
        starts = attrs.get("starts_at")
        ends = attrs.get("ends_at")
        if starts and ends and ends <= starts:
            raise serializers.ValidationError(
                {"ends_at": "The end must be after the start."}
            )
        if "payment_amount" in attrs and "payment_method" not in attrs:
            raise serializers.ValidationError(
                {"payment_method": "A method is required to record a payment."}
            )
        return attrs


class RenewSerializer(serializers.Serializer):
    ends_at = serializers.DateTimeField(required=False)
    days = serializers.IntegerField(required=False, min_value=1)
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


class CancelSubscriptionSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ChangePlanSerializer(serializers.Serializer):
    """Explicitly move the hotel's live subscription to a different plan."""

    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True, default="")
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
        if not attrs["plan"].is_active:
            raise serializers.ValidationError(
                {"plan": "Cannot change to an inactive plan."}
            )
        if "payment_amount" in attrs and "payment_method" not in attrs:
            raise serializers.ValidationError(
                {"payment_method": "A method is required to record a payment."}
            )
        return attrs


class ReactivateSerializer(serializers.Serializer):
    """Revive billing for a hotel whose subscription has ended (a NEW one)."""

    plan = serializers.PrimaryKeyRelatedField(queryset=SubscriptionPlan.objects.all())
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
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
        if not attrs["plan"].is_active:
            raise serializers.ValidationError(
                {"plan": "Cannot reactivate on an inactive plan."}
            )
        if "payment_amount" in attrs and "payment_method" not in attrs:
            raise serializers.ValidationError(
                {"payment_method": "A method is required to record a payment."}
            )
        return attrs


class SuspendHotelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


# --- Phase 16: manual platform payments --------------------------------------


class PlatformPaymentSerializer(serializers.ModelSerializer):
    hotel_name = serializers.CharField(source="hotel.name", read_only=True)
    recorded_by = serializers.SerializerMethodField()
    is_voided = serializers.BooleanField(read_only=True)

    class Meta:
        from apps.subscriptions.models import PlatformSubscriptionPayment

        model = PlatformSubscriptionPayment
        fields = [
            "id",
            "hotel",
            "hotel_name",
            "subscription",
            "amount",
            "currency",
            "method",
            "reference",
            "note",
            "received_at",
            "recorded_by",
            "is_voided",
            "voided_at",
            "void_reason",
            "created_at",
        ]
        read_only_fields = fields

    def get_recorded_by(self, obj):
        return obj.recorded_by.email if obj.recorded_by_id else None


class PlatformPaymentCreateSerializer(serializers.Serializer):
    hotel = serializers.PrimaryKeyRelatedField(queryset=Hotel.objects.all())
    subscription = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default="USD")
    method = serializers.ChoiceField(
        choices=["cash", "bank_transfer", "manual", "other"]
    )
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
    received_at = serializers.DateTimeField(required=False)


class VoidPaymentSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


# --- Phase 16: public site settings -------------------------------------------

_I18N_LOCALES = ("ar", "en", "tr")


def _validate_i18n_value(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError("Expected an object of ar/en/tr strings.")
    clean = {}
    for locale in _I18N_LOCALES:
        text = value.get(locale, "")
        if not isinstance(text, str):
            raise serializers.ValidationError(f"'{locale}' must be a string.")
        clean[locale] = text.strip()[:200]
    return clean


def _validate_safe_url(value: str) -> str:
    """Internal path or explicit http(s) only.

    A single leading slash is an internal path, but a PROTOCOL-RELATIVE URL
    ("//evil.com") also starts with "/" and would resolve to an external host
    — it is explicitly rejected (Copilot review finding on PR #15).
    """
    value = (value or "").strip()
    if not value:
        return value
    if value.startswith("//"):
        raise serializers.ValidationError(
            "Protocol-relative URLs (//...) are not allowed."
        )
    if not value.startswith(("/", "http://", "https://")):
        raise serializers.ValidationError(
            "Only internal paths (/...) or http(s) links are allowed."
        )
    return value


class PlatformPublicSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import PlatformPublicSettings

        model = PlatformPublicSettings
        exclude = ["id"]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        for field, value in list(attrs.items()):
            if field.endswith(("_label", "_title", "_subtitle")) or field == "footer_text":
                attrs[field] = _validate_i18n_value(value)
            if field.endswith("_button_url"):
                attrs[field] = _validate_safe_url(value)
        return attrs
