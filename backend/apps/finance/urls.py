"""Finance API URLs (mounted under /api/v1/hotel/finance/)."""
from django.urls import path

from .views import (
    ChargeAdjustView,
    ChargeVoidView,
    ExpenseDetailView,
    ExpenseListCreateView,
    ExpenseReverseView,
    ExpenseVoidView,
    ExpenseVoucherView,
    FinanceOverviewView,
    FolioChargeCreateView,
    FolioAwaitingChargesView,
    FolioCloseView,
    FolioRefundView,
    FolioReopenView,
    FolioSettleView,
    FolioDetailView,
    FolioInvoiceCreateView,
    FolioListCreateView,
    FolioPaymentCreateView,
    FolioStatementView,
    FolioVoidView,
    InvoiceDetailView,
    InvoiceIssueView,
    InvoiceListView,
    InvoicePrintView,
    InvoiceVoidView,
    PaymentListView,
    PaymentReceiptView,
    PaymentReverseView,
    PaymentVoidView,
)

app_name = "finance"

urlpatterns = [
    path("finance/overview/", FinanceOverviewView.as_view(), name="overview"),
    # Folios
    path("finance/folios/", FolioListCreateView.as_view(), name="folio-list"),
    path("finance/folios/<int:pk>/", FolioDetailView.as_view(), name="folio-detail"),
    path("finance/folios/<int:pk>/close/", FolioCloseView.as_view(), name="folio-close"),
    path("finance/folios/<int:pk>/reopen/", FolioReopenView.as_view(), name="folio-reopen"),
    path(
        "finance/folios/<int:pk>/awaiting-final-charges/",
        FolioAwaitingChargesView.as_view(),
        name="folio-awaiting-charges",
    ),
    path("finance/folios/<int:pk>/settle/", FolioSettleView.as_view(), name="folio-settle"),
    path("finance/folios/<int:pk>/refund/", FolioRefundView.as_view(), name="folio-refund"),
    path("finance/folios/<int:pk>/void/", FolioVoidView.as_view(), name="folio-void"),
    path("finance/folios/<int:pk>/charges/", FolioChargeCreateView.as_view(), name="folio-charge-create"),
    path("finance/folios/<int:pk>/payments/", FolioPaymentCreateView.as_view(), name="folio-payment-create"),
    path("finance/folios/<int:pk>/invoices/", FolioInvoiceCreateView.as_view(), name="folio-invoice-create"),
    path("finance/folios/<int:pk>/statement/", FolioStatementView.as_view(), name="folio-statement"),
    # Charges
    path("finance/charges/<int:pk>/void/", ChargeVoidView.as_view(), name="charge-void"),
    path("finance/charges/<int:pk>/adjust/", ChargeAdjustView.as_view(), name="charge-adjust"),
    # Payments
    path("finance/payments/", PaymentListView.as_view(), name="payment-list"),
    path("finance/payments/<int:pk>/void/", PaymentVoidView.as_view(), name="payment-void"),
    path("finance/payments/<int:pk>/reverse/", PaymentReverseView.as_view(), name="payment-reverse"),
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
    path("finance/expenses/<int:pk>/reverse/", ExpenseReverseView.as_view(), name="expense-reverse"),
    path("finance/expenses/<int:pk>/voucher/", ExpenseVoucherView.as_view(), name="expense-voucher"),
]
