"""Service catalog + orders URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    CategoryDetailView,
    CategoryListCreateView,
    ItemDetailView,
    ItemListCreateView,
    OrderCancelView,
    OrderDetailView,
    OrderListCreateView,
    OrderPostToFolioView,
    OrderStatusView,
    OrderTicketView,
    ServicesOverviewView,
)

app_name = "services"

urlpatterns = [
    path("services/overview/", ServicesOverviewView.as_view(), name="overview"),
    path("services/categories/", CategoryListCreateView.as_view(), name="category-list"),
    path("services/categories/<int:pk>/", CategoryDetailView.as_view(), name="category-detail"),
    path("services/items/", ItemListCreateView.as_view(), name="item-list"),
    path("services/items/<int:pk>/", ItemDetailView.as_view(), name="item-detail"),
    path("services/orders/", OrderListCreateView.as_view(), name="order-list"),
    path("services/orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("services/orders/<int:pk>/status/", OrderStatusView.as_view(), name="order-status"),
    path("services/orders/<int:pk>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
    path(
        "services/orders/<int:pk>/post-to-folio/",
        OrderPostToFolioView.as_view(),
        name="order-post-to-folio",
    ),
    path("services/orders/<int:pk>/ticket/", OrderTicketView.as_view(), name="order-ticket"),
]
