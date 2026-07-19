"""Serializers for the guest extra-services API (input validation only).

The catalog itself is managed via the Django admin (deactivate, never delete);
these serializers cover the two operational endpoints — add-service and the
folio directory. Money/price/tax are resolved SERVER-SIDE in the service layer;
the client never sends ``source`` or the tax/total.
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    _CURRENCY_CODE_RE,
    GuestExtraService,
    normalize_service_name,
)

ZERO = Decimal("0.00")


class GuestExtraServiceSerializer(serializers.ModelSerializer):
    """The hotel's extra-services catalog (P9 "Services & Prices" tab).

    Enforces every #12 invariant at the serializer boundary (in addition to the
    DB constraints): non-empty name after trim, a 3-letter currency code, a
    non-negative unit price, tax 0..100, non-negative display order, a
    fixed/variable pricing mode, and per-hotel uniqueness of the NORMALIZED name
    (a friendly 400, never a raw IntegrityError 500). ``is_active`` is READ-ONLY
    here — deactivation/activation has its own endpoint gated on ``services.delete``
    so it never rides in on a ``services.update`` PATCH."""

    class Meta:
        model = GuestExtraService
        fields = [
            "id",
            "name",
            "category",
            "description",
            "unit_price",
            "currency",
            "tax_rate",
            "pricing_mode",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_active", "created_at", "updated_at"]

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("A service name is required.")
        return name

    def validate_currency(self, value):
        code = (value or "").strip().upper()
        if not _CURRENCY_CODE_RE.match(code):
            raise serializers.ValidationError("Currency must be a 3-letter code.")
        return code

    def validate_unit_price(self, value):
        if value is not None and value < ZERO:
            raise serializers.ValidationError("Unit price cannot be negative.")
        return value

    def validate_tax_rate(self, value):
        if value is not None and not (ZERO <= value <= Decimal("100")):
            raise serializers.ValidationError("Tax rate must be between 0 and 100.")
        return value

    def validate_display_order(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Display order cannot be negative.")
        return value

    def validate(self, attrs):
        # Per-hotel uniqueness on the NORMALIZED name — a friendly 400 (the DB
        # constraint is the backstop for a race, converted in the view).
        request = self.context.get("request")
        hotel = getattr(request, "hotel", None)
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        normalized = normalize_service_name(name or "")
        if hotel is not None and normalized:
            qs = GuestExtraService.objects.filter(
                hotel=hotel, name_normalized=normalized
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": "A service with this name already exists."}
                )
        return attrs


class AddGuestServiceSerializer(serializers.Serializer):
    """Body for ``POST guest-services/stays/{stay_id}/add/``.

    ``service`` is the catalog ``GuestExtraService`` id (resolved + tenant-checked
    in the view). ``unit_price_override`` is honored ONLY for a VARIABLE service
    and only for a caller holding ``finance.charge_create`` (enforced in the
    service); on a FIXED service it is ignored. ``reason`` is mandatory when an
    override is actually applied. ``idempotency_key`` is optional (empty = no
    idempotency)."""

    service = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01")
    )
    unit_price_override = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0"),
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, max_length=255, default=""
    )
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, max_length=64, default=""
    )
