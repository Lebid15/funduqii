"""Service catalog + order API views (Phase 9), under /api/v1/hotel/services/.

Scoped to the caller's hotel, guarded by ``services.*`` / ``service_orders.*``
permissions. A suspended hotel is read-only. All order mutations (and the one
financial exit — posting to a folio) go through the domain services.
"""
from __future__ import annotations

from django.db.models import Count, OuterRef, Q, Subquery, Sum
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ResourceInUse
from apps.finance.services import money
from apps.rbac.permissions import HasHotelPermission
from apps.shifts.services import get_business_date
from apps.stays.models import Stay
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .models import (
    OrderSettlement,
    OrderStatus,
    OrderType,
    Outlet,
    RestaurantTable,
    ServiceCategory,
    ServiceItem,
    ServiceOrder,
    ServiceOrderItem,
)
from .serializers import (
    OrderCancelSerializer,
    OrderCreateSerializer,
    OrderPostToFolioSerializer,
    OrderSettleDirectSerializer,
    OrderStatusSerializer,
    OrderUpdateSerializer,
    RestaurantTableSerializer,
    ReturnSerializer,
    ServiceCategorySerializer,
    ServiceItemSerializer,
    ServiceOrderListSerializer,
    ServiceOrderReturnSerializer,
    ServiceOrderSerializer,
    TableStatusSerializer,
)

CatalogView = HasHotelPermission("services.view")
CatalogCreate = HasHotelPermission("services.create")
CatalogUpdate = HasHotelPermission("services.update")
CatalogDelete = HasHotelPermission("services.delete")
TablesManage = HasHotelPermission("services.tables_manage")

OrdersView = HasHotelPermission("service_orders.view")
OrdersCreate = HasHotelPermission("service_orders.create")
OrdersUpdate = HasHotelPermission("service_orders.update")
OrdersCancel = HasHotelPermission("service_orders.cancel")
OrdersStatus = HasHotelPermission("service_orders.status_update")
OrdersPost = HasHotelPermission("service_orders.post_to_folio")
OrdersSettleDirect = HasHotelPermission("service_orders.settle_direct")
# A return/exchange moves money BACK to (or collects a delta from) the customer —
# gated on the EXISTING finance refund permission (§37: a real payout to the
# guest), NOT a new code and NOT an RBAC-registry change. This is the most
# defensible reuse: a return is fundamentally a guest refund.
OrdersReturn = HasHotelPermission("finance.refund")

#: The "open order" predicate — one per table; occupancy is DERIVED from it.
OPEN_ORDER_Q = Q(settled_at__isnull=True) & ~Q(status=OrderStatus.CANCELLED)


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
        if p.get("outlet") in {c for c, _ in Outlet.choices}:
            qs = qs.filter(outlet=p["outlet"])
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        if p.get("search"):
            qs = qs.filter(name__icontains=p["search"]) | qs.filter(
                code__icontains=p["search"]
            )
        return qs.distinct()

    def perform_create(self, serializer):
        _guard_write(self.request)
        # Restaurant closure: a disabled outlet takes no NEW catalog rows.
        services._ensure_outlet_enabled(
            self.request.hotel, serializer.validated_data.get("outlet", Outlet.RESTAURANT)
        )
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
        if p.get("outlet") in {c for c, _ in Outlet.choices}:
            qs = qs.filter(category__outlet=p["outlet"])
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
        # Restaurant closure: a disabled outlet takes no NEW items.
        if category is not None:
            services._ensure_outlet_enabled(self.request.hotel, category.outlet)
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


# --- Tables ----------------------------------------------------------------------


class TableListCreateView(generics.ListCreateAPIView):
    serializer_class = RestaurantTableSerializer

    def get_permissions(self):
        return [TablesManage()] if self.request.method == "POST" else [CatalogView()]

    def get_queryset(self):
        from django.db.models import Exists

        open_orders = ServiceOrder.objects.filter(OPEN_ORDER_Q, table=OuterRef("pk"))
        qs = RestaurantTable.objects.filter(hotel=self.request.hotel).annotate(
            is_occupied=Exists(open_orders)
        )
        p = self.request.query_params
        if p.get("outlet") in {c for c, _ in Outlet.choices}:
            qs = qs.filter(outlet=p["outlet"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        return qs

    def list(self, request, *args, **kwargs):
        # Attach each table's ONE open order (cheap: open orders are few).
        response = super().list(request, *args, **kwargs)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        ids = [r["id"] for r in rows]
        open_orders = (
            ServiceOrder.objects.filter(OPEN_ORDER_Q, table_id__in=ids)
            .select_related("stay__primary_guest")
        )
        by_table = {o.table_id: o for o in open_orders}
        for r in rows:
            order = by_table.get(r["id"])
            r["open_order"] = (
                {
                    "id": order.id,
                    "order_number": order.order_number,
                    "status": order.status,
                    "customer_name": order.customer_name,
                    "guest_name": (
                        order.stay.primary_guest.full_name if order.stay else ""
                    ),
                }
                if order
                else None
            )
        return response

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        table = services.create_table(
            request.hotel,
            outlet=d["outlet"],
            number=d["number"],
            name=d.get("name", ""),
            capacity=d.get("capacity", 2),
            user=request.user,
        )
        return Response(
            RestaurantTableSerializer(table).data, status=status.HTTP_201_CREATED
        )


class TableDetailView(APIView):
    def get_permissions(self):
        return [CatalogView()] if self.request.method == "GET" else [TablesManage()]

    def get(self, request: Request, pk: int) -> Response:
        table = _get(RestaurantTable, request, pk)
        data = RestaurantTableSerializer(table).data
        data["is_occupied"] = services._table_has_open_order(table)
        return Response(data)

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        table = _get(RestaurantTable, request, pk)
        serializer = RestaurantTableSerializer(table, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = {
            k: v for k, v in serializer.validated_data.items()
            if k in ("number", "name", "capacity")
        }
        table = services.update_table(table, user=request.user, **fields)
        return Response(RestaurantTableSerializer(table).data)

    def delete(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        table = _get(RestaurantTable, request, pk)
        if table.orders.exists():
            # Used in at least one order — history keeps it; take it out of
            # service instead of deleting.
            raise ResourceInUse({"resource": "restaurant_table", "id": table.id})
        table.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TableStatusView(APIView):
    permission_classes = [TablesManage]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        table = _get(RestaurantTable, request, pk)
        serializer = TableStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        table = services.set_table_status(
            table,
            status=serializer.validated_data["status"],
            note=serializer.validated_data.get("note", ""),
            user=request.user,
        )
        return Response(RestaurantTableSerializer(table).data)


# --- Orders ----------------------------------------------------------------------


def _resolve_order_refs(request: Request, data: dict) -> dict:
    """Turn stay/table/item ids into hotel-scoped instances (404 if foreign)."""
    stay = _get(Stay, request, data["stay"]) if data.get("stay") else None
    table = _get(RestaurantTable, request, data["table"]) if data.get("table") else None
    items_data = None
    if data.get("items") is not None:
        items_data = [
            {
                "service_item": _get(
                    ServiceItem.objects.select_related("category"), request,
                    entry["service_item"],
                ),
                "quantity": entry["quantity"],
                "notes": entry.get("notes", ""),
            }
            for entry in data["items"]
        ]
    return {"stay": stay, "table": table, "items_data": items_data}


class OrderListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [OrdersCreate()] if self.request.method == "POST" else [OrdersView()]

    def get_queryset(self):
        qs = (
            ServiceOrder.objects.filter(hotel=self.request.hotel)
            .select_related("room", "stay", "table")
            .annotate(
                total=Sum(
                    "items__total_amount",
                    filter=Q(items__cancelled_at__isnull=True),
                )
            )
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in OrderStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("order_type") in {c for c, _ in OrderType.choices}:
            qs = qs.filter(order_type=p["order_type"])
        if p.get("outlet") in {c for c, _ in Outlet.choices}:
            qs = qs.filter(outlet=p["outlet"])
        if p.get("settlement") in {c for c, _ in OrderSettlement.choices}:
            qs = qs.filter(settlement=p["settlement"])
        if p.get("stay") and str(p["stay"]).isdigit():
            qs = qs.filter(stay_id=int(p["stay"]))
        if p.get("room") and str(p["room"]).isdigit():
            qs = qs.filter(room_id=int(p["room"]))
        if p.get("table") and str(p["table"]).isdigit():
            qs = qs.filter(table_id=int(p["table"]))
        if p.get("date"):
            # The hotel BUSINESS date (legacy rows fall back to ordered_at).
            qs = qs.filter(
                Q(business_date=p["date"])
                | Q(business_date__isnull=True, ordered_at__date=p["date"])
            )
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
            order_type=data["order_type"],
            outlet=data["outlet"],
            stay=refs["stay"],
            table=refs["table"],
            customer_name=data.get("customer_name", ""),
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
            for k in ("requested_delivery_time", "notes", "internal_notes")
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
        serializer = OrderPostToFolioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data.get("idempotency_key", "")
        # The fingerprint is server-derived (only the order identity is salient).
        fingerprint = (
            services.build_folio_post_fingerprint(order_id=order.id) if key else ""
        )
        order = services.post_order_to_folio(
            order, user=request.user,
            settlement_key=key, settlement_fingerprint=fingerprint,
        )
        return Response(ServiceOrderSerializer(order).data)


class OrderSettleDirectView(APIView):
    """Direct payment — the transient-folio cycle (XOR with folio posting)."""

    permission_classes = [OrdersSettleDirect]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        order = _get(ServiceOrder, request, pk)
        serializer = OrderSettleDirectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        # D5 — the fingerprint is computed server-side from the salient request
        # fields (mirrors the guest_services idempotency wiring).
        fingerprint = services.build_settlement_fingerprint(
            order_id=order.id,
            method=d["method"],
            amount_received=d.get("amount_received"),
            reference=d.get("reference", ""),
        )
        order = services.settle_order_direct(
            order,
            method=d["method"],
            user=request.user,
            amount_received=d.get("amount_received"),
            settlement_reference=d.get("reference", ""),
            settlement_key=d.get("idempotency_key", ""),
            settlement_fingerprint=fingerprint,
        )
        return Response(ServiceOrderSerializer(order).data)


def _resolve_return_items(request: Request, order, items: list) -> list:
    """Turn the return body's original_item / replacement_item ids into
    hotel-scoped instances (a cross-hotel or non-order line is a 404)."""
    resolved = []
    for entry in items:
        orig = generics.get_object_or_404(
            ServiceOrderItem, pk=entry["original_item"], order=order,
            hotel=request.hotel,
        )
        rep = None
        if entry.get("replacement_item"):
            rep = _get(
                ServiceItem.objects.select_related("category"), request,
                entry["replacement_item"],
            )
        resolved.append(
            {
                "original_item": orig,
                "quantity": entry["quantity"],
                "replacement_item": rep,
                "replacement_quantity": entry.get("replacement_quantity"),
            }
        )
    return resolved


class OrderReturnView(APIView):
    """Return / exchange a DELIVERED, SETTLED order (after delivery only).

    Gated on ``finance.refund`` (the §37 payout-to-guest permission) — a return
    moves money back to (or collects a delta from) the customer. All money runs
    through finance; the order's original settlement is never rewritten."""

    permission_classes = [OrdersReturn]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        order = _get(ServiceOrder, request, pk)
        serializer = ReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        # D5 — build the fingerprint from the RAW request ids BEFORE resolving.
        fingerprint = services.build_return_fingerprint(
            order_id=order.id, kind=d["kind"], items=d["items"], reason=d["reason"],
        )
        items = _resolve_return_items(request, order, d["items"])
        ret = services.return_order(
            order,
            kind=d["kind"],
            items=items,
            reason=d["reason"],
            user=request.user,
            idempotency_key=d.get("idempotency_key", ""),
            request_fingerprint=fingerprint,
            method=d.get("method"),
            amount_received=d.get("amount_received"),
            settlement_reference=d.get("reference", ""),
        )
        order.refresh_from_db()
        return Response(
            {
                "return": ServiceOrderReturnSerializer(ret).data,
                "order": ServiceOrderSerializer(order).data,
            },
            status=status.HTTP_201_CREATED,
        )


class OrderItemCancelView(APIView):
    """Cancel ONE whole line before settlement (reason mandatory; the line
    stays with its snapshot and is excluded from the totals)."""

    permission_classes = [OrdersUpdate]

    def post(self, request: Request, pk: int, item_id: int) -> Response:
        _guard_write(request)
        order = _get(ServiceOrder, request, pk)
        item = generics.get_object_or_404(
            ServiceOrderItem, pk=item_id, order=order, hotel=request.hotel
        )
        serializer = OrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_order_item(
            item, reason=serializer.validated_data["reason"], user=request.user
        )
        order.refresh_from_db()
        return Response(ServiceOrderSerializer(order).data)


class OrderTicketView(APIView):
    """Print documents via the existing print system: ``variant=kot`` (kitchen
    ticket — no money on it) or ``variant=guest_check`` (items + taxes +
    totals, before settlement). Reprintable; cancelled lines never print."""

    permission_classes = [OrdersView]

    def get(self, request: Request, pk: int) -> Response:
        order = _get(ServiceOrder, request, pk)
        variant = request.query_params.get("variant", "kot")
        if variant not in ("kot", "guest_check"):
            variant = "kot"
        totals = services.order_totals(order)
        items = order.items.filter(cancelled_at__isnull=True)
        body = {
            "document": "guest_check" if variant == "guest_check" else "service_ticket",
            "hotel": _hotel_header(request.hotel),
            "order": {
                "order_number": order.order_number,
                "order_type": order.order_type,
                "outlet": order.outlet,
                "status": order.status,
                "settlement": order.settlement,
                "currency": order.currency or services._base_currency(request.hotel),
                "room_number": order.room.number if order.room else "",
                "table_number": order.table.number if order.table else "",
                "customer_name": order.customer_name,
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
                    "notes": i.notes,
                    **(
                        {
                            "unit_price": str(i.unit_price),
                            "tax_amount": str(i.tax_amount),
                            "total_amount": str(i.total_amount),
                        }
                        if variant == "guest_check"
                        else {}
                    ),
                }
                for i in items
            ],
        }
        if variant == "guest_check":
            body["totals"] = {k: str(v) for k, v in totals.items()}
        return Response(body)


# --- Overview ---------------------------------------------------------------------


class ServicesOverviewView(APIView):
    permission_classes = [OrdersView]

    def get(self, request: Request) -> Response:
        hotel = request.hotel
        # Restaurant closure: "today" is the HOTEL business date (legacy rows
        # without one fall back to their ordered_at calendar date).
        today = get_business_date(hotel)
        base = ServiceOrder.objects.filter(hotel=hotel)
        today_q = Q(business_date=today) | Q(
            business_date__isnull=True, ordered_at__date=today
        )
        today_qs = base.filter(today_q)
        by_status = {row["status"]: row["n"] for row in
                     today_qs.values("status").annotate(n=Count("id"))}
        posted_today = base.filter(posted_at__date=today).aggregate(
            total=Sum("posted_charge__total_amount")
        )["total"]
        paid_direct_today = base.filter(
            settlement=OrderSettlement.DIRECT, settled_at__date=today
        ).aggregate(total=Sum("settlement_payment__amount"))["total"]
        return Response(
            {
                "orders_today": today_qs.count(),
                "submitted": by_status.get(OrderStatus.SUBMITTED, 0),
                "preparing": by_status.get(OrderStatus.PREPARING, 0),
                "ready": by_status.get(OrderStatus.READY, 0),
                "delivered": by_status.get(OrderStatus.DELIVERED, 0),
                "delivered_not_settled": base.filter(
                    status=OrderStatus.DELIVERED,
                    settlement=OrderSettlement.UNSETTLED,
                ).count(),
                # Kept name for UI continuity: delivered orders not yet posted.
                "delivered_not_posted": base.filter(
                    status=OrderStatus.DELIVERED, posted_at__isnull=True,
                    settlement=OrderSettlement.UNSETTLED,
                ).count(),
                "posted_today_total": str(money(posted_today or 0)),
                "paid_direct_today_total": str(money(paid_direct_today or 0)),
                "active_items": ServiceItem.objects.filter(
                    hotel=hotel, is_active=True
                ).count(),
            }
        )
