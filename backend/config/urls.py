"""Root URL configuration for the Funduqii backend.

Phase 2 exposes authentication, a platform-scope probe, and a permission
probe. The probes under ``/api/platform/`` and ``/api/foundation/`` are
FOUNDATION endpoints used to verify auth/permission wiring — they are NOT
operational business features.

Phase 3 adds the platform owner's first real feature surface under the
versioned prefix ``/api/v1/platform/`` (apps.platform). Every endpoint there is
restricted to the platform owner.

Phase 4 adds the hotel's own settings & media under ``/api/v1/hotel/``
(apps.hotels), scoped to the caller's hotel context and permissions.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import PlatformPingView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/platform/ping/", PlatformPingView.as_view(), name="platform-ping"),
    path("api/foundation/", include("apps.rbac.urls")),
    path("api/v1/platform/", include("apps.platform.urls")),
    path("api/v1/hotel/", include("apps.hotels.urls")),
    path("api/v1/hotel/", include("apps.rooms.urls")),
    path("api/v1/hotel/", include("apps.reservations.urls")),
    path("api/v1/hotel/", include("apps.guests.urls")),
    path("api/v1/hotel/", include("apps.stays.urls")),
    path("api/v1/hotel/", include("apps.finance.urls")),
    path("api/v1/hotel/", include("apps.services.urls")),
    path("api/v1/hotel/", include("apps.operations.urls")),
    path("api/v1/hotel/", include("apps.staff.urls")),
    path("api/v1/hotel/", include("apps.shifts.urls")),
    path("api/v1/hotel/", include("apps.reports.urls")),
]

# Serve uploaded media in development only. In production the media files are
# served by the web server / object storage (see the deployment docs).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
