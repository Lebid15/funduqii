"""Reservations & availability API URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    AvailabilityCalendarView,
    AvailabilityView,
    ReservationCancelView,
    ReservationConfirmView,
    ReservationDetailView,
    ReservationHoldView,
    ReservationListCreateView,
    ReservationLogsView,
    ReservationOverviewView,
)

app_name = "reservations"

urlpatterns = [
    path(
        "reservations/",
        ReservationListCreateView.as_view(),
        name="reservation-list",
    ),
    path(
        "reservations/overview/",
        ReservationOverviewView.as_view(),
        name="reservation-overview",
    ),
    path(
        "reservations/<int:pk>/",
        ReservationDetailView.as_view(),
        name="reservation-detail",
    ),
    path(
        "reservations/<int:pk>/confirm/",
        ReservationConfirmView.as_view(),
        name="reservation-confirm",
    ),
    path(
        "reservations/<int:pk>/cancel/",
        ReservationCancelView.as_view(),
        name="reservation-cancel",
    ),
    path(
        "reservations/<int:pk>/hold/",
        ReservationHoldView.as_view(),
        name="reservation-hold",
    ),
    path(
        "reservations/<int:pk>/logs/",
        ReservationLogsView.as_view(),
        name="reservation-logs",
    ),
    path("availability/", AvailabilityView.as_view(), name="availability"),
    path(
        "availability/calendar/",
        AvailabilityCalendarView.as_view(),
        name="availability-calendar",
    ),
]
