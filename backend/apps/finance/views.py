"""Internal finance API views (Phase 8), under /api/v1/hotel/finance/.

Scoped to the caller's hotel and guarded by ``finance.*`` / ``expenses.*``
permissions. A suspended hotel is read-only. Money mutations go through the
finance services; there is no hard delete and no external gateway.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import FolioClosed, InvalidFinanceOperation
from apps.guests.models import Guest
from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.reservations.models import Reservation
from apps.shifts.services import get_business_date
from apps.stays.models import Stay
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .constants import SERVICE_LINE_SOURCES
from .models import (
    Expense,
    ExpenseType,
    Folio,
    FolioCharge,
    FolioStatus,
    Invoice,
    InvoiceStatus,
    Payment,
    PostingStatus,
    RefundableInsurance,
)
from .serializers import (
    ChargeCreateSerializer,
    ExpenseCreateSerializer,
    ExpenseSerializer,
    ExpenseTypeSerializer,
    ExpenseTypeWriteSerializer,
    ExpenseUpdateSerializer,
    FolioCreateSerializer,
    FolioListSerializer,
    FolioSerializer,
    InsuranceSerializer,
    InvoiceCreateSerializer,
    InvoiceSerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    VoidSerializer,
)

ZERO = Decimal("0.00")

CanView = HasHotelPermission("finance.view")
CanCreate = HasHotelPermission("finance.create")
CanUpdate = HasHotelPermission("finance.update")
CanClose = HasHotelPermission("finance.close")
CanVoid = HasHotelPermission("finance.void")
CanChargeCreate = HasHotelPermission("finance.charge_create")
CanChargeVoid = HasHotelPermission("finance.charge_void")
CanPaymentCreate = HasHotelPermission("finance.payment_create")
CanPaymentVoid = HasHotelPermission("finance.payment_void")
CanReopen = HasHotelPermission("finance.reopen")
CanRefund = HasHotelPermission("finance.refund")
CanInsuranceManage = HasHotelPermission("finance.insurance_manage")
CanAdjust = HasHotelPermission("finance.adjust")
CanPaymentReverse = HasHotelPermission("finance.payment_reverse")
CanInvoiceCreate = HasHotelPermission("finance.invoice_create")
CanInvoiceIssue = HasHotelPermission("finance.invoice_issue")
CanInvoiceVoid = HasHotelPermission("finance.invoice_void")

ExpView = HasHotelPermission("expenses.view")
ExpCreate = HasHotelPermission("expenses.create")
ExpUpdate = HasHotelPermission("expenses.update")
ExpVoid = HasHotelPermission("expenses.void")
ExpReverse = HasHotelPermission("expenses.reverse")
ExpManageTypes = HasHotelPermission("expenses.manage_types")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _hotel_header(hotel) -> dict:
    s = getattr(hotel, "settings", None)
    return {
        "hotel_name": (getattr(s, "display_name", "") or hotel.name),
        "currency": getattr(s, "default_currency", "") or "USD",
        "phone": getattr(s, "phone", "") or "",
        "address": getattr(s, "address_line", "") or "",
    }


def _get(model, request, pk):
    return generics.get_object_or_404(model, pk=pk, hotel=request.hotel)


def _statement_line_items(folio) -> list:
    """P7 — itemize a folio's POSTED charges for the departure statement.

    Reads only the already-prefetched ``folio.charges`` (no extra query) and
    projects each posted line with its origin, quantity, unit price, tax, and
    the staff member who posted it (NAME only — see C5 below).
    ``is_service_line`` uses the central ``SERVICE_LINE_SOURCES`` allowlist so
    guest extra-service and restaurant/café lines are flagged consistently.
    """
    items = []
    for c in folio.charges.all():
        if c.status != PostingStatus.POSTED:
            continue
        staff = None
        if c.created_by_id:
            # C5 — NAME ONLY. This document is printed and handed to the guest;
            # a staff member with no full_name must degrade to null, never to
            # their login email address.
            staff = c.created_by.full_name or None
        items.append(
            {
                "id": c.id,
                "charge_number": c.charge_number,
                "type": c.type,
                "source": c.source,
                "is_service_line": c.source in SERVICE_LINE_SOURCES,
                "description": c.description,
                "quantity": str(c.quantity),
                "unit_price": str(c.unit_amount),
                "tax_rate": str(c.tax_rate),
                "tax_amount": str(c.tax_amount),
                "total_amount": str(c.total_amount),
                "charge_date": str(c.charge_date),
                "staff": staff,
                "service_name_snapshot": c.service_name_snapshot,
                "source_reference": c.source_reference,
            }
        )
    return items


def _opt_decimal(data, field):
    """Validate an optional money field: None/'' → None; a malformed value → a
    400 (not a 500 from Decimal() deep in the service). Returns the raw string
    so the service keeps its own quantization/FX handling."""
    value = data.get(field)
    if value is None or value == "":
        return None
    try:
        Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "must_be_a_number"})
    return str(value)


def _req_decimal(data, field):
    """Same as :func:`_opt_decimal` but the field is mandatory (400 if absent)."""
    value = _opt_decimal(data, field)
    if value is None:
        raise ValidationError({field: "required"})
    return value


# --- Folios -----------------------------------------------------------------


class FolioListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [CanCreate()] if self.request.method == "POST" else [CanView()]

    def get_serializer_class(self):
        return FolioListSerializer

    def get_queryset(self):
        qs = Folio.objects.filter(hotel=self.request.hotel).select_related(
            "reservation", "guest"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in FolioStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("reservation") and str(p["reservation"]).isdigit():
            qs = qs.filter(reservation_id=int(p["reservation"]))
        if p.get("stay") and str(p["stay"]).isdigit():
            qs = qs.filter(stay_id=int(p["stay"]))
        search = p.get("search")
        if search:
            qs = (
                qs.filter(folio_number__icontains=search)
                | qs.filter(customer_name__icontains=search)
                | qs.filter(guest__full_name__icontains=search)
            )
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = FolioCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reservation = _get(Reservation, request, data["reservation"]) if data.get("reservation") else None
        stay = _get(Stay, request, data["stay"]) if data.get("stay") else None
        guest = _get(Guest, request, data["guest"]) if data.get("guest") else None
        # Duplicate-open-folio and reservation-without-stay guards live in the
        # central service (folio closure round) — nothing is checked here.
        folio = services.create_folio(
            request.hotel,
            reservation=reservation,
            stay=stay,
            guest=guest,
            customer_name=data.get("customer_name", ""),
            notes=data.get("notes", ""),
            user=request.user,
        )
        return Response(FolioSerializer(folio).data, status=status.HTTP_201_CREATED)


class FolioDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = FolioSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [CanUpdate()] if self.request.method == "PATCH" else [CanView()]

    def get_queryset(self):
        # ``charges__created_by`` is prefetched so the P7 DTO enrichment
        # (created_by / staff name per charge line) does not add an N+1 on this
        # single-folio detail response.
        return Folio.objects.filter(hotel=self.request.hotel).prefetch_related(
            "charges__created_by", "payments"
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        folio = self.get_object()
        # Folio closure round: a closed/voided folio is fully read-only —
        # even its free-text notes.
        if folio.status != FolioStatus.OPEN:
            raise FolioClosed({"folio": folio.id, "status": folio.status})
        # Only free-text notes may be patched on a folio.
        notes = request.data.get("notes")
        if notes is not None:
            folio.notes = notes
            folio.updated_by = request.user
            folio.save(update_fields=["notes", "updated_by", "updated_at"])
        return Response(FolioSerializer(folio).data)


class FolioCloseView(APIView):
    def get_permissions(self):
        return [CanClose()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        services.close_folio(folio, user=request.user)
        folio.refresh_from_db()
        return Response(FolioSerializer(folio).data)


class FolioReopenView(APIView):
    """Reopen a CLOSED folio (§42) — POST folios/<id>/reopen/ with a mandatory
    ``reason``. Requires ``finance.reopen``."""

    def get_permissions(self):
        return [CanReopen()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        services.reopen_folio(
            folio, reason=(request.data.get("reason") or ""), user=request.user
        )
        folio.refresh_from_db()
        return Response(FolioSerializer(folio).data)


class FolioAwaitingChargesView(APIView):
    """Toggle the folio's awaiting-final-charges flag (§32) — POST
    folios/<id>/awaiting-final-charges/ with ``awaiting`` (bool) + optional
    ``note``. Requires ``finance.update``."""

    def get_permissions(self):
        return [CanUpdate()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        services.set_folio_awaiting_final_charges(
            folio,
            awaiting=bool(request.data.get("awaiting")),
            note=(request.data.get("note") or ""),
            user=request.user,
        )
        folio.refresh_from_db()
        return Response(FolioSerializer(folio).data)


class FolioSettleView(APIView):
    """Settle a folio balance with a payment (§34), multi-currency aware — POST
    folios/<id>/settle/. Requires ``finance.payment_create``; a manual FX rate on
    a foreign-currency payment additionally requires ``exchange_rate.override``."""

    def get_permissions(self):
        return [CanPaymentCreate()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        data = request.data
        currency = (data.get("currency") or "").strip().upper()
        if (
            currency
            and currency != folio.currency.upper()
            and data.get("exchange_rate") is not None
            and not has_hotel_permission(
                request.user, request.hotel, "exchange_rate.override"
            )
        ):
            raise PermissionDenied()
        services.record_folio_settlement(
            folio,
            method=data.get("method", "cash"),
            amount=_opt_decimal(data, "amount"),
            currency=(currency or None),
            original_amount=_opt_decimal(data, "original_amount"),
            exchange_rate=_opt_decimal(data, "exchange_rate"),
            rate_basis=data.get("rate_basis", ""),
            payer_name=data.get("payer_name", ""),
            reference=data.get("reference", ""),
            notes=data.get("notes", ""),
            user=request.user,
        )
        folio.refresh_from_db()
        return Response(FolioSerializer(folio).data)


class FolioRefundView(APIView):
    """Refund a folio credit balance to the guest (§37) — POST folios/<id>/refund/
    with a mandatory ``reason`` (+ optional ``amount``/``method``). Requires
    ``finance.refund``."""

    def get_permissions(self):
        return [CanRefund()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        services.refund_folio_credit(
            folio,
            amount=_opt_decimal(request.data, "amount"),
            reason=(request.data.get("reason") or ""),
            method=request.data.get("method"),
            user=request.user,
        )
        folio.refresh_from_db()
        return Response(FolioSerializer(folio).data)


class FolioVoidView(APIView):
    def get_permissions(self):
        return [CanVoid()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.void_folio(folio, reason=s.validated_data["reason"], user=request.user)
        folio.refresh_from_db()
        return Response(FolioSerializer(folio).data)


# --- Charges ----------------------------------------------------------------


class FolioChargeCreateView(APIView):
    def get_permissions(self):
        return [CanChargeCreate()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        s = ChargeCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        services.add_charge(
            folio,
            charge_type=d["type"],
            description=d["description"],
            quantity=d["quantity"],
            unit_amount=d["unit_amount"],
            tax_rate=d.get("tax_rate", ZERO),
            user=request.user,
        )
        folio.refresh_from_db()
        return Response(FolioSerializer(folio).data, status=status.HTTP_201_CREATED)


def _void_ack(charge) -> dict:
    """S2 — the money-SAFE acknowledgement for a caller who may VOID a charge but
    may not READ the folio.

    Carries ONLY the outcome of the caller's own action: which charge, its new
    status, the reason, and who voided it when. Deliberately omits the folio,
    its balance/total_charges/total_payments, the payments[] block (receipt
    numbers, amounts, methods, payer names, staff emails) and every unrelated
    charge on the folio."""
    return {
        "id": charge.id,
        "charge_number": charge.charge_number,
        "status": charge.status,
        "void_reason": charge.void_reason or "",
        "voided_by": getattr(charge.voided_by, "full_name", None),
        "voided_at": charge.voided_at.isoformat() if charge.voided_at else None,
    }


class ChargeVoidView(APIView):
    """POST charges/{id}/void/ — gated on ``finance.charge_void`` (UNCHANGED: who
    may void is exactly who could before).

    The RESPONSE BODY is separately gated on ``finance.view``. ``finance.charge_void``
    is an operational correction right and is deliberately held by personas
    (e.g. the guest-folio surface) that are NOT allowed to see folio money; before
    this fix the endpoint returned the FULL ``FolioSerializer`` — balance, totals,
    every payment with its receipt number/method/payer, and every unrelated charge
    — making it the easiest way to recover exactly the data the guest-folio
    surface omits by design. A caller WITH ``finance.view`` still receives the
    identical full body, so the finance UI is untouched."""

    def get_permissions(self):
        return [CanChargeVoid()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        charge = _get(FolioCharge, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.void_charge(charge, reason=s.validated_data["reason"], user=request.user)
        if not has_hotel_permission(request.user, request.hotel, "finance.view"):
            charge.refresh_from_db()
            return Response(_void_ack(charge))
        return Response(FolioSerializer(charge.folio).data)


class ChargeAdjustView(APIView):
    """Full counter-posting for a charge whose void window has closed."""

    def get_permissions(self):
        return [CanAdjust()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        charge = _get(FolioCharge, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.adjust_charge(charge, reason=s.validated_data["reason"], user=request.user)
        return Response(FolioSerializer(charge.folio).data, status=status.HTTP_201_CREATED)


# --- Payments ---------------------------------------------------------------


class FolioPaymentCreateView(APIView):
    def get_permissions(self):
        return [CanPaymentCreate()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        s = PaymentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        payment = services.record_payment(
            folio,
            amount=d["amount"],
            method=d["method"],
            payer_name=d.get("payer_name", ""),
            reference=d.get("reference", ""),
            notes=d.get("notes", ""),
            user=request.user,
        )
        return Response(
            {"folio": FolioSerializer(folio).data, "payment": PaymentSerializer(payment).data},
            status=status.HTTP_201_CREATED,
        )


class PaymentListView(generics.ListAPIView):
    serializer_class = PaymentSerializer

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        qs = Payment.objects.filter(hotel=self.request.hotel).select_related("folio")
        p = self.request.query_params
        if p.get("status") in {c for c, _ in PostingStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("method"):
            qs = qs.filter(method=p["method"])
        if p.get("folio") and str(p["folio"]).isdigit():
            qs = qs.filter(folio_id=int(p["folio"]))
        if p.get("date_from"):
            qs = qs.filter(paid_at__date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(paid_at__date__lte=p["date_to"])
        return qs


class PaymentVoidView(APIView):
    def get_permissions(self):
        return [CanPaymentVoid()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        payment = _get(Payment, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.void_payment(payment, reason=s.validated_data["reason"], user=request.user)
        payment.refresh_from_db()
        return Response(PaymentSerializer(payment).data)


class PaymentReverseView(APIView):
    """Full counter-payment for a payment whose void window has closed."""

    def get_permissions(self):
        return [CanPaymentReverse()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        payment = _get(Payment, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reversal = services.reverse_payment(
            payment, reason=s.validated_data["reason"], user=request.user
        )
        return Response(
            {
                "folio": FolioSerializer(payment.folio).data,
                "payment": PaymentSerializer(reversal).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentReceiptView(APIView):
    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        payment = _get(Payment, request, pk)
        return Response(
            {
                "document": "receipt",
                "hotel": _hotel_header(request.hotel),
                "payment": PaymentSerializer(payment).data,
            }
        )


class FolioStatementView(APIView):
    """The operational folio statement (print-friendly JSON, same pattern as
    the receipt/invoice documents). NOT a tax invoice. Works for closed and
    voided folios too — they are reprintable, never editable."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        folio = generics.get_object_or_404(
            Folio.objects.select_related(
                "reservation", "guest", "stay", "stay__room"
            ).prefetch_related(
                "charges__adjusts", "charges__created_by", "payments__reverses"
            ),
            pk=pk,
            hotel=request.hotel,
        )
        stay = folio.stay
        return Response(
            {
                "document": "statement",
                "hotel": _hotel_header(request.hotel),
                "folio": FolioSerializer(folio).data,
                # P7 — an itemized bill of the POSTED charge lines (source, qty,
                # unit price, tax, and the staff who posted each). Restaurant /
                # café (``service_order``) and guest extra-service
                # (``guest_extra_service``) lines therefore appear here as
                # first-class rows. This is additive metadata over the existing
                # ``folio.charges`` — the departure page / checkout cycle and the
                # final print are unchanged.
                "line_items": _statement_line_items(folio),
                "stay": (
                    {
                        "id": stay.id,
                        "room_number": stay.room.number,
                        "planned_check_in_date": str(stay.planned_check_in_date),
                        "planned_check_out_date": str(stay.planned_check_out_date),
                    }
                    if stay
                    else None
                ),
            }
        )


# --- Invoices ---------------------------------------------------------------


class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceSerializer

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        qs = Invoice.objects.filter(hotel=self.request.hotel).prefetch_related("lines")
        p = self.request.query_params
        if p.get("status") in {c for c, _ in InvoiceStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("date_from"):
            qs = qs.filter(issued_at__date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(issued_at__date__lte=p["date_to"])
        search = p.get("search")
        if search:
            qs = qs.filter(invoice_number__icontains=search) | qs.filter(
                customer_name__icontains=search
            )
        return qs.distinct()


class FolioInvoiceCreateView(APIView):
    def get_permissions(self):
        return [CanInvoiceCreate()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        folio = _get(Folio, request, pk)
        s = InvoiceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        invoice = services.create_invoice(
            folio,
            due_date=d.get("due_date"),
            customer_name=d.get("customer_name", ""),
            customer_phone=d.get("customer_phone", ""),
            notes=d.get("notes", ""),
            user=request.user,
        )
        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)


class InvoiceDetailView(generics.RetrieveAPIView):
    serializer_class = InvoiceSerializer

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        return Invoice.objects.filter(hotel=self.request.hotel).prefetch_related("lines")


class InvoiceIssueView(APIView):
    def get_permissions(self):
        return [CanInvoiceIssue()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        invoice = _get(Invoice, request, pk)
        services.issue_invoice(invoice, user=request.user)
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data)


class InvoiceVoidView(APIView):
    def get_permissions(self):
        return [CanInvoiceVoid()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        invoice = _get(Invoice, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.void_invoice(invoice, reason=s.validated_data["reason"], user=request.user)
        invoice.refresh_from_db()
        return Response(InvoiceSerializer(invoice).data)


class InvoicePrintView(APIView):
    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        invoice = _get(Invoice, request, pk)
        return Response(
            {
                "document": "invoice",
                "hotel": _hotel_header(request.hotel),
                "invoice": InvoiceSerializer(invoice).data,
            }
        )


# --- Expenses ---------------------------------------------------------------


def _expense_ack(expense) -> dict:
    """The minimal, non-leaking acknowledgement for a WRITE action."""
    return {
        "id": expense.id,
        "expense_number": expense.expense_number,
        "status": expense.status,
        "voided_at": expense.voided_at,
    }


def _expense_write_response(request: Request, expense) -> dict:
    """Response body for a write action (edit / corrective movement).

    SEC: a WRITE permission must never widen READ access (owner §7). Only a
    caller who also holds ``expenses.view`` receives the full voucher; everyone
    else gets the minimal ack — otherwise ``expenses.update``-only or
    ``expenses.reverse``-only staff could read records they cannot GET.
    """
    if has_hotel_permission(request.user, request.hotel, "expenses.view"):
        return ExpenseSerializer(expense).data
    return _expense_ack(expense)


class ExpenseListCreateView(generics.ListCreateAPIView):
    serializer_class = ExpenseSerializer

    def get_permissions(self):
        return [ExpCreate()] if self.request.method == "POST" else [ExpView()]

    def get_queryset(self):
        qs = Expense.objects.filter(hotel=self.request.hotel).select_related(
            "expense_type", "shift"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in PostingStatus.choices}:
            qs = qs.filter(status=p["status"])
        # EXPENSES-CLOSURE: filter by the manageable type (legacy ``category``
        # filter retained as a fallback for pre-migration rows / callers).
        if p.get("expense_type"):
            # A non-numeric filter must be a clean empty result, never a 500.
            try:
                qs = qs.filter(expense_type_id=int(p["expense_type"]))
            except (TypeError, ValueError):
                return qs.none()
        if p.get("category"):
            qs = qs.filter(category=p["category"])
        if p.get("method"):
            qs = qs.filter(method=p["method"])
        # Expenses closure: date filters run on the BUSINESS date (legacy
        # rows without one fall back to their paid_at calendar date).
        if p.get("date_from"):
            qs = qs.filter(
                Q(business_date__gte=p["date_from"])
                | Q(business_date__isnull=True, paid_at__date__gte=p["date_from"])
            )
        if p.get("date_to"):
            qs = qs.filter(
                Q(business_date__lte=p["date_to"])
                | Q(business_date__isnull=True, paid_at__date__lte=p["date_to"])
            )
        search = p.get("search")
        if search:
            qs = (
                qs.filter(description__icontains=search)
                | qs.filter(expense_number__icontains=search)
                | qs.filter(vendor_name__icontains=search)
                | qs.filter(reference__icontains=search)
            )
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        s = ExpenseCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        # Server-derived fingerprint over the SALIENT inputs — a replayed
        # idempotency key with a matching fingerprint returns the same voucher;
        # a different payload for the same key is a 409 (never a double post).
        fingerprint = services.build_expense_fingerprint(
            hotel_id=request.hotel.id,
            expense_type_id=d["expense_type"],
            description=d["description"],
            amount=d.get("amount"),
            method=d["method"],
            currency=d.get("currency", ""),
            original_amount=d.get("original_amount"),
            exchange_rate=d.get("exchange_rate"),
            rate_basis=d.get("rate_basis", ""),
            notes=d.get("notes", ""),
        )
        expense = services.create_expense(
            request.hotel,
            expense_type=d["expense_type"],
            description=d["description"],
            amount=d.get("amount"),
            method=d["method"],
            currency=d.get("currency", ""),
            original_amount=d.get("original_amount"),
            exchange_rate=d.get("exchange_rate"),
            rate_basis=d.get("rate_basis", ""),
            notes=d.get("notes", ""),
            idempotency_key=d.get("idempotency_key", ""),
            request_fingerprint=fingerprint,
            user=request.user,
        )
        # SEC: on an idempotent REPLAY this returns an EXISTING voucher, which
        # may carry fields the caller never supplied — so it is gated the same
        # way as the other write responses.
        return Response(
            _expense_write_response(request, expense), status=status.HTTP_201_CREATED
        )


class ExpenseDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ExpenseSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [ExpUpdate()] if self.request.method == "PATCH" else [ExpView()]

    def get_queryset(self):
        return Expense.objects.filter(hotel=self.request.hotel).select_related(
            "expense_type", "shift"
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        # EXPENSES-CLOSURE: atomic financial edit (reverse-old-then-apply-new,
        # inherent in the derived-sum model) inside the voucher's own open
        # business date — through the central service.
        _guard_write(request)
        expense = self.get_object()
        s = ExpenseUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        expense = services.update_expense(expense, user=request.user, **s.validated_data)
        # SEC: an `expenses.update`-only caller must NOT read the voucher (an
        # empty PATCH would otherwise be a silent `expenses.view` bypass).
        return Response(_expense_write_response(request, expense))


class ExpenseReverseView(APIView):
    """Full corrective counter-voucher for an expense whose void window has
    closed (owner: a distinct 'corrective movement', never an auto void→reverse
    fallback)."""

    def get_permissions(self):
        return [ExpReverse()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        expense = _get(Expense, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reversal = services.reverse_expense(
            expense, reason=s.validated_data["reason"], user=request.user
        )
        # SEC: the counter-voucher MIRRORS the original (amount, vendor,
        # reference, FX), so returning it in full would disclose the original to
        # an `expenses.reverse`-only caller (owner §7).
        return Response(
            _expense_write_response(request, reversal), status=status.HTTP_201_CREATED
        )


class ExpenseVoidView(APIView):
    def get_permissions(self):
        return [ExpVoid()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        expense = _get(Expense, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.void_expense(expense, reason=s.validated_data["reason"], user=request.user)
        expense.refresh_from_db()
        # Hardened (S3): a caller with expenses.void but NOT expenses.view must
        # not read the full voucher — return a minimal ack only.
        return Response(
            {
                "id": expense.id,
                "expense_number": expense.expense_number,
                "status": expense.status,
                "voided_at": expense.voided_at,
            }
        )


class ExpenseMetaView(APIView):
    """Base + accepted currencies for the expense form, gated on
    ``expenses.view`` so the multi-currency entry does not require the separate
    ``settings.view`` permission."""

    def get_permissions(self):
        return [ExpView()]

    def get(self, request: Request) -> Response:
        return Response(services.expense_currency_options(request.hotel))


class ExpenseVoucherView(APIView):
    def get_permissions(self):
        return [ExpView()]

    def get(self, request: Request, pk: int) -> Response:
        expense = _get(Expense, request, pk)
        return Response(
            {
                "document": "voucher",
                "hotel": _hotel_header(request.hotel),
                "expense": ExpenseSerializer(expense).data,
            }
        )


# --- Expense types (manageable per-hotel categories) ------------------------


class ExpenseTypeListCreateView(generics.ListCreateAPIView):
    serializer_class = ExpenseTypeSerializer

    def get_permissions(self):
        return [ExpManageTypes()] if self.request.method == "POST" else [ExpView()]

    def get_queryset(self):
        qs = ExpenseType.objects.filter(hotel=self.request.hotel)
        # The create-form dropdown (expenses.view/create) only ever sees ACTIVE
        # types. Inactive types surface ONLY to the management tab, i.e. a caller
        # holding expenses.manage_types who explicitly asks (``?all=1``).
        wants_all = self.request.query_params.get("all") in {"1", "true", "True"}
        if wants_all and has_hotel_permission(
            self.request.user, self.request.hotel, "expenses.manage_types"
        ):
            return qs
        return qs.filter(is_active=True)

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        s = ExpenseTypeWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        etype = services.create_expense_type(
            request.hotel, name=s.validated_data.get("name"), user=request.user
        )
        return Response(ExpenseTypeSerializer(etype).data, status=status.HTTP_201_CREATED)


class ExpenseTypeDetailView(APIView):
    """Rename / (de)activate a type — never a hard delete."""

    def get_permissions(self):
        return [ExpManageTypes()]

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        etype = _get(ExpenseType, request, pk)
        s = ExpenseTypeWriteSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        etype = services.update_expense_type(
            etype,
            name=s.validated_data.get("name"),
            is_active=s.validated_data.get("is_active"),
            user=request.user,
        )
        return Response(ExpenseTypeSerializer(etype).data)


# --- Overview ---------------------------------------------------------------


class FinanceOverviewView(APIView):
    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        hotel = request.hotel
        # Folio closure round: "today" is the HOTEL business date, and money
        # is never summed across currencies — legacy foreign-currency folios
        # are counted and flagged separately instead.
        today = get_business_date(hotel)
        hotel_currency = _hotel_header(hotel)["currency"]
        open_folios = Folio.objects.filter(hotel=hotel, status=FolioStatus.OPEN)
        # S1 — aggregate the open-folio balances in the DB (constant query count,
        # no per-folio loop / N+1) REUSING the exact ``folio_balance`` definition
        # so the overview can never drift from the per-folio number. Currency is
        # kept separate: only base-currency folios feed ``outstanding``/``unpaid``;
        # foreign-currency folios are counted + listed, never summed in.
        agg = services.aggregate_open_folio_balances(
            open_folios, base_currency=hotel_currency
        )
        outstanding = agg["outstanding"]
        unpaid = agg["unpaid"]
        foreign_count = agg["foreign_count"]
        foreign_currencies = agg["foreign_currencies"]
        payments_today = Payment.objects.filter(
            Q(business_date=today) | Q(business_date__isnull=True, paid_at__date=today),
            hotel=hotel,
            status=PostingStatus.POSTED,
        ).aggregate(t=Sum("amount"))["t"] or ZERO
        expenses_today = Expense.objects.filter(
            Q(business_date=today) | Q(business_date__isnull=True, paid_at__date=today),
            hotel=hotel,
            status=PostingStatus.POSTED,
        ).aggregate(t=Sum("amount"))["t"] or ZERO
        return Response(
            {
                "open_folios": open_folios.count(),
                "outstanding_balance": str(services.money(outstanding)),
                "unpaid_folios": unpaid,
                "foreign_currency_folios": {
                    "count": foreign_count,
                    "currencies": foreign_currencies,
                },
                "payments_today": str(services.money(payments_today)),
                "expenses_today": str(services.money(expenses_today)),
                "net_today": str(services.money(payments_today - expenses_today)),
                "issued_invoices": Invoice.objects.filter(
                    hotel=hotel, status=InvoiceStatus.ISSUED
                ).count(),
                "currency": hotel_currency,
            }
        )


# --- Refundable insurance (STAYS §35) ---------------------------------------


class InsuranceListCreateView(APIView):
    """GET finance/insurances/?stay=&reservation= (finance.view) — list held
    insurances; POST records one (finance.insurance_manage)."""

    def get_permissions(self):
        return [CanView()] if self.request.method == "GET" else [CanInsuranceManage()]

    def get(self, request: Request) -> Response:
        qs = RefundableInsurance.objects.filter(hotel=request.hotel)
        stay = request.query_params.get("stay")
        reservation = request.query_params.get("reservation")
        if stay and str(stay).isdigit():
            qs = qs.filter(stay_id=stay)
        if reservation and str(reservation).isdigit():
            qs = qs.filter(reservation_id=reservation)
        return Response(InsuranceSerializer(qs, many=True).data)

    def post(self, request: Request) -> Response:
        _guard_write(request)
        data = request.data
        reservation = stay = None
        if data.get("reservation"):
            from apps.reservations.models import Reservation

            reservation = generics.get_object_or_404(
                Reservation, pk=data["reservation"], hotel=request.hotel
            )
        if data.get("stay"):
            from apps.stays.models import Stay

            stay = generics.get_object_or_404(
                Stay, pk=data["stay"], hotel=request.hotel
            )
        ins = services.record_insurance(
            hotel=request.hotel,
            amount=_req_decimal(data, "amount"),
            currency=data.get("currency"),
            method=data.get("method"),
            reservation=reservation,
            stay=stay,
            reference=data.get("reference", ""),
            notes=data.get("notes", ""),
            user=request.user,
        )
        return Response(
            InsuranceSerializer(ins).data, status=status.HTTP_201_CREATED
        )


class InsuranceRefundView(APIView):
    """POST finance/insurances/<id>/refund/ (finance.insurance_manage) — refund
    part/all held insurance to the guest."""

    def get_permissions(self):
        return [CanInsuranceManage()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        ins = _get(RefundableInsurance, request, pk)
        services.refund_insurance(
            ins,
            amount=_opt_decimal(request.data, "amount"),
            reason=(request.data.get("reason") or ""),
            user=request.user,
        )
        ins.refresh_from_db()
        return Response(InsuranceSerializer(ins).data)


class InsuranceDeductView(APIView):
    """POST finance/insurances/<id>/deduct/ (finance.insurance_manage) — deduct a
    documented portion (reason required); posts the deducted portion to the folio."""

    def get_permissions(self):
        return [CanInsuranceManage()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        ins = _get(RefundableInsurance, request, pk)
        services.deduct_insurance(
            ins,
            amount=_req_decimal(request.data, "amount"),
            reason=(request.data.get("reason") or ""),
            user=request.user,
        )
        ins.refresh_from_db()
        return Response(InsuranceSerializer(ins).data)
