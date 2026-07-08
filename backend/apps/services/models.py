"""Service catalog + internal service orders (Phase 9).

Restaurant / café / room-service orders that a hotel raises for an in-house
stay (or a room) and later posts to the guest's Folio as ONE finance charge.

Deliberate boundaries:
- **No POS, no inventory, no tables, no kitchen system, no direct payment.**
  This is an internal order pad whose only financial exit is a FolioCharge
  created through ``apps.finance.services`` — money is never written here.
- **Item lines are snapshots.** ``item_name``/prices are copied onto the order
  line so later catalog edits never rewrite history. Money is Decimal-only.
- **No hard delete for history.** Orders are cancelled (with a reason), never
  deleted; catalog rows in use are deactivated instead of deleted.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

MONEY_KW = dict(max_digits=12, decimal_places=2)
ZERO = Decimal("0.00")


class ServiceNumberSequence(models.Model):
    """Per-hotel counter for service documents (mirrors the finance sequence,
    kept separate so non-financial kinds never mix into financial numbering)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="service_sequences"
    )
    kind = models.CharField(max_length=16, default="order")
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "service_number_sequences"
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "kind"], name="unique_service_sequence_per_hotel"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.hotel_id}:{self.kind}={self.last_number}"


class ServiceItemType(models.TextChoices):
    RESTAURANT = "restaurant", "Restaurant"
    CAFE = "cafe", "Café"
    ROOM_SERVICE = "room_service", "Room service"
    OTHER = "other", "Other"


class ServiceCategory(models.Model):
    """A section of the catalog (restaurant, café, room service, …)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="service_categories"
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_categories"
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "code"],
                condition=~models.Q(code=""),
                name="unique_service_category_code_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (hotel={self.hotel_id})"


class ServiceItem(models.Model):
    """A sellable service/menu item. Prices are Decimal-only."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="service_items"
    )
    category = models.ForeignKey(
        ServiceCategory, on_delete=models.PROTECT, related_name="items"
    )
    name = models.CharField(max_length=160)
    code = models.CharField(max_length=32, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    item_type = models.CharField(
        max_length=16,
        choices=ServiceItemType.choices,
        default=ServiceItemType.OTHER,
    )
    unit_price = models.DecimalField(**MONEY_KW, default=ZERO)
    currency = models.CharField(max_length=3, blank=True, default="")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    is_available = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_items"
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "code"],
                condition=~models.Q(code=""),
                name="unique_service_item_code_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (hotel={self.hotel_id})"


class OrderSource(models.TextChoices):
    ROOM_SERVICE = "room_service", "Room service"
    RESTAURANT = "restaurant", "Restaurant"
    CAFE = "cafe", "Café"
    OTHER = "other", "Other"


class OrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    PREPARING = "preparing", "Preparing"
    READY = "ready", "Ready"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class ServiceOrder(models.Model):
    """One internal service order, optionally tied to a stay and/or room.

    Posting to the folio is one-way and once-only: ``posted_charge``/
    ``posted_at`` mark it, a posted order can never be posted again nor
    cancelled — any correction is a finance-side charge void (Phase 8 rules).
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="service_orders"
    )
    order_number = models.CharField(max_length=20)
    source = models.CharField(
        max_length=16, choices=OrderSource.choices, default=OrderSource.ROOM_SERVICE
    )
    stay = models.ForeignKey(
        "stays.Stay",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders",
    )
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders",
    )
    folio = models.ForeignKey(
        "finance.Folio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders",
    )
    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.SUBMITTED
    )
    ordered_at = models.DateTimeField()
    requested_delivery_time = models.TimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders_cancelled",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    internal_notes = models.CharField(max_length=255, blank=True, default="")
    posted_charge = models.OneToOneField(
        "finance.FolioCharge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_order",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders_posted",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_orders"
        ordering = ["-ordered_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "order_number"],
                name="unique_service_order_number_per_hotel",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "ordered_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.order_number} (hotel={self.hotel_id}, {self.status})"

    @property
    def is_posted(self) -> bool:
        return self.posted_at is not None


class ServiceOrderItem(models.Model):
    """A line on an order. ``item_name``/prices are SNAPSHOTS — later catalog
    changes never affect an existing order. Totals are computed server-side."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="service_order_items"
    )
    order = models.ForeignKey(
        ServiceOrder, on_delete=models.CASCADE, related_name="items"
    )
    service_item = models.ForeignKey(
        ServiceItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )
    item_name = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit_price = models.DecimalField(**MONEY_KW, default=ZERO)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=ZERO)
    amount = models.DecimalField(**MONEY_KW, default=ZERO)
    tax_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    total_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_order_items"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.item_name} ×{self.quantity} (order={self.order_id})"


class ServiceOrderStatusLog(models.Model):
    """A lightweight per-order status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="service_order_status_logs",
    )
    order = models.ForeignKey(
        ServiceOrder, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=16, blank=True, default="")
    new_status = models.CharField(max_length=16)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_order_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "service_order_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.order_id}: {self.previous_status}->{self.new_status}"
