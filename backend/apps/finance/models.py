"""Internal finance (Phase 8) — the hotel's own money records.

This is an **internal accounting layer only**: folios, charges, payments,
invoices, and expenses. It is deliberately NOT a payment gateway, external
accounting/e-invoicing integration, daily close, or advanced reporting.

Money rules enforced across this app:
- **Decimal only** — money is never a float.
- **No hard delete** of posted records — use ``void`` (with a reason).
- **Balances are computed** from posted charges/payments, never trusted from a
  single stored number (a service re-derives them from the line items).
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

MONEY_KW = dict(max_digits=12, decimal_places=2)
ZERO = Decimal("0.00")


class NumberKind(models.TextChoices):
    FOLIO = "folio", "Folio"
    RECEIPT = "receipt", "Receipt"
    INVOICE = "invoice", "Invoice"
    EXPENSE = "expense", "Expense"
    CHARGE = "charge", "Charge"


class FinancialNumberSequence(models.Model):
    """A per-hotel, per-kind monotonic counter for financial document numbers.

    Numbers are allocated inside a transaction with ``select_for_update`` so two
    concurrent allocations can never collide (see ``services.next_number``).
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="number_sequences"
    )
    kind = models.CharField(max_length=16, choices=NumberKind.choices)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "finance_number_sequences"
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "kind"], name="unique_number_sequence_per_hotel_kind"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} seq hotel={self.hotel_id} @ {self.last_number}"


class FolioStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    VOIDED = "voided", "Voided"


class Folio(models.Model):
    """The financial account of a reservation or stay."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="folios"
    )
    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios",
    )
    stay = models.ForeignKey(
        "stays.Stay",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios",
    )
    guest = models.ForeignKey(
        "guests.Guest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios",
    )
    customer_name = models.CharField(max_length=180, blank=True, default="")
    folio_number = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16, choices=FolioStatus.choices, default=FolioStatus.OPEN
    )
    currency = models.CharField(max_length=3, default="USD")
    notes = models.TextField(blank=True, default="")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios_closed",
    )
    void_reason = models.CharField(max_length=255, blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios_voided",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="folios_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "folios"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "folio_number"],
                name="unique_folio_number_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.folio_number} (hotel={self.hotel_id})"


class ChargeType(models.TextChoices):
    ROOM = "room", "Room"
    SERVICE = "service", "Service"
    TAX = "tax", "Tax"
    ADJUSTMENT = "adjustment", "Adjustment"
    DISCOUNT = "discount", "Discount"
    OTHER = "other", "Other"


class PostingStatus(models.TextChoices):
    POSTED = "posted", "Posted"
    VOIDED = "voided", "Voided"


# Charge types whose total may be negative (a credit against the folio).
CREDIT_CHARGE_TYPES = (ChargeType.DISCOUNT, ChargeType.ADJUSTMENT)


class FolioCharge(models.Model):
    """A single amount owed on a folio (room, service, tax, discount, …)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="folio_charges"
    )
    folio = models.ForeignKey(
        Folio, on_delete=models.PROTECT, related_name="charges"
    )
    charge_number = models.CharField(max_length=32, blank=True, default="")
    type = models.CharField(
        max_length=16, choices=ChargeType.choices, default=ChargeType.SERVICE
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1"))
    unit_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    amount = models.DecimalField(**MONEY_KW, default=ZERO)
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=ZERO
    )  # percent, e.g. 15.00
    tax_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    total_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    charge_date = models.DateField()
    source = models.CharField(max_length=16, blank=True, default="manual")
    status = models.CharField(
        max_length=16, choices=PostingStatus.choices, default=PostingStatus.POSTED
    )
    void_reason = models.CharField(max_length=255, blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges_voided",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charges_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "folio_charges"
        ordering = ["charge_date", "id"]

    def __str__(self) -> str:
        return f"charge {self.total_amount} on folio={self.folio_id}"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    ELECTRONIC = "electronic", "Electronic"
    OTHER = "other", "Other"


class Payment(models.Model):
    """A receipt: money received against a folio. INTERNAL record only —
    ``card``/``electronic`` here do NOT process a real transaction."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="payments"
    )
    folio = models.ForeignKey(
        Folio, on_delete=models.PROTECT, related_name="payments"
    )
    receipt_number = models.CharField(max_length=32)
    amount = models.DecimalField(**MONEY_KW)
    currency = models.CharField(max_length=3, default="USD")
    method = models.CharField(
        max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    status = models.CharField(
        max_length=16, choices=PostingStatus.choices, default=PostingStatus.POSTED
    )
    paid_at = models.DateTimeField()
    payer_name = models.CharField(max_length=180, blank=True, default="")
    reference = models.CharField(max_length=120, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    void_reason = models.CharField(max_length=255, blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_voided",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments"
        ordering = ["-paid_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "receipt_number"],
                name="unique_receipt_number_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"payment {self.amount} on folio={self.folio_id}"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    VOIDED = "voided", "Voided"


class Invoice(models.Model):
    """An invoice issued from a folio. Once ``issued`` it is an immutable
    snapshot of the customer, lines, and totals."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="invoices"
    )
    folio = models.ForeignKey(
        Folio, on_delete=models.PROTECT, related_name="invoices"
    )
    invoice_number = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT
    )
    currency = models.CharField(max_length=3, default="USD")
    issued_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(**MONEY_KW, default=ZERO)
    tax_total = models.DecimalField(**MONEY_KW, default=ZERO)
    total = models.DecimalField(**MONEY_KW, default=ZERO)
    balance_at_issue = models.DecimalField(**MONEY_KW, default=ZERO)
    customer_name = models.CharField(max_length=180, blank=True, default="")
    customer_phone = models.CharField(max_length=32, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    void_reason = models.CharField(max_length=255, blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_voided",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "invoice_number"],
                condition=~models.Q(invoice_number=""),
                name="unique_invoice_number_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"invoice {self.invoice_number or 'draft'} (hotel={self.hotel_id})"


class InvoiceLine(models.Model):
    """A frozen snapshot of a charge at the moment the invoice was issued."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="invoice_lines"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="lines"
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1"))
    unit_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    tax_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    total_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    source_charge = models.ForeignKey(
        FolioCharge,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoice_lines"
        ordering = ["invoice_id", "id"]

    def __str__(self) -> str:
        return f"invoice_line {self.total_amount} (invoice={self.invoice_id})"


class ExpenseCategory(models.TextChoices):
    OPERATIONS = "operations", "Operations"
    MAINTENANCE = "maintenance", "Maintenance"
    SUPPLIES = "supplies", "Supplies"
    MARKETING = "marketing", "Marketing"
    SALARY = "salary", "Salary"
    UTILITIES = "utilities", "Utilities"
    OTHER = "other", "Other"


class Expense(models.Model):
    """A hotel expense / payment voucher. Internal record only — no payroll,
    no ledger, no bank reconciliation."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="expenses"
    )
    expense_number = models.CharField(max_length=32)
    category = models.CharField(
        max_length=16, choices=ExpenseCategory.choices, default=ExpenseCategory.OTHER
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(**MONEY_KW)
    currency = models.CharField(max_length=3, default="USD")
    method = models.CharField(
        max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    paid_at = models.DateTimeField()
    vendor_name = models.CharField(max_length=180, blank=True, default="")
    reference = models.CharField(max_length=120, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=16, choices=PostingStatus.choices, default=PostingStatus.POSTED
    )
    void_reason = models.CharField(max_length=255, blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_voided",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "expenses"
        ordering = ["-paid_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "expense_number"],
                name="unique_expense_number_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"expense {self.amount} (hotel={self.hotel_id})"
