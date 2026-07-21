"""Service catalog + tables + orders URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    CategoryDetailView,
    CategoryListCreateView,
    ItemDetailView,
    ItemListCreateView,
    OrderCancelView,
    OrderDetailView,
    OrderItemCancelView,
    OrderListCreateView,
    OrderPostToFolioView,
    OrderReturnView,
    OrderSettleDirectView,
    OrderStatusView,
    OrderTicketView,
    ServicesOverviewView,
    TableDetailView,
    TableListCreateView,
    TableStatusView,
)

app_name = "services"

urlpatterns = [
    path("services/overview/", ServicesOverviewView.as_view(), name="overview"),
    path("services/categories/", CategoryListCreateView.as_view(), name="category-list"),
    path("services/categories/<int:pk>/", CategoryDetailView.as_view(), name="category-detail"),
    path("services/items/", ItemListCreateView.as_view(), name="item-list"),
    path("services/items/<int:pk>/", ItemDetailView.as_view(), name="item-detail"),
    # Tables (restaurant & café final closure)
    path("services/tables/", TableListCreateView.as_view(), name="table-list"),
    path("services/tables/<int:pk>/", TableDetailView.as_view(), name="table-detail"),
    path("services/tables/<int:pk>/status/", TableStatusView.as_view(), name="table-status"),
    path("services/orders/", OrderListCreateView.as_view(), name="order-list"),
    path("services/orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("services/orders/<int:pk>/status/", OrderStatusView.as_view(), name="order-status"),
    path("services/orders/<int:pk>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
    path(
        "services/orders/<int:pk>/items/<int:item_id>/cancel/",
        OrderItemCancelView.as_view(),
        name="order-item-cancel",
    ),
    path(
        "services/orders/<int:pk>/post-to-folio/",
        OrderPostToFolioView.as_view(),
        name="order-post-to-folio",
    ),
    path(
        "services/orders/<int:pk>/settle-direct/",
        OrderSettleDirectView.as_view(),
        name="order-settle-direct",
    ),
    path(
        "services/orders/<int:pk>/return/",
        OrderReturnView.as_view(),
        name="order-return",
    ),
    path("services/orders/<int:pk>/ticket/", OrderTicketView.as_view(), name="order-ticket"),
]
