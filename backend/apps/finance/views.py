"""Internal finance API views (Phase 8), under /api/v1/hotel/finance/.

Scoped to the caller's hotel and guarded by ``finance.*`` / ``expenses.*``
permissions. A suspended hotel is read-only. Money mutations go through the
finance services; there is no hard delete and no external gateway.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import InvalidFinanceOperation
from apps.guests.models import Guest
from apps.rbac.permissions import HasHotelPermission
from apps.reservations.models import Reservation
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
)
from .serializers import (
    ChargeCreateSerializer,
    ExpenseSerializer,
    FolioCreateSerializer,
    FolioListSerializer,
    FolioSerializer,
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
CanInvoiceCreate = HasHotelPermission("finance.invoice_create")
CanInvoiceIssue = HasHotelPermission("finance.invoice_issue")
CanInvoiceVoid = HasHotelPermission("finance.invoice_void")

ExpView = HasHotelPermission("expenses.view")
ExpCreate = HasHotelPermission("expenses.create")
ExpUpdate = HasHotelPermission("expenses.update")
ExpVoid = HasHotelPermission("expenses.void")


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
        if stay is not None and Folio.objects.filter(
            hotel=request.hotel, stay=stay, status=FolioStatus.OPEN
        ).exists():
            raise InvalidFinanceOperation({"reason": "open_folio_exists_for_stay"})
        folio = services.create_folio(
            request.hotel,
            reservation=reservation,
            stay=stay,
            guest=guest,
            customer_name=data.get("customer_name", ""),
            currency=(data.get("currency") or None),
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
            charge_date=d.get("charge_date"),
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
            paid_at=d.get("paid_at"),
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
        if p.get("date_from"):
            qs = qs.filter(paid_at__date__gte=p["date_from"])
        if p.get("date_to"):
            qs = qs.filter(paid_at__date__lte=p["date_to"])
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
            paid_at=d.get("paid_at"),
            vendor_name=d.get("vendor_name", ""),
            reference=d.get("reference", ""),
            notes=d.get("notes", ""),
            currency=(d.get("currency") or None),
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
        _guard_write(request)
        expense = self.get_object()
        if expense.status != PostingStatus.POSTED:
            raise InvalidFinanceOperation({"reason": "not_editable"})
        s = ExpenseSerializer(expense, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save(updated_by=request.user)
        return Response(ExpenseSerializer(expense).data)


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
        today = timezone.localdate()
        open_folios = Folio.objects.filter(hotel=hotel, status=FolioStatus.OPEN)
        outstanding = ZERO
        unpaid = 0
        for folio in open_folios.prefetch_related("charges", "payments"):
            bal = services.folio_balance(folio)["balance"]
            outstanding += bal
            if bal > ZERO:
                unpaid += 1
        payments_today = Payment.objects.filter(
            hotel=hotel, status=PostingStatus.POSTED, paid_at__date=today
        ).aggregate(t=Sum("amount"))["t"] or ZERO
        expenses_today = Expense.objects.filter(
            hotel=hotel, status=PostingStatus.POSTED, paid_at__date=today
        ).aggregate(t=Sum("amount"))["t"] or ZERO
        return Response(
            {
                "open_folios": open_folios.count(),
                "outstanding_balance": str(services.money(outstanding)),
                "unpaid_folios": unpaid,
                "payments_today": str(services.money(payments_today)),
                "expenses_today": str(services.money(expenses_today)),
                "net_today": str(services.money(payments_today - expenses_today)),
                "issued_invoices": Invoice.objects.filter(
                    hotel=hotel, status=InvoiceStatus.ISSUED
                ).count(),
                "currency": _hotel_header(hotel)["currency"],
            }
        )
