"""Stays / front-desk API URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    ArrivalsTodayView,
    CheckInRoomsView,
    CheckInView,
    CheckOutView,
    ReverseCheckInView,
    CurrentResidentsView,
    DeparturesTodayView,
    ImmediateCheckInView,
    StayDetailView,
    StayExtendView,
    StayFolioSummaryView,
    StayListView,
    StayLogsView,
    StayMoveCandidatesView,
    StayMoveRoomView,
    StaysOverviewView,
    StayShortenView,
)

app_name = "stays"

urlpatterns = [
    path("stays/", StayListView.as_view(), name="stay-list"),
    path("stays/current/", CurrentResidentsView.as_view(), name="stay-current"),
    path("stays/overview/", StaysOverviewView.as_view(), name="stay-overview"),
    path(
        "stays/arrivals-today/",
        ArrivalsTodayView.as_view(),
        name="stay-arrivals-today",
    ),
    path(
        "stays/departures-today/",
        DeparturesTodayView.as_view(),
        name="stay-departures-today",
    ),
    path("stays/check-in/", CheckInView.as_view(), name="stay-check-in"),
    path(
        "stays/immediate-check-in/",
        ImmediateCheckInView.as_view(),
        name="stay-immediate-check-in",
    ),
    path(
        "stays/check-in-rooms/",
        CheckInRoomsView.as_view(),
        name="stay-check-in-rooms",
    ),
    path("stays/<int:pk>/", StayDetailView.as_view(), name="stay-detail"),
    path("stays/<int:pk>/check-out/", CheckOutView.as_view(), name="stay-check-out"),
    path(
        "stays/<int:pk>/reverse-check-in/",
        ReverseCheckInView.as_view(),
        name="stay-reverse-check-in",
    ),
    path("stays/<int:pk>/extend/", StayExtendView.as_view(), name="stay-extend"),
    path("stays/<int:pk>/shorten/", StayShortenView.as_view(), name="stay-shorten"),
    path(
        "stays/<int:pk>/move-room/",
        StayMoveRoomView.as_view(),
        name="stay-move-room",
    ),
    path(
        "stays/<int:pk>/move-candidates/",
        StayMoveCandidatesView.as_view(),
        name="stay-move-candidates",
    ),
    path(
        "stays/<int:pk>/folio-summary/",
        StayFolioSummaryView.as_view(),
        name="stay-folio-summary",
    ),
    path("stays/<int:pk>/logs/", StayLogsView.as_view(), name="stay-logs"),
]
