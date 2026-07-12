"""Report URLs (mounted under /api/v1/hotel/). All endpoints are GET-only."""
from django.urls import path

from .views import (
    ComparisonsReportView,
    DailyCloseReportDetailView,
    DailyCloseReportListView,
    ExpensesReportView,
    FinanceOverviewView,
    FinanceReportView,
    FolioBalancesReportView,
    GuestsReportView,
    OccupancyReportView,
    OperationsReportView,
    OverviewReportView,
    PaymentsExportView,
    PaymentsReportView,
    ReservationsExportView,
    ReservationsReportView,
    RestaurantCafeReportView,
    RevenueReportView,
    ServicesReportView,
    ShiftsExportView,
    ShiftsReportView,
    TaxReportView,
)

app_name = "reports"

urlpatterns = [
    path("reports/overview/", OverviewReportView.as_view(), name="overview"),
    path("reports/reservations/", ReservationsReportView.as_view(), name="reservations"),
    path(
        "reports/reservations/export.csv",
        ReservationsExportView.as_view(),
        name="reservations-export",
    ),
    path("reports/occupancy/", OccupancyReportView.as_view(), name="occupancy"),
    path("reports/guests/", GuestsReportView.as_view(), name="guests"),
    path("reports/finance/", FinanceReportView.as_view(), name="finance"),
    path(
        "reports/finance/payments/export.csv",
        PaymentsExportView.as_view(),
        name="payments-export",
    ),
    # Finance reports (business_date-keyed, under reports.finance)
    path("reports/finance/overview/", FinanceOverviewView.as_view(), name="finance-overview"),
    path("reports/finance/revenue/", RevenueReportView.as_view(), name="revenue"),
    path("reports/finance/payments/", PaymentsReportView.as_view(), name="payments"),
    path("reports/finance/expenses/", ExpensesReportView.as_view(), name="expenses"),
    path("reports/finance/taxes/", TaxReportView.as_view(), name="taxes"),
    path("reports/finance/folios/", FolioBalancesReportView.as_view(), name="folio-balances"),
    path(
        "reports/finance/restaurant-cafe/",
        RestaurantCafeReportView.as_view(),
        name="restaurant-cafe",
    ),
    path("reports/finance/comparisons/", ComparisonsReportView.as_view(), name="comparisons"),
    path("reports/services/", ServicesReportView.as_view(), name="services"),
    path("reports/operations/", OperationsReportView.as_view(), name="operations"),
    path("reports/shifts/", ShiftsReportView.as_view(), name="shifts"),
    path(
        "reports/shifts/export.csv",
        ShiftsExportView.as_view(),
        name="shifts-export",
    ),
    path("reports/daily-close/", DailyCloseReportListView.as_view(), name="daily-close"),
    path(
        "reports/daily-close/<str:business_date>/",
        DailyCloseReportDetailView.as_view(),
        name="daily-close-detail",
    ),
]
