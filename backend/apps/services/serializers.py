"""Serializers for the service catalog and service orders (Phase 9).

Money is always serialized as strings by DRF's DecimalField; all totals are
computed server-side (never trusted from the client).
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    Outlet,
    OrderStatus,
    OrderType,
    RestaurantTable,
    ServiceCategory,
    ServiceItem,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatusLog,
    TableStatus,
)


def _reject_fields(serializer, *names):
    """Backend-decided fields (business date, legacy source/item_type) are
    refused outright so a client can never believe it controlled them."""
    provided = [n for n in names if n in (serializer.initial_data or {})]
    if provided:
        raise serializers.ValidationError(
            {name: "This field is set by the backend." for name in provided}
        )


# --- Catalog ------------------------------------------------------------------


class ServiceCategorySerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ServiceCategory
        fields = [
            "id", "outlet", "name", "code", "description", "sort_order",
            "is_active", "item_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_outlet(self, value):
        # The outlet is fixed after creation — a category never migrates
        # between the restaurant and the café menus.
        if self.instance is not None and value != self.instance.outlet:
            raise serializers.ValidationError("The outlet cannot be changed.")
        return value


class ServiceItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    outlet = serializers.CharField(source="category.outlet", read_only=True)

    # Legacy note: ``item_type`` is deprecated (superseded by the category's
    # outlet) and deliberately absent — it is neither written nor exposed.
    class Meta:
        model = ServiceItem
        fields = [
            "id", "category", "category_name", "outlet", "name", "code",
            "description", "unit_price", "currency", "tax_rate",
            "is_available", "is_active", "sort_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "category_name", "outlet", "created_at", "updated_at"]

    def validate(self, attrs):
        _reject_fields(self, "item_type")
        return attrs

    def validate_name(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price must not be negative.")
        return value

    def validate_tax_rate(self, value):
        if value < 0:
            raise serializers.ValidationError("Tax rate must not be negative.")
        return value


# --- Orders (write) -----------------------------------------------------------


class OrderItemInputSerializer(serializers.Serializer):
    service_item = serializers.IntegerField()
    quantity = serializers.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01")
    )
    notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class OrderCreateSerializer(serializers.Serializer):
    order_type = serializers.ChoiceField(choices=OrderType.choices)
    outlet = serializers.ChoiceField(choices=Outlet.choices)
    stay = serializers.IntegerField(required=False, allow_null=True)
    table = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(
        max_length=180, required=False, allow_blank=True, default=""
    )
    status = serializers.ChoiceField(
        choices=[(OrderStatus.DRAFT, "Draft"), (OrderStatus.SUBMITTED, "Submitted")],
        required=False,
        default=OrderStatus.SUBMITTED,
    )
    requested_delivery_time = serializers.TimeField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    internal_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    items = OrderItemInputSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        _reject_fields(self, "source", "business_date", "room")
        return attrs


class OrderUpdateSerializer(serializers.Serializer):
    requested_delivery_time = serializers.TimeField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    internal_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    items = OrderItemInputSerializer(many=True, required=False, allow_empty=False)

    def validate(self, attrs):
        # The shape is immutable after creation (final closure).
        _reject_fields(
            self, "source", "order_type", "outlet", "table", "stay",
            "customer_name", "business_date",
        )
        return attrs


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class OrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class OrderSettleDirectSerializer(serializers.Serializer):
    def _method_choices():  # noqa: N805 — evaluated at class-body time
        from apps.finance.models import PaymentMethod

        return PaymentMethod.choices

    method = serializers.ChoiceField(choices=_method_choices())


# --- Tables ---------------------------------------------------------------------


class RestaurantTableSerializer(serializers.ModelSerializer):
    is_occupied = serializers.BooleanField(read_only=True, default=False)
    open_order = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantTable
        fields = [
            "id", "outlet", "number", "name", "capacity", "status",
            "status_note", "is_occupied", "open_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "status_note", "is_occupied",
                            "open_order", "created_at", "updated_at"]

    def validate_outlet(self, value):
        if self.instance is not None and value != self.instance.outlet:
            raise serializers.ValidationError("The outlet cannot be changed.")
        return value

    def validate_number(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Number is required.")
        return value

    def validate_capacity(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Capacity must be at least 1.")
        return value

    def get_open_order(self, obj):
        # Annotated by the view (prefetch of the ONE open order, if any).
        order = getattr(obj, "open_order_obj", None)
        if not order:
            return None
        return {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "customer_name": order.customer_name,
            "guest_name": (
                order.stay.primary_guest.full_name if order.stay else ""
            ),
        }


class TableStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TableStatus.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


# --- Orders (read) --------------------------------------------------------------


class ServiceOrderItemSerializer(serializers.ModelSerializer):
    is_cancelled = serializers.BooleanField(read_only=True)
    cancelled_by_name = serializers.CharField(
        source="cancelled_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = ServiceOrderItem
        fields = [
            "id", "service_item", "item_name", "quantity", "unit_price",
            "tax_rate", "amount", "tax_amount", "total_amount", "notes",
            "is_cancelled", "cancelled_at", "cancelled_by_name", "cancel_reason",
        ]
        read_only_fields = fields


class OrderStatusLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = ServiceOrderStatusLog
        fields = ["id", "previous_status", "new_status", "note", "changed_by_name", "created_at"]
        read_only_fields = fields


class ServiceOrderListSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    table_number = serializers.CharField(source="table.number", read_only=True, default="")
    total = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, default=None
    )
    is_posted = serializers.BooleanField(read_only=True)

    # Legacy note: ``source`` is deprecated and deliberately absent.
    class Meta:
        model = ServiceOrder
        fields = [
            "id", "order_number", "order_type", "outlet", "status",
            "settlement", "stay", "room", "room_number", "table",
            "table_number", "customer_name", "business_date", "ordered_at",
            "requested_delivery_time", "delivered_at", "is_posted",
            "posted_at", "settled_at", "total",
        ]
        read_only_fields = fields


class ServiceOrderSerializer(serializers.ModelSerializer):
    items = ServiceOrderItemSerializer(many=True, read_only=True)
    status_logs = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    table_number = serializers.CharField(source="table.number", read_only=True, default="")
    guest_name = serializers.CharField(
        source="stay.primary_guest.full_name", read_only=True, default=""
    )
    folio_number = serializers.CharField(
        source="folio.folio_number", read_only=True, default=""
    )
    posted_charge_number = serializers.CharField(
        source="posted_charge.charge_number", read_only=True, default=""
    )
    settlement_receipt = serializers.CharField(
        source="settlement_payment.receipt_number", read_only=True, default=""
    )
    is_posted = serializers.BooleanField(read_only=True)

    # Legacy note: ``source`` is deprecated and deliberately absent.
    class Meta:
        model = ServiceOrder
        fields = [
            "id", "order_number", "order_type", "outlet", "status",
            "settlement", "stay", "room", "room_number", "table",
            "table_number", "customer_name", "business_date", "guest_name",
            "folio", "folio_number",
            "ordered_at", "requested_delivery_time", "delivered_at",
            "cancelled_at", "cancellation_reason", "notes", "internal_notes",
            "is_posted", "posted_at", "posted_charge", "posted_charge_number",
            "settled_at", "settlement_payment", "settlement_receipt",
            "items", "totals", "status_logs", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_totals(self, order):
        from .services import order_totals

        totals = order_totals(order)
        return {k: str(v) for k, v in totals.items()}

    def get_status_logs(self, order):
        logs = order.status_logs.select_related("changed_by")[:10]
        return OrderStatusLogSerializer(logs, many=True).data
