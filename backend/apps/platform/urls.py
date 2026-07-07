"""Platform-owner API URLs (mounted at /api/v1/platform/)."""
from django.urls import path

from .views import (
    HotelDetailView,
    HotelListCreateView,
    HotelManagerView,
    OverviewView,
    PlanDetailView,
    PlanListCreateView,
    SettingsView,
    SubscriptionDetailView,
    SubscriptionListCreateView,
)

app_name = "platform"

urlpatterns = [
    path("overview/", OverviewView.as_view(), name="overview"),
    path("hotels/", HotelListCreateView.as_view(), name="hotel-list"),
    path("hotels/<int:pk>/", HotelDetailView.as_view(), name="hotel-detail"),
    path(
        "hotels/<int:pk>/manager/",
        HotelManagerView.as_view(),
        name="hotel-manager",
    ),
    path("plans/", PlanListCreateView.as_view(), name="plan-list"),
    path("plans/<int:pk>/", PlanDetailView.as_view(), name="plan-detail"),
    path(
        "subscriptions/",
        SubscriptionListCreateView.as_view(),
        name="subscription-list",
    ),
    path(
        "subscriptions/<int:pk>/",
        SubscriptionDetailView.as_view(),
        name="subscription-detail",
    ),
    path("settings/", SettingsView.as_view(), name="settings"),
]
