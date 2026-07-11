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


class Outlet(models.TextChoices):
    """The two FIXED service outlets (final closure). No dynamic outlets."""

    RESTAURANT = "restaurant", "Restaurant"
    CAFE = "cafe", "Café"


class ServiceItemType(models.TextChoices):
    # LEGACY / DEPRECATED (final closure): superseded by the category's
    # ``outlet``. Kept read-only for old rows; never written by new logic.
    # Removal happens in a later, separate cleanup migration.
    RESTAURANT = "restaurant", "Restaurant"
    CAFE = "cafe", "Café"
    ROOM_SERVICE = "room_service", "Room service"
    OTHER = "other", "Other"


class ServiceCategory(models.Model):
    """A section of one outlet's menu. Items inherit the category's outlet."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="service_categories"
    )
    # Final closure: every category belongs to exactly ONE fixed outlet.
    outlet = models.CharField(
        max_length=16, choices=Outlet.choices, default=Outlet.RESTAURANT
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
    # LEGACY / DEPRECATED (final closure): the operational outlet now lives on
    # the CATEGORY. Kept read-only for old rows and internal compatibility;
    # never written by new logic, never shown as an operational reference.
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
    # LEGACY / DEPRECATED (final closure): superseded by ``order_type`` +
    # ``outlet``. Kept read-only for old rows; never written by new logic.
    # Removal happens in a later, separate cleanup migration.
    ROOM_SERVICE = "room_service", "Room service"
    RESTAURANT = "restaurant", "Restaurant"
    CAFE = "cafe", "Café"
    OTHER = "other", "Other"


class OrderType(models.TextChoices):
    """The two order shapes (final closure): a ROOM order lives on an
    in-house stay; a TABLE order lives on an outlet table (guest-linked or
    external customer)."""

    ROOM = "room", "Room"
    TABLE = "table", "Table"


class OrderSettlement(models.TextChoices):
    """Financial settlement state — deliberately SEPARATE from the
    operational status: "delivered" is not "paid". Settlement happens
    exactly once (XOR): direct payment or folio posting, never both."""

    UNSETTLED = "unsettled", "Unsettled"
    DIRECT = "direct", "Direct payment"
    FOLIO = "folio", "Posted to folio"


class TableStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    OUT_OF_SERVICE = "out_of_service", "Out of service"


class RestaurantTable(models.Model):
    """A simple outlet table — an ORGANIZER for orders, not a floor-plan
    system. ``occupied`` is never stored: it is DERIVED from the existence
    of one open (unsettled, non-cancelled) order on the table."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="restaurant_tables"
    )
    outlet = models.CharField(max_length=16, choices=Outlet.choices)
    number = models.CharField(max_length=20)
    name = models.CharField(max_length=120, blank=True, default="")
    capacity = models.PositiveSmallIntegerField(default=2)
    status = models.CharField(
        max_length=16, choices=TableStatus.choices, default=TableStatus.AVAILABLE
    )
    status_note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restaurant_tables_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="restaurant_tables_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "restaurant_tables"
        ordering = ["outlet", "number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "outlet", "number"],
                name="unique_table_number_per_hotel_outlet",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.outlet} table {self.number} (hotel={self.hotel_id})"


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
    # LEGACY / DEPRECATED (final closure): superseded by order_type + outlet.
    # Read-only for old rows; never written by new logic; removed from the
    # write serializers and the UI. Cleanup migration comes later.
    source = models.CharField(
        max_length=16, choices=OrderSource.choices, default=OrderSource.ROOM_SERVICE
    )
    # Final closure: the fixed shape of the order — IMMUTABLE after creation.
    order_type = models.CharField(
        max_length=8, choices=OrderType.choices, default=OrderType.ROOM
    )
    outlet = models.CharField(
        max_length=16, choices=Outlet.choices, default=Outlet.RESTAURANT
    )
    table = models.ForeignKey(
        RestaurantTable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    # External customer on a table order: a free-text name ONLY — no guest
    # profile, no customer account (documented decision).
    customer_name = models.CharField(max_length=180, blank=True, default="")
    # The HOTEL business date the order belongs to (stamped by the service;
    # NULL only on legacy rows, backfilled from ordered_at in the hotel tz).
    business_date = models.DateField(null=True, blank=True)
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
    # Final closure: settlement state — XOR enforced in the services AND by
    # the check constraint below. Never returns to unsettled.
    settlement = models.CharField(
        max_length=12,
        choices=OrderSettlement.choices,
        default=OrderSettlement.UNSETTLED,
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders_settled",
    )
    # The direct-payment receipt (transient-folio cycle). PROTECT: a payment
    # referenced by an order settlement is part of the money story.
    settlement_payment = models.ForeignKey(
        "finance.Payment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="settled_service_orders",
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
            # ONE open (unsettled, non-cancelled) order per table — the DB
            # backstop behind the table row lock in the service.
            models.UniqueConstraint(
                fields=["table"],
                condition=models.Q(
                    table__isnull=False, settled_at__isnull=True
                ) & ~models.Q(status="cancelled"),
                name="unique_open_order_per_table",
            ),
            # XOR: unsettled carries no settlement marks; direct carries a
            # payment; folio carries a posted charge. Never both, never half.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        settlement="unsettled",
                        settled_at__isnull=True,
                        settlement_payment__isnull=True,
                    )
                    | models.Q(
                        settlement="direct",
                        settled_at__isnull=False,
                        settlement_payment__isnull=False,
                    )
                    | models.Q(
                        settlement="folio",
                        settled_at__isnull=False,
                        posted_charge__isnull=False,
                        settlement_payment__isnull=True,
                    )
                ),
                name="service_order_settlement_xor",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "ordered_at"]),
            models.Index(fields=["hotel", "business_date"], name="svcorder_hotel_bizdate_idx"),
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
    # Final closure: single-item cancellation BEFORE settlement — the line is
    # never deleted; price/quantity snapshot stays; totals exclude it.
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_order_items_cancelled",
    )
    cancel_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "service_order_items"
        ordering = ["id"]

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled_at is not None

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
