"""Report URLs (mounted under /api/v1/hotel/). All endpoints are GET-only."""
from django.urls import path

from .views import (
    DailyCloseReportDetailView,
    DailyCloseReportListView,
    FinanceReportView,
    GuestsReportView,
    OccupancyReportView,
    OperationsReportView,
    OverviewReportView,
    PaymentsExportView,
    ReservationsExportView,
    ReservationsReportView,
    ServicesReportView,
    ShiftsExportView,
    ShiftsReportView,
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
