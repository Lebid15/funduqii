"""Shifts / handover / daily-close URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    CurrentShiftView,
    DailyCloseCloseView,
    DailyCloseDetailView,
    DailyCloseListView,
    DailyClosePrepareView,
    DailyCloseStatementView,
    HandoverAcceptView,
    HandoverCancelView,
    HandoverDetailView,
    HandoverListCreateView,
    HandoverRejectView,
    HandoverSubmitView,
    HandoverVoucherView,
    ShiftCancelView,
    ShiftCloseView,
    ShiftDetailView,
    ShiftListCreateView,
    ShiftsOverviewView,
    ShiftStatementView,
    ShiftSummaryView,
)

app_name = "shifts"

urlpatterns = [
    path("shifts/overview/", ShiftsOverviewView.as_view(), name="overview"),
    path("shifts/current/", CurrentShiftView.as_view(), name="current"),
    # Handovers
    path("shifts/handovers/", HandoverListCreateView.as_view(), name="handover-list"),
    path(
        "shifts/handovers/<int:pk>/",
        HandoverDetailView.as_view(),
        name="handover-detail",
    ),
    path(
        "shifts/handovers/<int:pk>/submit/",
        HandoverSubmitView.as_view(),
        name="handover-submit",
    ),
    path(
        "shifts/handovers/<int:pk>/accept/",
        HandoverAcceptView.as_view(),
        name="handover-accept",
    ),
    path(
        "shifts/handovers/<int:pk>/reject/",
        HandoverRejectView.as_view(),
        name="handover-reject",
    ),
    path(
        "shifts/handovers/<int:pk>/cancel/",
        HandoverCancelView.as_view(),
        name="handover-cancel",
    ),
    path(
        "shifts/handovers/<int:pk>/voucher/",
        HandoverVoucherView.as_view(),
        name="handover-voucher",
    ),
    # Daily close
    path("shifts/daily-close/", DailyCloseListView.as_view(), name="daily-close-list"),
    path(
        "shifts/daily-close/prepare/",
        DailyClosePrepareView.as_view(),
        name="daily-close-prepare",
    ),
    path(
        "shifts/daily-close/close/",
        DailyCloseCloseView.as_view(),
        name="daily-close-close",
    ),
    path(
        "shifts/daily-close/<int:pk>/statement/",
        DailyCloseStatementView.as_view(),
        name="daily-close-statement",
    ),
    path(
        "shifts/daily-close/<str:business_date>/",
        DailyCloseDetailView.as_view(),
        name="daily-close-detail",
    ),
    # Shifts
    path("shifts/", ShiftListCreateView.as_view(), name="shift-list"),
    path("shifts/<int:pk>/", ShiftDetailView.as_view(), name="shift-detail"),
    path("shifts/<int:pk>/close/", ShiftCloseView.as_view(), name="shift-close"),
    path("shifts/<int:pk>/cancel/", ShiftCancelView.as_view(), name="shift-cancel"),
    path("shifts/<int:pk>/summary/", ShiftSummaryView.as_view(), name="shift-summary"),
    path(
        "shifts/<int:pk>/statement/",
        ShiftStatementView.as_view(),
        name="shift-statement",
    ),
]
