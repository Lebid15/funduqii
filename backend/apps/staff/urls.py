"""Staff & permissions URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    MyPermissionsView,
    PermissionRegistryView,
    StaffDeactivateView,
    StaffDetailView,
    StaffLinkExistingView,
    StaffListCreateView,
    StaffOverviewView,
    StaffPermissionsView,
    StaffReactivateView,
    StaffResetPasswordView,
)

app_name = "staff"

urlpatterns = [
    path("staff/overview/", StaffOverviewView.as_view(), name="overview"),
    path(
        "staff/permission-registry/",
        PermissionRegistryView.as_view(),
        name="permission-registry",
    ),
    path("staff/my-permissions/", MyPermissionsView.as_view(), name="my-permissions"),
    path(
        "staff/link-existing-user/",
        StaffLinkExistingView.as_view(),
        name="link-existing-user",
    ),
    path("staff/", StaffListCreateView.as_view(), name="staff-list"),
    path("staff/<int:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path(
        "staff/<int:pk>/deactivate/",
        StaffDeactivateView.as_view(),
        name="staff-deactivate",
    ),
    path(
        "staff/<int:pk>/reactivate/",
        StaffReactivateView.as_view(),
        name="staff-reactivate",
    ),
    path(
        "staff/<int:pk>/permissions/",
        StaffPermissionsView.as_view(),
        name="staff-permissions",
    ),
    path(
        "staff/<int:pk>/reset-password/",
        StaffResetPasswordView.as_view(),
        name="staff-reset-password",
    ),
]
