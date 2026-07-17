"""Hotel-side API URLs (mounted at /api/v1/hotel/)."""
from django.urls import path

from .subscription_views import (
    HotelAvailablePlansView,
    HotelChangeRequestCancelView,
    HotelChangeRequestListCreateView,
)
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
    # §8.4/§8.5 — hotel-initiated subscription requests.
    path(
        "subscription/plans/",
        HotelAvailablePlansView.as_view(),
        name="subscription-plans",
    ),
    path(
        "subscription/requests/",
        HotelChangeRequestListCreateView.as_view(),
        name="subscription-requests",
    ),
    path(
        "subscription/requests/<int:pk>/cancel/",
        HotelChangeRequestCancelView.as_view(),
        name="subscription-request-cancel",
    ),
]
