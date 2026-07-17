"""Platform-owner API URLs (mounted at /api/v1/platform/)."""
from django.urls import path

from .views import (
    DashboardView,
    HotelActivatePaidView,
    HotelActivateView,
    HotelCancelSubscriptionView,
    HotelChangePlanView,
    HotelDetailView,
    HotelExpireSubscriptionView,
    HotelListCreateView,
    HotelManagerView,
    HotelReactivateView,
    HotelRenewView,
    HotelStartTrialView,
    HotelSubscriptionHistoryView,
    HotelSubscriptionStateView,
    HotelSuspendView,
    HotelUnsuspendView,
    OverviewView,
    PlanActivateView,
    PlanDeactivateView,
    PlanDetailView,
    PlanListCreateView,
    PlatformPaymentListCreateView,
    PlatformPaymentVoidView,
    PublicSiteSettingsView,
    SettingsView,
    SubscriptionDetailView,
    SubscriptionListCreateView,
    SubscriptionRequestAcceptView,
    SubscriptionRequestCancelView,
    SubscriptionRequestDetailView,
    SubscriptionRequestExecuteView,
    SubscriptionRequestListView,
    SubscriptionRequestRejectView,
)

app_name = "platform"

urlpatterns = [
    path("overview/", OverviewView.as_view(), name="overview"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("hotels/", HotelListCreateView.as_view(), name="hotel-list"),
    path("hotels/<int:pk>/", HotelDetailView.as_view(), name="hotel-detail"),
    path(
        "hotels/<int:pk>/manager/",
        HotelManagerView.as_view(),
        name="hotel-manager",
    ),
    # Phase 16 — hotel status lifecycle (no hard delete exists).
    path(
        "hotels/<int:pk>/activate/",
        HotelActivateView.as_view(),
        name="hotel-activate",
    ),
    path(
        "hotels/<int:pk>/suspend/",
        HotelSuspendView.as_view(),
        name="hotel-suspend",
    ),
    path(
        "hotels/<int:pk>/unsuspend/",
        HotelUnsuspendView.as_view(),
        name="hotel-unsuspend",
    ),
    # Phase 16 — subscription lifecycle per hotel.
    path(
        "hotels/<int:pk>/subscriptions/start-trial/",
        HotelStartTrialView.as_view(),
        name="hotel-start-trial",
    ),
    path(
        "hotels/<int:pk>/subscriptions/activate-paid/",
        HotelActivatePaidView.as_view(),
        name="hotel-activate-paid",
    ),
    path(
        "hotels/<int:pk>/subscriptions/renew/",
        HotelRenewView.as_view(),
        name="hotel-renew",
    ),
    path(
        "hotels/<int:pk>/subscriptions/change-plan/",
        HotelChangePlanView.as_view(),
        name="hotel-change-plan",
    ),
    path(
        "hotels/<int:pk>/subscriptions/reactivate/",
        HotelReactivateView.as_view(),
        name="hotel-reactivate",
    ),
    path(
        "hotels/<int:pk>/subscriptions/cancel/",
        HotelCancelSubscriptionView.as_view(),
        name="hotel-cancel-subscription",
    ),
    path(
        "hotels/<int:pk>/subscriptions/expire/",
        HotelExpireSubscriptionView.as_view(),
        name="hotel-expire-subscription",
    ),
    path(
        "hotels/<int:pk>/subscriptions/state/",
        HotelSubscriptionStateView.as_view(),
        name="hotel-subscription-state",
    ),
    path(
        "hotels/<int:pk>/subscriptions/history/",
        HotelSubscriptionHistoryView.as_view(),
        name="hotel-subscription-history",
    ),
    path("plans/", PlanListCreateView.as_view(), name="plan-list"),
    path("plans/<int:pk>/", PlanDetailView.as_view(), name="plan-detail"),
    path(
        "plans/<int:pk>/activate/",
        PlanActivateView.as_view(),
        name="plan-activate",
    ),
    path(
        "plans/<int:pk>/deactivate/",
        PlanDeactivateView.as_view(),
        name="plan-deactivate",
    ),
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
    # Phase 16 — manual platform payments (never a gateway).
    path(
        "subscription-payments/",
        PlatformPaymentListCreateView.as_view(),
        name="payment-list",
    ),
    path(
        "subscription-payments/<int:pk>/void/",
        PlatformPaymentVoidView.as_view(),
        name="payment-void",
    ),
    # §8.5 — hotel-initiated subscription change requests (owner review).
    path(
        "subscription-requests/",
        SubscriptionRequestListView.as_view(),
        name="subscription-request-list",
    ),
    path(
        "subscription-requests/<int:pk>/",
        SubscriptionRequestDetailView.as_view(),
        name="subscription-request-detail",
    ),
    path(
        "subscription-requests/<int:pk>/accept/",
        SubscriptionRequestAcceptView.as_view(),
        name="subscription-request-accept",
    ),
    path(
        "subscription-requests/<int:pk>/reject/",
        SubscriptionRequestRejectView.as_view(),
        name="subscription-request-reject",
    ),
    path(
        "subscription-requests/<int:pk>/execute/",
        SubscriptionRequestExecuteView.as_view(),
        name="subscription-request-execute",
    ),
    path(
        "subscription-requests/<int:pk>/cancel/",
        SubscriptionRequestCancelView.as_view(),
        name="subscription-request-cancel",
    ),
    path("settings/", SettingsView.as_view(), name="settings"),
    # Phase 16 — public-website admin settings.
    path(
        "public-site-settings/",
        PublicSiteSettingsView.as_view(),
        name="public-site-settings",
    ),
]
