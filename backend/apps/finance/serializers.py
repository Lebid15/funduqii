"""DRF serializers for internal finance (Phase 8). Money is always Decimal."""
from __future__ import annotations

from rest_framework import serializers

from .models import (
    ChargeType,
    Expense,
    ExpenseType,
    Folio,
    FolioCharge,
    Invoice,
    InvoiceLine,
    PaymentMethod,
    Payment,
    RefundableInsurance,
)
from .services import folio_balance


class InsuranceSerializer(serializers.ModelSerializer):
    held_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = RefundableInsurance
        fields = [
            "id", "reservation", "stay", "currency", "amount",
            "deducted_amount", "refunded_amount", "held_amount", "status",
            "method", "reference", "notes", "received_at", "settled_at",
        ]
        read_only_fields = fields


class FolioChargeSerializer(serializers.ModelSerializer):
    voided_by = serializers.SerializerMethodField()
    # P7 — expose the creating staff member on the charge DTO (data already on
    # the model). ``created_by`` mirrors the Payment/Expense convention (email);
    # ``created_by_name`` is the display name for the itemized statement.
    created_by = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    adjusts_number = serializers.CharField(
        source="adjusts.charge_number", read_only=True, default=None
    )

    class Meta:
        model = FolioCharge
        fields = [
            "id", "charge_number", "type", "description", "quantity",
            "unit_amount", "amount", "tax_rate", "tax_amount", "total_amount",
            "charge_date", "source", "adjusts", "adjusts_number", "status",
            # P7 enrichment + P2 frozen snapshots (NULL on historical charges).
            "created_by", "created_by_name",
            "currency_snapshot", "service_name_snapshot", "unit_price_snapshot",
            "tax_rate_snapshot", "source_reference",
            "void_reason", "voided_at", "voided_by", "created_at",
        ]
        read_only_fields = fields

    def get_voided_by(self, obj):
        return obj.voided_by.email if obj.voided_by_id else None

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by_id else None

    def get_created_by_name(self, obj):
        if not obj.created_by_id:
            return None
        return obj.created_by.full_name or obj.created_by.email


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
            # RESERVATIONS-FORM-UX-CORRECTION (§29): the FX snapshot already stored
            # on the model, now surfaced read-only so the reservation detail/edit
            # screens can show payment currency + rate + equivalent. Additive:
            # ``amount``/``currency`` (base) are unchanged, so existing consumers
            # keep working; these are informational and default to "" / null.
            "payment_currency", "original_amount", "exchange_rate", "rate_basis",
            "rate_captured_at",
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


class ExpenseTypeSerializer(serializers.ModelSerializer):
    """Read shape for a manageable per-hotel expense type."""

    class Meta:
        model = ExpenseType
        fields = ["id", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class ExpenseTypeWriteSerializer(serializers.Serializer):
    """Create/rename/(de)activate — normalization + uniqueness live in the
    service. ``name`` is required on create; both fields optional on edit."""

    name = serializers.CharField(max_length=80, required=False, allow_blank=False)
    is_active = serializers.BooleanField(required=False)


class ExpenseSerializer(serializers.ModelSerializer):
    """READ representation only. All writes go through
    ``ExpenseCreateSerializer`` / ``ExpenseUpdateSerializer`` so the service is
    the single money path. ``amount``/``currency`` are the HOTEL BASE values;
    the FX snapshot exposes what was actually entered."""

    created_by = serializers.SerializerMethodField()
    voided_by = serializers.SerializerMethodField()
    shift_number = serializers.CharField(
        source="shift.shift_number", read_only=True, default=None
    )
    reverses_number = serializers.CharField(
        source="reverses.expense_number", read_only=True, default=None
    )
    reversed_by_number = serializers.SerializerMethodField()
    expense_type_name = serializers.CharField(
        source="expense_type.name", read_only=True, default=None
    )
    has_attachment = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            "id", "expense_number", "category", "expense_type", "expense_type_name",
            "description", "amount", "currency",
            "original_currency", "original_amount", "exchange_rate", "rate_basis",
            "rate_captured_at",
            "method", "paid_at", "business_date", "shift", "shift_number",
            "reverses", "reverses_number", "reversed_by_number",
            "vendor_name", "reference", "notes", "has_attachment", "status",
            "void_reason", "voided_at", "voided_by", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by_id else None

    def get_voided_by(self, obj):
        return obj.voided_by.email if obj.voided_by_id else None

    def get_reversed_by_number(self, obj):
        posted = [r for r in obj.reversals.all() if r.status == "posted"]
        return posted[0].expense_number if posted else None

    def get_has_attachment(self, obj):
        return bool(obj.attachment)


def _validate_currency_code(value):
    code = (value or "").strip().upper()
    if code and len(code) != 3:
        raise serializers.ValidationError("Currency must be a 3-letter code.")
    return code


class ExpenseCreateSerializer(serializers.Serializer):
    """CREATE payload. The base currency, timestamp, financial date, and shift
    are backend-decided; ``currency`` here is the ENTRY currency (base or a
    hotel-accepted foreign one). Foreign entry requires ``original_amount`` +
    ``exchange_rate`` (validated + derived by the service)."""

    expense_type = serializers.IntegerField()
    description = serializers.CharField(max_length=255)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
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
    notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    idempotency_key = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )

    def validate_currency(self, value):
        return _validate_currency_code(value)

    def validate(self, attrs):
        _reject_fields(
            self, "paid_at", "business_date", "shift", "reverses", "status",
            "vendor_name", "reference", "category", "hotel",
        )
        return attrs


class ExpenseUpdateSerializer(serializers.Serializer):
    """Atomic financial-edit payload (only inside the open business date). Any
    subset of the fields; money fields present → the service re-derives the base
    amount + FX. Immutable fields are refused outright."""

    description = serializers.CharField(max_length=255, required=False)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    method = serializers.ChoiceField(choices=PaymentMethod.choices, required=False)
    expense_type = serializers.IntegerField(required=False)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    original_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    exchange_rate = serializers.DecimalField(
        max_digits=18, decimal_places=8, required=False, allow_null=True
    )
    rate_basis = serializers.CharField(max_length=32, required=False, allow_blank=True)

    def validate_currency(self, value):
        return _validate_currency_code(value)

    def validate(self, attrs):
        _reject_fields(
            self, "paid_at", "business_date", "shift", "hotel", "status",
            "reverses", "category", "vendor_name", "reference",
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
        # H1 revenue-integrity: ROOM charges are per-NIGHT charges generated only
        # by the system (``ensure_due_room_charges``, which always sets the night).
        # A manual ROOM charge would be unlinked (no room_night) and could suppress
        # automated nightly billing — reject it here with a clear field error.
        if attrs.get("type") == ChargeType.ROOM:
            raise serializers.ValidationError(
                {"type": "room_charges_are_system_generated"}
            )
        # P4 — the generic charge-create path posts DEBITS only. A credit
        # correction (DISCOUNT / ADJUSTMENT) or any negative amount must go
        # through the dedicated ``finance.adjust`` path (``adjust_charge``),
        # which requires a reason, links to the original, is one-per-original,
        # and writes a full audit event. Keeping credits off this path stops
        # unaudited, unlinked, stackable negative postings.
        if attrs.get("type") in (ChargeType.DISCOUNT, ChargeType.ADJUSTMENT):
            raise serializers.ValidationError(
                {"type": "credit_charges_go_through_adjust"}
            )
        if attrs.get("unit_amount") is not None and attrs["unit_amount"] < 0:
            raise serializers.ValidationError(
                {"unit_amount": "must_not_be_negative"}
            )
        if attrs.get("quantity") is not None and attrs["quantity"] < 0:
            raise serializers.ValidationError(
                {"quantity": "must_not_be_negative"}
            )
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
