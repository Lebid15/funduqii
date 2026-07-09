"""Service catalog + order API views (Phase 9), under /api/v1/hotel/services/.

Scoped to the caller's hotel, guarded by ``services.*`` / ``service_orders.*``
permissions. A suspended hotel is read-only. All order mutations (and the one
financial exit — posting to a folio) go through the domain services.
"""
from __future__ import annotations

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceInUse
from apps.finance.services import money
from apps.rbac.permissions import HasHotelPermission
from apps.rooms.models import Room
from apps.stays.models import Stay
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .models import (
    OrderSource,
    OrderStatus,
    ServiceCategory,
    ServiceItem,
    ServiceItemType,
    ServiceOrder,
)
from .serializers import (
    OrderCancelSerializer,
    OrderCreateSerializer,
    OrderStatusSerializer,
    OrderUpdateSerializer,
    ServiceCategorySerializer,
    ServiceItemSerializer,
    ServiceOrderListSerializer,
    ServiceOrderSerializer,
)

CatalogView = HasHotelPermission("services.view")
CatalogCreate = HasHotelPermission("services.create")
CatalogUpdate = HasHotelPermission("services.update")
CatalogDelete = HasHotelPermission("services.delete")

OrdersView = HasHotelPermission("service_orders.view")
OrdersCreate = HasHotelPermission("service_orders.create")
OrdersUpdate = HasHotelPermission("service_orders.update")
OrdersCancel = HasHotelPermission("service_orders.cancel")
OrdersStatus = HasHotelPermission("service_orders.status_update")
OrdersPost = HasHotelPermission("service_orders.post_to_folio")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _get(model, request, pk):
    return generics.get_object_or_404(model, pk=pk, hotel=request.hotel)


def _hotel_header(hotel) -> dict:
    s = getattr(hotel, "settings", None)
    return {
        "hotel_name": (getattr(s, "display_name", "") or hotel.name),
        "currency": getattr(s, "default_currency", "") or "USD",
        "phone": getattr(s, "phone", "") or "",
        "address": getattr(s, "address_line", "") or "",
    }


# --- Categories ---------------------------------------------------------------


class CategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceCategorySerializer

    def get_permissions(self):
        return [CatalogCreate()] if self.request.method == "POST" else [CatalogView()]

    def get_queryset(self):
        qs = ServiceCategory.objects.filter(hotel=self.request.hotel).annotate(
            item_count=Count("items")
        )
        p = self.request.query_params
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        if p.get("search"):
            qs = qs.filter(name__icontains=p["search"]) | qs.filter(
                code__icontains=p["search"]
            )
        return qs.distinct()

    def perform_create(self, serializer):
        _guard_write(self.request)
        serializer.save(hotel=self.request.hotel)


class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServiceCategorySerializer
    http_method_names = ["get", "patch", "delete", "options", "head"]

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [CatalogDelete()]
        if self.request.method == "PATCH":
            return [CatalogUpdate()]
        return [CatalogView()]

    def get_queryset(self):
        return ServiceCategory.objects.filter(hotel=self.request.hotel).annotate(
            item_count=Count("items")
        )

    def perform_update(self, serializer):
        _guard_write(self.request)
        serializer.save()

    def perform_destroy(self, instance):
        _guard_write(self.request)
        if instance.items.exists():
            raise ResourceInUse({"resource": "service_category", "id": instance.id})
        instance.delete()


# --- Items ----------------------------------------------------------------------


class ItemListCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceItemSerializer

    def get_permissions(self):
        return [CatalogCreate()] if self.request.method == "POST" else [CatalogView()]

    def get_queryset(self):
        qs = ServiceItem.objects.filter(hotel=self.request.hotel).select_related(
            "category"
        )
        p = self.request.query_params
        if p.get("category") and str(p["category"]).isdigit():
            qs = qs.filter(category_id=int(p["category"]))
        if p.get("item_type") in {c for c, _ in ServiceItemType.choices}:
            qs = qs.filter(item_type=p["item_type"])
        if p.get("is_available") in ("true", "false"):
            qs = qs.filter(is_available=p["is_available"] == "true")
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        if p.get("search"):
            qs = qs.filter(name__icontains=p["search"]) | qs.filter(
                code__icontains=p["search"]
            )
        ordering = p.get("ordering")
        if ordering in ("name", "-name", "unit_price", "-unit_price", "sort_order"):
            qs = qs.order_by(ordering)
        return qs.distinct()

    def perform_create(self, serializer):
        _guard_write(self.request)
        category = serializer.validated_data.get("category")
        if category is not None and category.hotel_id != self.request.hotel.id:
            from apps.common.exceptions import CrossTenantReference

            raise CrossTenantReference({"field": "category"})
        serializer.save(hotel=self.request.hotel)


class ItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ServiceItemSerializer
    http_method_names = ["get", "patch", "delete", "options", "head"]

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [CatalogDelete()]
        if self.request.method == "PATCH":
            return [CatalogUpdate()]
        return [CatalogView()]

    def get_queryset(self):
        return ServiceItem.objects.filter(hotel=self.request.hotel).select_related(
            "category"
        )

    def perform_update(self, serializer):
        _guard_write(self.request)
        category = serializer.validated_data.get("category")
        if category is not None and category.hotel_id != self.request.hotel.id:
            from apps.common.exceptions import CrossTenantReference

            raise CrossTenantReference({"field": "category"})
        serializer.save()

    def perform_destroy(self, instance):
        _guard_write(self.request)
        if instance.order_items.exists():
            # Used on at least one order — deactivate instead of deleting.
            raise ResourceInUse({"resource": "service_item", "id": instance.id})
        instance.delete()


# --- Orders ----------------------------------------------------------------------


def _resolve_order_refs(request: Request, data: dict) -> dict:
    """Turn stay/room/item ids into hotel-scoped instances (404 if foreign)."""
    stay = _get(Stay, request, data["stay"]) if data.get("stay") else None
    room = _get(Room, request, data["room"]) if data.get("room") else None
    items_data = None
    if data.get("items") is not None:
        items_data = [
            {
                "service_item": _get(ServiceItem, request, entry["service_item"]),
                "quantity": entry["quantity"],
                "notes": entry.get("notes", ""),
            }
            for entry in data["items"]
        ]
    return {"stay": stay, "room": room, "items_data": items_data}


class OrderListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [OrdersCreate()] if self.request.method == "POST" else [OrdersView()]

    def get_queryset(self):
        qs = (
            ServiceOrder.objects.filter(hotel=self.request.hotel)
            .select_related("room", "stay")
            .annotate(total=Sum("items__total_amount"))
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in OrderStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("source") in {c for c, _ in OrderSource.choices}:
            qs = qs.filter(source=p["source"])
        if p.get("stay") and str(p["stay"]).isdigit():
            qs = qs.filter(stay_id=int(p["stay"]))
        if p.get("room") and str(p["room"]).isdigit():
            qs = qs.filter(room_id=int(p["room"]))
        if p.get("date"):
            qs = qs.filter(ordered_at__date=p["date"])
        if p.get("posted") in ("true", "false"):
            qs = qs.filter(posted_at__isnull=(p["posted"] == "false"))
        if p.get("search"):
            qs = qs.filter(order_number__icontains=p["search"])
        ordering = p.get("ordering")
        if ordering in ("ordered_at", "-ordered_at", "order_number", "-order_number"):
            qs = qs.order_by(ordering)
        return qs

    def get_serializer_class(self):
        return ServiceOrderListSerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refs = _resolve_order_refs(request, data)
        order = services.create_order(
            request.hotel,
            user=request.user,
            source=data["source"],
            stay=refs["stay"],
            room=refs["room"],
            status=data["status"],
            requested_delivery_time=data.get("requested_delivery_time"),
            notes=data.get("notes", ""),
            internal_notes=data.get("internal_notes", ""),
            items_data=refs["items_data"] or [],
        )
        return Response(
            ServiceOrderSerializer(order).data, status=status.HTTP_201_CREATED
        )


class OrderDetailView(APIView):
    def get_permissions(self):
        return [OrdersUpdate()] if self.request.method == "PATCH" else [OrdersView()]

    def get(self, request: Request, pk: int) -> Response:
        order = _get(ServiceOrder, request, pk)
        return Response(ServiceOrderSerializer(order).data)

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        order = _get(ServiceOrder, request, pk)
        serializer = OrderUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refs = _resolve_order_refs(request, data)
        meta = {
            k: data[k]
            for k in ("source", "requested_delivery_time", "notes", "internal_notes")
            if k in data
        }
        order = services.update_order(
            order, user=request.user, items_data=refs["items_data"], **meta
        )
        return Response(ServiceOrderSerializer(order).data)


class OrderStatusView(APIView):
    permission_classes = [OrdersStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        order = _get(ServiceOrder, request, pk)
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.change_status(
            order,
            new_status=serializer.validated_data["status"],
            user=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(ServiceOrderSerializer(order).data)


class OrderCancelView(APIView):
    permission_classes = [OrdersCancel]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        order = _get(ServiceOrder, request, pk)
        serializer = OrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.cancel_order(
            order, reason=serializer.validated_data["reason"], user=request.user
        )
        return Response(ServiceOrderSerializer(order).data)


class OrderPostToFolioView(APIView):
    permission_classes = [OrdersPost]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        order = _get(ServiceOrder, request, pk)
        order = services.post_order_to_folio(order, user=request.user)
        return Response(ServiceOrderSerializer(order).data)


class OrderTicketView(APIView):
    permission_classes = [OrdersView]

    def get(self, request: Request, pk: int) -> Response:
        order = _get(ServiceOrder, request, pk)
        totals = services.order_totals(order)
        return Response(
            {
                "document": "service_ticket",
                "hotel": _hotel_header(request.hotel),
                "order": {
                    "order_number": order.order_number,
                    "source": order.source,
                    "status": order.status,
                    "room_number": order.room.number if order.room else "",
                    "guest_name": (
                        order.stay.primary_guest.full_name if order.stay else ""
                    ),
                    "ordered_at": order.ordered_at,
                    "requested_delivery_time": order.requested_delivery_time,
                    "notes": order.notes,
                },
                "items": [
                    {
                        "item_name": i.item_name,
                        "quantity": str(i.quantity),
                        "unit_price": str(i.unit_price),
                        "total_amount": str(i.total_amount),
                        "notes": i.notes,
                    }
                    for i in order.items.all()
                ],
                "totals": {k: str(v) for k, v in totals.items()},
            }
        )


# --- Overview ---------------------------------------------------------------------


class ServicesOverviewView(APIView):
    permission_classes = [OrdersView]

    def get(self, request: Request) -> Response:
        hotel = request.hotel
        today = timezone.localdate()
        base = ServiceOrder.objects.filter(hotel=hotel)
        today_qs = base.filter(ordered_at__date=today)
        by_status = {row["status"]: row["n"] for row in
                     today_qs.values("status").annotate(n=Count("id"))}
        posted_today = base.filter(posted_at__date=today).aggregate(
            total=Sum("posted_charge__total_amount")
        )["total"]
        return Response(
            {
                "orders_today": today_qs.count(),
                "submitted": by_status.get(OrderStatus.SUBMITTED, 0),
                "preparing": by_status.get(OrderStatus.PREPARING, 0),
                "ready": by_status.get(OrderStatus.READY, 0),
                "delivered": by_status.get(OrderStatus.DELIVERED, 0),
                "delivered_not_posted": base.filter(
                    status=OrderStatus.DELIVERED, posted_at__isnull=True
                ).count(),
                "posted_today_total": str(money(posted_today or 0)),
                "active_items": ServiceItem.objects.filter(
                    hotel=hotel, is_active=True
                ).count(),
            }
        )
