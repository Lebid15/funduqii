"""Notification/activity URLs (mounted under /api/v1/hotel/). No DELETE."""
from django.urls import path

from .views import (
    ActivityDetailView,
    ActivityListView,
    ArchiveView,
    MarkAllReadView,
    MarkReadView,
    NotificationDetailView,
    NotificationListView,
    NotificationsOverviewView,
    UnreadCountView,
)

app_name = "notifications"

urlpatterns = [
    path(
        "notifications/overview/",
        NotificationsOverviewView.as_view(),
        name="overview",
    ),
    path("notifications/unread-count/", UnreadCountView.as_view(), name="unread-count"),
    path(
        "notifications/mark-all-read/",
        MarkAllReadView.as_view(),
        name="mark-all-read",
    ),
    path("notifications/activity/", ActivityListView.as_view(), name="activity-list"),
    path(
        "notifications/activity/<int:pk>/",
        ActivityDetailView.as_view(),
        name="activity-detail",
    ),
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path(
        "notifications/<int:pk>/",
        NotificationDetailView.as_view(),
        name="notification-detail",
    ),
    path(
        "notifications/<int:pk>/mark-read/",
        MarkReadView.as_view(),
        name="mark-read",
    ),
    path("notifications/<int:pk>/archive/", ArchiveView.as_view(), name="archive"),
]
