"""Finance API URLs (mounted under /api/v1/hotel/finance/)."""
from django.urls import path

from .views import (
    ChargeVoidView,
    ExpenseDetailView,
    ExpenseListCreateView,
    ExpenseVoidView,
    ExpenseVoucherView,
    FinanceOverviewView,
    FolioChargeCreateView,
    FolioCloseView,
    FolioDetailView,
    FolioInvoiceCreateView,
    FolioListCreateView,
    FolioPaymentCreateView,
    FolioVoidView,
    InvoiceDetailView,
    InvoiceIssueView,
    InvoiceListView,
    InvoicePrintView,
    InvoiceVoidView,
    PaymentListView,
    PaymentReceiptView,
    PaymentVoidView,
)

app_name = "finance"

urlpatterns = [
    path("finance/overview/", FinanceOverviewView.as_view(), name="overview"),
    # Folios
    path("finance/folios/", FolioListCreateView.as_view(), name="folio-list"),
    path("finance/folios/<int:pk>/", FolioDetailView.as_view(), name="folio-detail"),
    path("finance/folios/<int:pk>/close/", FolioCloseView.as_view(), name="folio-close"),
    path("finance/folios/<int:pk>/void/", FolioVoidView.as_view(), name="folio-void"),
    path("finance/folios/<int:pk>/charges/", FolioChargeCreateView.as_view(), name="folio-charge-create"),
    path("finance/folios/<int:pk>/payments/", FolioPaymentCreateView.as_view(), name="folio-payment-create"),
    path("finance/folios/<int:pk>/invoices/", FolioInvoiceCreateView.as_view(), name="folio-invoice-create"),
    # Charges
    path("finance/charges/<int:pk>/void/", ChargeVoidView.as_view(), name="charge-void"),
    # Payments
    path("finance/payments/", PaymentListView.as_view(), name="payment-list"),
    path("finance/payments/<int:pk>/void/", PaymentVoidView.as_view(), name="payment-void"),
    path("finance/payments/<int:pk>/receipt/", PaymentReceiptView.as_view(), name="payment-receipt"),
    # Invoices
    path("finance/invoices/", InvoiceListView.as_view(), name="invoice-list"),
    path("finance/invoices/<int:pk>/", InvoiceDetailView.as_view(), name="invoice-detail"),
    path("finance/invoices/<int:pk>/issue/", InvoiceIssueView.as_view(), name="invoice-issue"),
    path("finance/invoices/<int:pk>/void/", InvoiceVoidView.as_view(), name="invoice-void"),
    path("finance/invoices/<int:pk>/print/", InvoicePrintView.as_view(), name="invoice-print"),
    # Expenses
    path("finance/expenses/", ExpenseListCreateView.as_view(), name="expense-list"),
    path("finance/expenses/<int:pk>/", ExpenseDetailView.as_view(), name="expense-detail"),
    path("finance/expenses/<int:pk>/void/", ExpenseVoidView.as_view(), name="expense-void"),
    path("finance/expenses/<int:pk>/voucher/", ExpenseVoucherView.as_view(), name="expense-voucher"),
]
