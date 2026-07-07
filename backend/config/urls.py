"""Root URL configuration for the Funduqii backend.

Phase 2 exposes authentication, a platform-scope probe, and a permission
probe. The probes under ``/api/platform/`` and ``/api/foundation/`` are
FOUNDATION endpoints used to verify auth/permission wiring — they are NOT
operational business features.
"""
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import PlatformPingView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/platform/ping/", PlatformPingView.as_view(), name="platform-ping"),
    path("api/foundation/", include("apps.rbac.urls")),
]
