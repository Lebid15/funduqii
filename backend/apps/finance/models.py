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
            # Folio closure round: ONE open operational folio per stay. The
            # service checks under a stay row lock; this is the DB backstop.
            models.UniqueConstraint(
                fields=["stay"],
                condition=models.Q(status="open", stay__isnull=False),
                name="unique_open_folio_per_stay",
            ),
            # Reservation-form rework: ONE open PRE-ARRIVAL folio per
            # reservation (deposit before check-in), i.e. reservation set and
            # stay still NULL. Mirrors the per-stay guard; the service checks
            # under a reservation row lock and this is the DB backstop. A
            # read-only precheck (zero reservations with >1 open stay-null
            # folio) MUST pass before this constraint is applied.
            models.UniqueConstraint(
                fields=["reservation"],
                condition=models.Q(status="open", stay__isnull=True),
                name="unique_open_folio_per_reservation",
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
    # Folio closure round: a full counter-posting created AFTER the original
    # charge's void window closed. The original is never edited; the link is
    # the audit trail. Adjustments cannot themselves be adjusted (no chains).
    adjusts = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="adjustments",
    )
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
        constraints = [
            # Full-reversal rule: at most ONE posted adjustment per original
            # charge (a voided adjustment frees the slot again).
            models.UniqueConstraint(
                fields=["adjusts"],
                condition=models.Q(status="posted", adjusts__isnull=False),
                name="unique_posted_adjustment_per_charge",
            ),
        ]

    def __str__(self) -> str:
        return f"charge {self.total_amount} on folio={self.folio_id}"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    ELECTRONIC = "electronic", "Electronic"
    # Owner's "electronic داخلي": an internal electronic settlement (e.g. a
    # closed-loop wallet / house account transfer) distinct from an external
    # electronic gateway. NOT a real gateway transaction. NOTE: there is no
    # ``on_room_account`` method by design — posting to the room account is a
    # charge with no Payment (see services.post_room_account_charge).
    INTERNAL_ELECTRONIC = "internal_electronic", "Internal electronic"
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
    # ``amount`` is ALWAYS the equivalent contribution in the folio/base
    # currency — it is the ONLY value ``folio_balance()`` reads, so the balance
    # derivation is unchanged by multi-currency payments.
    amount = models.DecimalField(**MONEY_KW)
    # The folio/base currency of ``amount`` (kept for back-compat; existing
    # rows and same-currency payments record the folio currency here).
    currency = models.CharField(max_length=3, default="USD")
    # --- Multi-currency snapshot (payment layer only) -----------------------
    # All nullable/blank-defaulted so legacy rows are valid unchanged. When the
    # guest tenders a currency other than the folio/base currency, the FX
    # snapshot below is captured; ``amount`` still holds the base equivalent.
    # An empty ``payment_currency`` means "same as folio.currency" (legacy).
    payment_currency = models.CharField(max_length=3, blank=True, default="")
    # The amount actually tendered, expressed in ``payment_currency`` (informational).
    original_amount = models.DecimalField(**MONEY_KW, null=True, blank=True)
    # Manual, high-precision rate (no external gateway/API). Canonical direction:
    # base ``amount`` = ``original_amount`` * ``exchange_rate`` (i.e. units of
    # the folio/base currency per 1 unit of ``payment_currency``). The direction
    # label is stored explicitly in ``rate_basis``.
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=8, null=True, blank=True
    )
    # Free-form annotation recording the rate's direction/meaning (default is
    # the canonical "base_per_payment"); auditors read this, math uses multiply.
    rate_basis = models.CharField(max_length=32, blank=True, default="")
    # When the rate was captured (stamped by the service at creation).
    rate_captured_at = models.DateTimeField(null=True, blank=True)
    # Who entered the manual rate (gated by ``exchange_rate.override`` at the
    # view/serializer layer in a later package).
    rate_entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_rates_entered",
    )
    method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    status = models.CharField(
        max_length=16, choices=PostingStatus.choices, default=PostingStatus.POSTED
    )
    paid_at = models.DateTimeField()
    # Folio closure round: the HOTEL business date the payment belongs to
    # (stamped by the service at creation; NULL only on legacy rows, where it
    # is derived from ``paid_at`` in the hotel's timezone).
    business_date = models.DateField(null=True, blank=True)
    # Folio closure round: a full counter-payment (negative amount) created
    # AFTER the original payment's void window closed. The original is never
    # edited. Reversals cannot themselves be reversed (no chains).
    reverses = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversals",
    )
    # Phase 12: the shift whose cash drawer received this payment. Attached
    # by the finance services when the creator has an open shift; NULL means
    # an "unassigned movement" (reported, never hidden).
    shift = models.ForeignKey(
        "shifts.Shift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
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
            # Full-reversal rule: at most ONE posted reversal per original
            # payment (a voided reversal frees the slot again).
            models.UniqueConstraint(
                fields=["reverses"],
                condition=models.Q(status="posted", reverses__isnull=False),
                name="unique_posted_reversal_per_payment",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "business_date"], name="pay_hotel_bizdate_idx"),
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
    # Extra customer snapshot fields (Phase 8.1) — filled from the folio guest
    # when available so the printed invoice stays immutable.
    customer_email = models.EmailField(blank=True, default="")
    customer_document_number = models.CharField(
        max_length=64, blank=True, default=""
    )
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
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    # Expenses closure: ``paid_at`` is the EXECUTION timestamp only (stamped
    # by the service, never client-sent); the financial date is business_date.
    paid_at = models.DateTimeField()
    # The HOTEL business date the voucher belongs to (stamped by the service;
    # NULL only on legacy rows, derived from ``paid_at`` in the hotel tz).
    business_date = models.DateField(null=True, blank=True)
    # A full counter-voucher (negative amount) created AFTER the original's
    # void window closed. The original is never edited; reversals cannot
    # themselves be reversed (no chains).
    reverses = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversals",
    )
    # Phase 12: the shift whose cash drawer paid this expense (see Payment).
    shift = models.ForeignKey(
        "shifts.Shift",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
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
            # Full-reversal rule: at most ONE posted reversal per original
            # (a voided reversal frees the slot again).
            models.UniqueConstraint(
                fields=["reverses"],
                condition=models.Q(status="posted", reverses__isnull=False),
                name="unique_posted_reversal_per_expense",
            ),
            # Negative amounts exist ONLY on reversal rows (service-built).
            models.CheckConstraint(
                condition=models.Q(reverses__isnull=False) | models.Q(amount__gt=0),
                name="expense_amount_sign",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "business_date"], name="exp_hotel_bizdate_idx"),
        ]

    def __str__(self) -> str:
        return f"expense {self.amount} (hotel={self.hotel_id})"
