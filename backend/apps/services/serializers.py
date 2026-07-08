"""Serializers for the service catalog and service orders (Phase 9).

Money is always serialized as strings by DRF's DecimalField; all totals are
computed server-side (never trusted from the client).
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    OrderSource,
    OrderStatus,
    ServiceCategory,
    ServiceItem,
    ServiceItemType,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderStatusLog,
)

# --- Catalog ------------------------------------------------------------------


class ServiceCategorySerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ServiceCategory
        fields = [
            "id", "name", "code", "description", "sort_order", "is_active",
            "item_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value


class ServiceItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ServiceItem
        fields = [
            "id", "category", "category_name", "name", "code", "description",
            "item_type", "unit_price", "currency", "tax_rate", "is_available",
            "is_active", "sort_order", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "category_name", "created_at", "updated_at"]

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
    source = serializers.ChoiceField(
        choices=OrderSource.choices, required=False, default=OrderSource.ROOM_SERVICE
    )
    stay = serializers.IntegerField(required=False, allow_null=True)
    room = serializers.IntegerField(required=False, allow_null=True)
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


class OrderUpdateSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=OrderSource.choices, required=False)
    requested_delivery_time = serializers.TimeField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    internal_notes = serializers.CharField(max_length=255, required=False, allow_blank=True)
    items = OrderItemInputSerializer(many=True, required=False, allow_empty=False)


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class OrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


# --- Orders (read) --------------------------------------------------------------


class ServiceOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceOrderItem
        fields = [
            "id", "service_item", "item_name", "quantity", "unit_price",
            "tax_rate", "amount", "tax_amount", "total_amount", "notes",
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
    total = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, default=None
    )
    is_posted = serializers.BooleanField(read_only=True)

    class Meta:
        model = ServiceOrder
        fields = [
            "id", "order_number", "source", "status", "stay", "room",
            "room_number", "ordered_at", "requested_delivery_time",
            "delivered_at", "is_posted", "posted_at", "total",
        ]
        read_only_fields = fields


class ServiceOrderSerializer(serializers.ModelSerializer):
    items = ServiceOrderItemSerializer(many=True, read_only=True)
    status_logs = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    room_number = serializers.CharField(source="room.number", read_only=True, default="")
    guest_name = serializers.CharField(
        source="stay.primary_guest.full_name", read_only=True, default=""
    )
    folio_number = serializers.CharField(
        source="folio.folio_number", read_only=True, default=""
    )
    posted_charge_number = serializers.CharField(
        source="posted_charge.charge_number", read_only=True, default=""
    )
    is_posted = serializers.BooleanField(read_only=True)

    class Meta:
        model = ServiceOrder
        fields = [
            "id", "order_number", "source", "status", "stay", "room",
            "room_number", "guest_name", "folio", "folio_number",
            "ordered_at", "requested_delivery_time", "delivered_at",
            "cancelled_at", "cancellation_reason", "notes", "internal_notes",
            "is_posted", "posted_at", "posted_charge", "posted_charge_number",
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
