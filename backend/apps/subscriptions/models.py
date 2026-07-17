"""Subscription plans and hotel subscriptions (Phase 3).

These are the FIRST business models in the project. They belong to the platform
owner's scope only: the platform owner sells the SaaS to hotels via
``SubscriptionPlan`` packages and tracks each hotel's ``HotelSubscription``.

Deliberately out of scope here (later phases): payment gateways, invoices,
electronic collection, and any hotel-panel/operational feature. Nothing in this
app talks to an external service.
"""
from __future__ import annotations

from django.conf import settings
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
    # --- Phase 16 additions. The Phase 3 fields are REUSED, not duplicated:
    # slug = the plan code, price = the price for `billing_cycle`,
    # room_limit/user_limit = max rooms/staff, feature_codes = features list.
    price_yearly = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    is_public = models.BooleanField(default=True)
    max_public_bookings_per_month = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_plans"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"

    @property
    def is_in_use(self) -> bool:
        # A plan is "in use" — and so never hard-deleted, only deactivated — when
        # any subscription references it OR any subscription change request (even a
        # terminal one) targets it. Both FKs are PROTECT, so this guard turns what
        # would be a raw ProtectedError into the clean ``plan_in_use`` (409).
        return self.subscriptions.exists() or self.change_requests.exists()


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
    # Grandfathering (subscriptions final closure): the plan's terms captured
    # at the moment this subscription began. A running subscription reads its
    # price/limits/features from HERE, never from the live plan, so editing a
    # plan never changes an existing subscriber retroactively. Nullable for
    # legacy rows, which migration 0004 backfills from the live plan.
    plan_snapshot = models.JSONField(null=True, blank=True)
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
        indexes = [
            # Phase 17: the subscription enforcement consults (hotel, status)
            # on EVERY important write request — keep that lookup indexed.
            models.Index(fields=["hotel", "status"]),
        ]

    def __str__(self) -> str:
        return f"hotel={self.hotel_id} plan={self.plan_id} ({self.status})"

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    MANUAL = "manual", "Manual"
    OTHER = "other", "Other"


class PlatformSubscriptionPayment(models.Model):
    """A MANUAL record of money the platform owner received for a hotel's
    subscription (Phase 16).

    This is NOT a payment gateway and NOT the hotel's finance: it never touches
    Folio/Invoice/Payment in apps.finance, computes no taxes, and is voided
    (with a reason) rather than deleted. Amounts are Decimal only.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="subscription_payments",
    )
    subscription = models.ForeignKey(
        HotelSubscription,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    method = models.CharField(
        max_length=16, choices=PaymentMethod.choices, default=PaymentMethod.MANUAL
    )
    reference = models.CharField(max_length=140, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    received_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_payments_recorded",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_subscription_payments"
        ordering = ["-received_at", "-id"]

    def __str__(self) -> str:
        return f"hotel={self.hotel_id} {self.amount} {self.currency} ({self.method})"

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None


class ChangeRequestKind(models.TextChoices):
    NEW_SUBSCRIPTION = "new_subscription", "New subscription"
    RENEWAL = "renewal", "Renewal"
    PLAN_CHANGE = "plan_change", "Plan change"


class ChangeRequestStatus(models.TextChoices):
    UNDER_REVIEW = "under_review", "Under review"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    EXECUTED = "executed", "Executed"


# The non-terminal (OPEN) request statuses. A hotel may hold at most ONE open
# request at a time (partial-unique constraint below): the owner must accept +
# execute, reject, or the hotel must cancel, before another can be submitted.
OPEN_REQUEST_STATUSES = (
    ChangeRequestStatus.UNDER_REVIEW,
    ChangeRequestStatus.ACCEPTED,
)


class SubscriptionChangeRequest(models.Model):
    """A hotel-initiated request to change its subscription (§8.5).

    This is the ONLY hotel-driven entry into the otherwise platform-owner-driven
    subscription lifecycle. The hotel submits a request; the platform owner
    reviews it (two-step: accept, then execute). Executing calls the existing
    lifecycle service (activate / renew / change plan) so every guarantee —
    single live subscription, plan snapshot, grandfathering, events — still
    holds. There is NO payment gateway, NO external messaging and NO customer
    account here: it is an internal review record only.

    Downgrades are deliberately NOT a hotel-initiated kind (owner decision):
    a hotel may request a NEW subscription, a RENEWAL, or an UPGRADE plan change.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="subscription_requests",
    )
    kind = models.CharField(max_length=20, choices=ChangeRequestKind.choices)
    # The target plan. NULL for a renewal (the plan does not change). PROTECT for
    # new_subscription / plan_change so a plan tied to request history is never
    # hard-deleted (see SubscriptionPlan.is_in_use).
    requested_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="change_requests",
        null=True,
        blank=True,
    )
    # Audit snapshot of the live subscription the request was raised against (for
    # display + owner context). SET_NULL because subscriptions are never deleted
    # (void-not-delete), so this is a stable, non-blocking back-reference.
    current_subscription = models.ForeignKey(
        HotelSubscription,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16,
        choices=ChangeRequestStatus.choices,
        default=ChangeRequestStatus.UNDER_REVIEW,
    )
    hotel_note = models.TextField(blank=True, default="")
    # The owner's decision note / mandatory rejection reason.
    admin_note = models.TextField(blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_requests_made",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_requests_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    # The subscription produced when the request is executed (SET_NULL — history
    # is preserved and the subscription is never deleted).
    resulting_subscription = models.ForeignKey(
        HotelSubscription,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_change_requests"
        ordering = ["-created_at"]
        constraints = [
            # At most one OPEN (under_review/accepted) request per hotel.
            models.UniqueConstraint(
                fields=["hotel"],
                condition=models.Q(status__in=list(OPEN_REQUEST_STATUSES)),
                name="unique_open_request_per_hotel",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"hotel={self.hotel_id} {self.kind} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_REQUEST_STATUSES
