"""Guests API URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import GuestDetailView, GuestListCreateView

app_name = "guests"

urlpatterns = [
    path("guests/", GuestListCreateView.as_view(), name="guest-list"),
    path("guests/<int:pk>/", GuestDetailView.as_view(), name="guest-detail"),
]
