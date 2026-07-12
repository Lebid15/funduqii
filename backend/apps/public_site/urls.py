"""Public website URLs (mounted under /api/v1/public/). Anonymous + throttled."""
from django.urls import path

from .views import (
    PublicAvailabilityView,
    PublicBookingCancelRequestView,
    PublicBookingCreateView,
    PublicBookingManageView,
    PublicHotelDetailView,
    PublicHotelListView,
    PublicPlansView,
    PublicSiteSettingsView,
)

app_name = "public_site"

urlpatterns = [
    path(
        "site-settings/",
        PublicSiteSettingsView.as_view(),
        name="site-settings",
    ),
    path("plans/", PublicPlansView.as_view(), name="plans"),
    path("hotels/", PublicHotelListView.as_view(), name="hotel-list"),
    path("hotels/<slug:slug>/", PublicHotelDetailView.as_view(), name="hotel-detail"),
    path(
        "hotels/<slug:slug>/availability/",
        PublicAvailabilityView.as_view(),
        name="availability",
    ),
    path(
        "hotels/<slug:slug>/bookings/",
        PublicBookingCreateView.as_view(),
        name="booking-create",
    ),
    path(
        "bookings/<str:reference>/",
        PublicBookingManageView.as_view(),
        name="booking-manage",
    ),
    path(
        "bookings/<str:reference>/cancel-request/",
        PublicBookingCancelRequestView.as_view(),
        name="booking-cancel-request",
    ),
]
