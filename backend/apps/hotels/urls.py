"""Hotel-side API URLs (mounted at /api/v1/hotel/)."""
from django.urls import path

from .views import (
    HotelMediaDetailView,
    HotelMediaListCreateView,
    HotelProfileView,
    HotelSettingsView,
)

app_name = "hotel"

urlpatterns = [
    path("settings/", HotelSettingsView.as_view(), name="settings"),
    path("profile/", HotelProfileView.as_view(), name="profile"),
    path("media/", HotelMediaListCreateView.as_view(), name="media-list"),
    path("media/<int:pk>/", HotelMediaDetailView.as_view(), name="media-detail"),
]
