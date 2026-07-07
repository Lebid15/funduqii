"""Subscription plans and hotel subscriptions (Phase 3).

These are the FIRST business models in the project. They belong to the platform
owner's scope only: the platform owner sells the SaaS to hotels via
``SubscriptionPlan`` packages and tracks each hotel's ``HotelSubscription``.

Deliberately out of scope here (later phases): payment gateways, invoices,
electronic collection, and any hotel-panel/operational feature. Nothing in this
app talks to an external service.
"""
from __future__ import annotations

from django.db import models


class BillingCycle(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"
    CUSTOM = "custom", "Custom"


class SubscriptionPlan(models.Model):
    """A sellable package the platform owner offers to hotels."""

    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    billing_cycle = models.CharField(
        max_length=16,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    trial_days = models.PositiveIntegerField(default=0)
    room_limit = models.PositiveIntegerField(null=True, blank=True)
    user_limit = models.PositiveIntegerField(null=True, blank=True)
    # Organized list of feature codes (e.g. ["reservations", "reports"]).
    # Feature ENFORCEMENT is intentionally not built in Phase 3 — the operational
    # features these codes would gate do not exist yet.
    feature_codes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_plans"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    @property
    def is_in_use(self) -> bool:
        return self.subscriptions.exists()


class SubscriptionStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


# Statuses that represent a currently-binding subscription. A hotel may hold at
# most one subscription in any of these states at a time.
LIVE_STATUSES = (
    SubscriptionStatus.TRIAL,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAST_DUE,
)


class HotelSubscription(models.Model):
    """A hotel's subscription to a plan. Lifecycle is driven by services."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )
    status = models.CharField(
        max_length=16,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIAL,
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hotel_subscriptions"
        ordering = ["-created_at"]
        constraints = [
            # A hotel cannot hold two binding (live) subscriptions at once.
            models.UniqueConstraint(
                fields=["hotel"],
                condition=models.Q(status__in=list(LIVE_STATUSES)),
                name="unique_live_subscription_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"hotel={self.hotel_id} plan={self.plan_id} ({self.status})"

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES
