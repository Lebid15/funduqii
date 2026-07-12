"""Platform-owner notification URLs (mounted at /api/v1/platform/notifications/).
No DELETE, no external channels — the platform owner's own in-app centre."""
from django.urls import path

from .platform_views import (
    PlatformArchiveView,
    PlatformMarkAllReadView,
    PlatformMarkReadView,
    PlatformNotificationDetailView,
    PlatformNotificationListView,
    PlatformNotificationsOverviewView,
    PlatformUnreadCountView,
)

app_name = "platform_notifications"

urlpatterns = [
    path("overview/", PlatformNotificationsOverviewView.as_view(), name="overview"),
    path("unread-count/", PlatformUnreadCountView.as_view(), name="unread-count"),
    path("mark-all-read/", PlatformMarkAllReadView.as_view(), name="mark-all-read"),
    path("", PlatformNotificationListView.as_view(), name="list"),
    path("<int:pk>/", PlatformNotificationDetailView.as_view(), name="detail"),
    path("<int:pk>/mark-read/", PlatformMarkReadView.as_view(), name="mark-read"),
    path("<int:pk>/archive/", PlatformArchiveView.as_view(), name="archive"),
]
