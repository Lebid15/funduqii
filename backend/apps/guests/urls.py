"""Guests API URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    GuestBlockView,
    GuestDetailView,
    GuestDirectoryView,
    GuestListCreateView,
    GuestProfileView,
    GuestUnblockView,
    GuestVipView,
)

app_name = "guests"

urlpatterns = [
    path("guests/", GuestListCreateView.as_view(), name="guest-list"),
    path(
        "guests/directory/",
        GuestDirectoryView.as_view(),
        name="guest-directory",
    ),
    path("guests/<int:pk>/", GuestDetailView.as_view(), name="guest-detail"),
    path(
        "guests/<int:pk>/profile/",
        GuestProfileView.as_view(),
        name="guest-profile",
    ),
    path("guests/<int:pk>/vip/", GuestVipView.as_view(), name="guest-vip"),
    path("guests/<int:pk>/block/", GuestBlockView.as_view(), name="guest-block"),
    path(
        "guests/<int:pk>/unblock/",
        GuestUnblockView.as_view(),
        name="guest-unblock",
    ),
]
