"""Guest extra-services URLs (mounted under /api/v1/hotel/).

Routes: the catalog (list/create/detail/update + deactivate/activate), the
add-service action, and the folio directory. There is NO DELETE http method on
ANY route (the catalog is deactivated, never deleted; postings are never
hard-deleted) and NO new permission namespace."""
from django.urls import path

from .views import (
    AddGuestServiceView,
    CatalogActivateView,
    CatalogDeactivateView,
    CatalogDetailView,
    CatalogListCreateView,
    GuestFolioDirectoryView,
    StayServiceLinesView,
)

app_name = "guest_services"

urlpatterns = [
    # Catalog ("Services & Prices") — services.* permissions.
    path(
        "guest-services/catalog/",
        CatalogListCreateView.as_view(),
        name="catalog-list",
    ),
    path(
        "guest-services/catalog/<int:pk>/",
        CatalogDetailView.as_view(),
        name="catalog-detail",
    ),
    path(
        "guest-services/catalog/<int:pk>/deactivate/",
        CatalogDeactivateView.as_view(),
        name="catalog-deactivate",
    ),
    path(
        "guest-services/catalog/<int:pk>/activate/",
        CatalogActivateView.as_view(),
        name="catalog-activate",
    ),
    # Post a catalog service to a stay's folio.
    path(
        "guest-services/stays/<int:stay_id>/add/",
        AddGuestServiceView.as_view(),
        name="stay-add-service",
    ),
    # Money-safe operational view of the stay's folio SERVICE line items.
    path(
        "guest-services/stays/<int:stay_id>/service-lines/",
        StayServiceLinesView.as_view(),
        name="stay-service-lines",
    ),
    # Compact in-house folio directory.
    path(
        "guest-services/folio-directory/",
        GuestFolioDirectoryView.as_view(),
        name="folio-directory",
    ),
]
