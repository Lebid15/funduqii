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
    adjusts_number = serializers.CharField(
        source="adjusts.charge_number", read_only=True, default=None
    )

    class Meta:
        model = FolioCharge
        fields = [
            "id", "charge_number", "type", "description", "quantity",
            "unit_amount", "amount", "tax_rate", "tax_amount", "total_amount",
            "charge_date", "source", "adjusts", "adjusts_number", "status",
            "void_reason", "voided_at", "voided_by", "created_at",
        ]
        read_only_fields = fields

    def get_voided_by(self, obj):
        return obj.voided_by.email if obj.voided_by_id else None


class PaymentSerializer(serializers.ModelSerializer):
    folio_number = serializers.CharField(source="folio.folio_number", read_only=True)
    # Safe read via the folio relation — for the printed receipt only.
    reservation_number = serializers.CharField(
        source="folio.reservation.reservation_number", read_only=True, default=None
    )
    created_by = serializers.SerializerMethodField()
    voided_by = serializers.SerializerMethodField()

    reverses_receipt = serializers.CharField(
        source="reverses.receipt_number", read_only=True, default=None
    )

    class Meta:
        model = Payment
        fields = [
            "id", "folio", "folio_number", "reservation_number", "receipt_number",
            "amount", "currency", "method", "status", "paid_at", "business_date",
            "reverses", "reverses_receipt", "payer_name",
            "reference", "notes", "void_reason", "voided_at", "voided_by",
            "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by_id else None

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
    # Safe read via the folio relation — for the printed invoice only.
    reservation_number = serializers.CharField(
        source="folio.reservation.reservation_number", read_only=True, default=None
    )
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "folio", "folio_number", "reservation_number", "invoice_number",
            "status", "currency", "issued_at", "due_date", "subtotal", "tax_total",
            "total", "balance_at_issue", "customer_name", "customer_phone",
            "customer_email", "customer_document_number", "notes",
            "void_reason", "voided_at", "lines", "created_at",
        ]
        read_only_fields = fields


class ExpenseSerializer(serializers.ModelSerializer):
    """Read + CREATE shape. The execution timestamp, financial date, and
    currency are backend-decided (expenses closure); the descriptive-edit
    path uses ``ExpenseUpdateSerializer``."""

    created_by = serializers.SerializerMethodField()
    voided_by = serializers.SerializerMethodField()
    shift_number = serializers.CharField(
        source="shift.shift_number", read_only=True, default=None
    )
    reverses_number = serializers.CharField(
        source="reverses.expense_number", read_only=True, default=None
    )
    reversed_by_number = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id", "expense_number", "category", "description", "amount", "currency",
            "method", "paid_at", "business_date", "shift", "shift_number",
            "reverses", "reverses_number", "reversed_by_number",
            "vendor_name", "reference", "notes", "status",
            "void_reason", "voided_at", "voided_by", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "expense_number", "currency", "paid_at", "business_date",
            "shift", "shift_number", "reverses", "reverses_number",
            "reversed_by_number", "status", "void_reason", "voided_at",
            "voided_by", "created_by", "created_at", "updated_at",
        ]

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by_id else None

    def get_voided_by(self, obj):
        return obj.voided_by.email if obj.voided_by_id else None

    def get_reversed_by_number(self, obj):
        posted = [r for r in obj.reversals.all() if r.status == "posted"]
        return posted[0].expense_number if posted else None

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value

    def validate(self, attrs):
        _reject_fields(self, "paid_at", "business_date", "currency", "shift", "reverses")
        return attrs


class ExpenseUpdateSerializer(serializers.Serializer):
    """The ONLY editable voucher fields — descriptive text, same open
    business date (enforced by the service)."""

    description = serializers.CharField(max_length=255, required=False)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    vendor_name = serializers.CharField(max_length=180, required=False, allow_blank=True)

    def validate(self, attrs):
        _reject_fields(
            self, "amount", "category", "method", "currency", "paid_at",
            "business_date", "shift", "hotel", "status", "reverses",
        )
        return attrs


# --- Write / action payloads ------------------------------------------------


def _reject_fields(serializer, *names):
    """Folio closure round: fields the backend now decides (business date,
    payment time, currency) are refused outright so a client can never
    believe it controlled them."""
    provided = [n for n in names if n in (serializer.initial_data or {})]
    if provided:
        raise serializers.ValidationError(
            {name: "This field is set by the backend." for name in provided}
        )


class FolioCreateSerializer(serializers.Serializer):
    reservation = serializers.IntegerField(required=False, allow_null=True)
    stay = serializers.IntegerField(required=False, allow_null=True)
    guest = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        _reject_fields(self, "currency")
        return attrs


class ChargeCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=FolioCharge._meta.get_field("type").choices)
    description = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)

    def validate(self, attrs):
        _reject_fields(self, "charge_date")
        return attrs


class PaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(choices=Payment._meta.get_field("method").choices)
    payer_name = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value

    def validate(self, attrs):
        _reject_fields(self, "paid_at", "currency")
        return attrs


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
