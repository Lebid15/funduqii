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
from .models import (
    Expense,
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
    ExpenseSerializer,
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
        return Folio.objects.filter(hotel=self.request.hotel).prefetch_related(
            "charges", "payments"
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


class ChargeVoidView(APIView):
    def get_permissions(self):
        return [CanChargeVoid()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        charge = _get(FolioCharge, request, pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.void_charge(charge, reason=s.validated_data["reason"], user=request.user)
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
            ).prefetch_related("charges__adjusts", "payments__reverses"),
            pk=pk,
            hotel=request.hotel,
        )
        stay = folio.stay
        return Response(
            {
                "document": "statement",
                "hotel": _hotel_header(request.hotel),
                "folio": FolioSerializer(folio).data,
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


class ExpenseListCreateView(generics.ListCreateAPIView):
    serializer_class = ExpenseSerializer

    def get_permissions(self):
        return [ExpCreate()] if self.request.method == "POST" else [ExpView()]

    def get_queryset(self):
        qs = Expense.objects.filter(hotel=self.request.hotel)
        p = self.request.query_params
        if p.get("status") in {c for c, _ in PostingStatus.choices}:
            qs = qs.filter(status=p["status"])
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
                qs.filter(vendor_name__icontains=search)
                | qs.filter(description__icontains=search)
                | qs.filter(reference__icontains=search)
                | qs.filter(expense_number__icontains=search)
            )
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        s = ExpenseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        expense = services.create_expense(
            request.hotel,
            category=d.get("category", "other"),
            description=d["description"],
            amount=d["amount"],
            method=d.get("method", "cash"),
            vendor_name=d.get("vendor_name", ""),
            reference=d.get("reference", ""),
            notes=d.get("notes", ""),
            user=request.user,
        )
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)


class ExpenseDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ExpenseSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [ExpUpdate()] if self.request.method == "PATCH" else [ExpView()]

    def get_queryset(self):
        return Expense.objects.filter(hotel=self.request.hotel)

    def update(self, request: Request, *args, **kwargs) -> Response:
        # Expenses closure (P0 fix): only the DESCRIPTIVE fields, only inside
        # the voucher's own open business date — through the central service.
        _guard_write(request)
        expense = self.get_object()
        s = ExpenseUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        expense = services.update_expense(expense, user=request.user, **s.validated_data)
        return Response(ExpenseSerializer(expense).data)


class ExpenseReverseView(APIView):
    """Full counter-voucher for an expense whose void window has closed."""

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
        return Response(ExpenseSerializer(reversal).data, status=status.HTTP_201_CREATED)


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
        return Response(ExpenseSerializer(expense).data)


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
        outstanding = ZERO
        unpaid = 0
        foreign_count = 0
        foreign_currencies = set()
        for folio in open_folios.prefetch_related("charges", "payments"):
            if folio.currency != hotel_currency:
                foreign_count += 1
                foreign_currencies.add(folio.currency)
                continue
            bal = services.folio_balance(folio)["balance"]
            outstanding += bal
            if bal > ZERO:
                unpaid += 1
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
                    "currencies": sorted(foreign_currencies),
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
