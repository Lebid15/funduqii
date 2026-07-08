"""Finance services (Phase 8) — the single controlled path for money.

All numbering, balance math, and lifecycle transitions live here; views never
mutate money directly. Balances are always **re-derived from posted line items**
(a stored total is never trusted). Nothing here touches an external gateway.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    FolioClosed,
    FolioNotBalanced,
    InvalidAmount,
    InvalidFinanceOperation,
    VoidReasonRequired,
)

from .models import (
    CREDIT_CHARGE_TYPES,
    ChargeType,
    Expense,
    FinancialNumberSequence,
    Folio,
    FolioCharge,
    FolioStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    NumberKind,
    Payment,
    PostingStatus,
)

TWO = Decimal("0.01")
ZERO = Decimal("0.00")

_PREFIX = {
    NumberKind.FOLIO: "FOL",
    NumberKind.RECEIPT: "RCP",
    NumberKind.INVOICE: "INV",
    NumberKind.EXPENSE: "EXP",
    NumberKind.CHARGE: "CHG",
}


def money(value) -> Decimal:
    """Quantize any numeric to 2 decimal places (bankers-safe half-up)."""
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def next_number(hotel, kind: str) -> str:
    """Allocate the next per-hotel document number for ``kind``.

    Uses ``select_for_update`` on the sequence row so concurrent allocations
    cannot collide. MUST run inside a transaction.
    """
    seq, _ = FinancialNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel, kind=kind
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"{_PREFIX[kind]}{seq.last_number:05d}"


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


# --- Balance ----------------------------------------------------------------


def folio_balance(folio) -> dict:
    """Re-derive a folio's totals from its posted charges and payments."""
    charges = folio.charges.filter(status=PostingStatus.POSTED)
    payments = folio.payments.filter(status=PostingStatus.POSTED)
    total_charges = money(sum((c.total_amount for c in charges), ZERO))
    total_payments = money(sum((p.amount for p in payments), ZERO))
    return {
        "total_charges": total_charges,
        "total_payments": total_payments,
        "balance": money(total_charges - total_payments),
    }


def compute_charge_totals(quantity, unit_amount, tax_rate, charge_type):
    """Return ``(amount, tax_amount, total_amount)`` for a charge."""
    amount = money(Decimal(quantity) * Decimal(unit_amount))
    tax_amount = money(amount * Decimal(tax_rate) / Decimal("100"))
    total = money(amount + tax_amount)
    is_credit = charge_type in CREDIT_CHARGE_TYPES
    if not is_credit and amount <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    if total == ZERO:
        raise InvalidAmount({"field": "total_amount", "reason": "must_not_be_zero"})
    return amount, tax_amount, total


# --- Folio lifecycle --------------------------------------------------------


@transaction.atomic
def create_folio(hotel, *, reservation=None, stay=None, guest=None,
                 customer_name="", currency=None, notes="", user=None) -> Folio:
    number = next_number(hotel, NumberKind.FOLIO)
    if currency is None:
        currency = _hotel_currency(hotel)
    actor = _actor(user)
    return Folio.objects.create(
        hotel=hotel,
        reservation=reservation,
        stay=stay,
        guest=guest,
        customer_name=customer_name or (guest.full_name if guest else ""),
        folio_number=number,
        currency=currency,
        notes=notes or "",
        created_by=actor,
        updated_by=actor,
    )


def _guard_open(folio):
    if folio.status != FolioStatus.OPEN:
        raise FolioClosed({"folio": folio.id, "status": folio.status})


@transaction.atomic
def close_folio(folio, *, user=None) -> Folio:
    _guard_open(folio)
    if folio_balance(folio)["balance"] != ZERO:
        raise FolioNotBalanced({"folio": folio.id})
    folio.status = FolioStatus.CLOSED
    folio.closed_at = timezone.now()
    folio.closed_by = _actor(user)
    folio.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    return folio


@transaction.atomic
def void_folio(folio, *, reason, user=None) -> Folio:
    if not (reason or "").strip():
        raise VoidReasonRequired()
    if folio.status == FolioStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    folio.status = FolioStatus.VOIDED
    folio.void_reason = reason.strip()
    folio.voided_at = timezone.now()
    folio.voided_by = _actor(user)
    folio.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    return folio


# --- Charges ----------------------------------------------------------------


@transaction.atomic
def add_charge(folio, *, charge_type, description, quantity, unit_amount,
               tax_rate=ZERO, charge_date=None, source="manual", user=None) -> FolioCharge:
    _guard_open(folio)
    amount, tax_amount, total = compute_charge_totals(
        quantity, unit_amount, tax_rate, charge_type
    )
    return FolioCharge.objects.create(
        hotel=folio.hotel,
        folio=folio,
        charge_number=next_number(folio.hotel, NumberKind.CHARGE),
        type=charge_type,
        description=description,
        quantity=money(quantity),
        unit_amount=money(unit_amount),
        amount=amount,
        tax_rate=Decimal(tax_rate),
        tax_amount=tax_amount,
        total_amount=total,
        charge_date=charge_date or timezone.localdate(),
        source=source,
        created_by=_actor(user),
    )


@transaction.atomic
def void_charge(charge, *, reason, user=None) -> FolioCharge:
    if not (reason or "").strip():
        raise VoidReasonRequired()
    if charge.status == PostingStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    charge.status = PostingStatus.VOIDED
    charge.void_reason = reason.strip()
    charge.voided_at = timezone.now()
    charge.voided_by = _actor(user)
    charge.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    return charge


# --- Payments ---------------------------------------------------------------


@transaction.atomic
def record_payment(folio, *, amount, method, paid_at=None, payer_name="",
                   reference="", notes="", currency=None, user=None) -> Payment:
    _guard_open(folio)
    if money(amount) <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    return Payment.objects.create(
        hotel=folio.hotel,
        folio=folio,
        receipt_number=next_number(folio.hotel, NumberKind.RECEIPT),
        amount=money(amount),
        currency=currency or folio.currency,
        method=method,
        paid_at=paid_at or timezone.now(),
        payer_name=payer_name or folio.customer_name,
        reference=reference or "",
        notes=notes or "",
        created_by=_actor(user),
    )


@transaction.atomic
def void_payment(payment, *, reason, user=None) -> Payment:
    if not (reason or "").strip():
        raise VoidReasonRequired()
    if payment.status == PostingStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    payment.status = PostingStatus.VOIDED
    payment.void_reason = reason.strip()
    payment.voided_at = timezone.now()
    payment.voided_by = _actor(user)
    payment.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    return payment


# --- Invoices ---------------------------------------------------------------


@transaction.atomic
def create_invoice(folio, *, due_date=None, customer_name="", customer_phone="",
                   notes="", user=None) -> Invoice:
    """Create a DRAFT invoice for a folio (no number/snapshot until issued)."""
    guest = folio.guest
    return Invoice.objects.create(
        hotel=folio.hotel,
        folio=folio,
        status=InvoiceStatus.DRAFT,
        currency=folio.currency,
        due_date=due_date,
        customer_name=customer_name or folio.customer_name,
        customer_phone=customer_phone or (guest.phone if guest else ""),
        customer_email=guest.email if guest else "",
        customer_document_number=guest.document_number if guest else "",
        notes=notes or "",
        created_by=_actor(user),
    )


@transaction.atomic
def issue_invoice(invoice, *, user=None) -> Invoice:
    """Issue a draft invoice: allocate a number and freeze a line snapshot."""
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvalidFinanceOperation(
            {"reason": "not_draft", "status": invoice.status}
        )
    charges = list(
        invoice.folio.charges.filter(status=PostingStatus.POSTED).order_by(
            "charge_date", "id"
        )
    )
    if not charges:
        raise InvalidFinanceOperation({"reason": "no_charges"})

    subtotal = money(sum((c.amount for c in charges), ZERO))
    tax_total = money(sum((c.tax_amount for c in charges), ZERO))
    total = money(subtotal + tax_total)

    for c in charges:
        InvoiceLine.objects.create(
            hotel=invoice.hotel,
            invoice=invoice,
            description=c.description,
            quantity=c.quantity,
            unit_amount=c.unit_amount,
            tax_rate=c.tax_rate,
            tax_amount=c.tax_amount,
            total_amount=c.total_amount,
            source_charge=c,
        )
    invoice.invoice_number = next_number(invoice.hotel, NumberKind.INVOICE)
    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = timezone.now()
    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.total = total
    invoice.balance_at_issue = folio_balance(invoice.folio)["balance"]
    invoice.save()
    return invoice


@transaction.atomic
def void_invoice(invoice, *, reason, user=None) -> Invoice:
    if not (reason or "").strip():
        raise VoidReasonRequired()
    if invoice.status == InvoiceStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    invoice.status = InvoiceStatus.VOIDED
    invoice.void_reason = reason.strip()
    invoice.voided_at = timezone.now()
    invoice.voided_by = _actor(user)
    invoice.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    return invoice


# --- Expenses ---------------------------------------------------------------


@transaction.atomic
def create_expense(hotel, *, category, description, amount, method, paid_at=None,
                   vendor_name="", reference="", notes="", currency=None, user=None) -> Expense:
    if money(amount) <= ZERO:
        raise InvalidAmount({"field": "amount", "reason": "must_be_positive"})
    actor = _actor(user)
    return Expense.objects.create(
        hotel=hotel,
        expense_number=next_number(hotel, NumberKind.EXPENSE),
        category=category,
        description=description,
        amount=money(amount),
        currency=currency or _hotel_currency(hotel),
        method=method,
        paid_at=paid_at or timezone.now(),
        vendor_name=vendor_name or "",
        reference=reference or "",
        notes=notes or "",
        created_by=actor,
        updated_by=actor,
    )


@transaction.atomic
def void_expense(expense, *, reason, user=None) -> Expense:
    if not (reason or "").strip():
        raise VoidReasonRequired()
    if expense.status == PostingStatus.VOIDED:
        raise InvalidFinanceOperation({"reason": "already_voided"})
    expense.status = PostingStatus.VOIDED
    expense.void_reason = reason.strip()
    expense.voided_at = timezone.now()
    expense.voided_by = _actor(user)
    expense.save(update_fields=["status", "void_reason", "voided_at", "voided_by", "updated_at"])
    return expense


def _hotel_currency(hotel) -> str:
    """The hotel's default currency (from HotelSettings) or USD."""
    settings_obj = getattr(hotel, "settings", None)
    if settings_obj and getattr(settings_obj, "default_currency", ""):
        return settings_obj.default_currency
    return "USD"
