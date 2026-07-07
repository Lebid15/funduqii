"""Foundation probe URLs (mounted at /api/foundation/)."""
from django.urls import path

from .views import RequirePermissionProbeView

urlpatterns = [
    path(
        "require-permission/",
        RequirePermissionProbeView.as_view(),
        name="foundation_require_permission",
    ),
]
