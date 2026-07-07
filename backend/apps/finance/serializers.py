"""DRF serializers for internal finance (Phase 8). Money is always Decimal."""
from __future__ import annotations

from rest_framework import serializers

from .models import (
    Expense,
    Folio,
    FolioCharge,
    Invoice,
    InvoiceLine,
    Payment,
)
from .services import folio_balance


class FolioChargeSerializer(serializers.ModelSerializer):
    voided_by = serializers.SerializerMethodField()

    class Meta:
        model = FolioCharge
        fields = [
            "id", "charge_number", "type", "description", "quantity",
            "unit_amount", "amount", "tax_rate", "tax_amount", "total_amount",
            "charge_date", "source", "status", "void_reason", "voided_at",
            "voided_by", "created_at",
        ]
        read_only_fields = fields

    def get_voided_by(self, obj):
        return obj.voided_by.email if obj.voided_by_id else None


class PaymentSerializer(serializers.ModelSerializer):
    folio_number = serializers.CharField(source="folio.folio_number", read_only=True)
    voided_by = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id", "folio", "folio_number", "receipt_number", "amount", "currency",
            "method", "status", "paid_at", "payer_name", "reference", "notes",
            "void_reason", "voided_at", "voided_by", "created_at",
        ]
        read_only_fields = fields

    def get_voided_by(self, obj):
        return obj.voided_by.email if obj.voided_by_id else None


class FolioSerializer(serializers.ModelSerializer):
    reservation_number = serializers.CharField(
        source="reservation.reservation_number", read_only=True, default=None
    )
    guest_name = serializers.CharField(
        source="guest.full_name", read_only=True, default=None
    )
    balance = serializers.SerializerMethodField()
    charges = FolioChargeSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Folio
        fields = [
            "id", "folio_number", "status", "currency", "reservation",
            "reservation_number", "stay", "guest", "guest_name", "customer_name",
            "notes", "opened_at", "closed_at", "void_reason", "voided_at",
            "balance", "charges", "payments", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_balance(self, obj):
        return {k: str(v) for k, v in folio_balance(obj).items()}


class FolioListSerializer(serializers.ModelSerializer):
    """Lighter folio row (no nested charges/payments) for lists."""

    reservation_number = serializers.CharField(
        source="reservation.reservation_number", read_only=True, default=None
    )
    guest_name = serializers.CharField(
        source="guest.full_name", read_only=True, default=None
    )
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Folio
        fields = [
            "id", "folio_number", "status", "currency", "reservation",
            "reservation_number", "stay", "guest", "guest_name", "customer_name",
            "balance", "opened_at", "created_at",
        ]
        read_only_fields = fields

    def get_balance(self, obj):
        return {k: str(v) for k, v in folio_balance(obj).items()}


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id", "description", "quantity", "unit_amount", "tax_rate",
            "tax_amount", "total_amount", "source_charge",
        ]
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    folio_number = serializers.CharField(source="folio.folio_number", read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "folio", "folio_number", "invoice_number", "status", "currency",
            "issued_at", "due_date", "subtotal", "tax_total", "total",
            "balance_at_issue", "customer_name", "customer_phone", "notes",
            "void_reason", "voided_at", "lines", "created_at",
        ]
        read_only_fields = fields


class ExpenseSerializer(serializers.ModelSerializer):
    voided_by = serializers.SerializerMethodField()
    paid_at = serializers.DateTimeField(required=False)

    class Meta:
        model = Expense
        fields = [
            "id", "expense_number", "category", "description", "amount", "currency",
            "method", "paid_at", "vendor_name", "reference", "notes", "status",
            "void_reason", "voided_at", "voided_by", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "expense_number", "status", "void_reason", "voided_at",
            "voided_by", "created_at", "updated_at",
        ]

    def get_voided_by(self, obj):
        return obj.voided_by.email if obj.voided_by_id else None

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value


# --- Write / action payloads ------------------------------------------------


class FolioCreateSerializer(serializers.Serializer):
    reservation = serializers.IntegerField(required=False, allow_null=True)
    stay = serializers.IntegerField(required=False, allow_null=True)
    guest = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ChargeCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=FolioCharge._meta.get_field("type").choices)
    description = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    charge_date = serializers.DateField(required=False, allow_null=True)


class PaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(choices=Payment._meta.get_field("method").choices)
    paid_at = serializers.DateTimeField(required=False, allow_null=True)
    payer_name = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value


class InvoiceCreateSerializer(serializers.Serializer):
    due_date = serializers.DateField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    customer_phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("A reason is required.")
        return value.strip()
