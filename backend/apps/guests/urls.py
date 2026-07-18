"""Guests API URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    GuestBlockView,
    GuestChangeLogView,
    GuestDetailView,
    GuestDirectoryView,
    GuestDocumentsView,
    GuestListView,
    GuestLookupView,
    GuestProfileView,
    GuestReservationsView,
    GuestStaysView,
    GuestUnblockView,
    GuestVipView,
)

app_name = "guests"

urlpatterns = [
    path("guests/", GuestListView.as_view(), name="guest-list"),
    path(
        "guests/directory/",
        GuestDirectoryView.as_view(),
        name="guest-directory",
    ),
    path("guests/lookup/", GuestLookupView.as_view(), name="guest-lookup"),
    path("guests/<int:pk>/", GuestDetailView.as_view(), name="guest-detail"),
    path(
        "guests/<int:pk>/profile/",
        GuestProfileView.as_view(),
        name="guest-profile",
    ),
    # GAP-1 read-only, paginated profile sub-resources (EXEC-GUESTS-CLOSURE-01
    # / W3b, Decision 11). Literal suffix segments, so none collide with
    # ``guests/<int:pk>/``.
    path(
        "guests/<int:pk>/stays/",
        GuestStaysView.as_view(),
        name="guest-stays",
    ),
    path(
        "guests/<int:pk>/reservations/",
        GuestReservationsView.as_view(),
        name="guest-reservations",
    ),
    path(
        "guests/<int:pk>/documents/",
        GuestDocumentsView.as_view(),
        name="guest-documents",
    ),
    path(
        "guests/<int:pk>/change-log/",
        GuestChangeLogView.as_view(),
        name="guest-change-log",
    ),
    path("guests/<int:pk>/vip/", GuestVipView.as_view(), name="guest-vip"),
    path("guests/<int:pk>/block/", GuestBlockView.as_view(), name="guest-block"),
    path(
        "guests/<int:pk>/unblock/",
        GuestUnblockView.as_view(),
        name="guest-unblock",
    ),
]
