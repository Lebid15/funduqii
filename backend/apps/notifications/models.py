"""Internal notifications + activity center (Phase 14).

Deliberate boundaries:
- **No external channels.** Nothing here sends WhatsApp, email, SMS or push —
  notifications live INSIDE the hotel console only.
- **ActivityEvent is a simplified operational feed for the UI** — it is NOT a
  legal/compliance audit log and NOT a replacement for the per-record status
  logs the earlier phases keep.
- **Nothing here mutates operational data.** Events/notifications are created
  exclusively through the central service (``apps.notifications.services``)
  which domain services call — never ad hoc from views.
- **No hard delete.** Notifications are read/archived; activity is append-only.
- ``related_url`` is an INTERNAL path only and ``metadata_json`` is scrubbed
  of secret-looking keys before storage (enforced in the service).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationsNumberSequence(models.Model):
    """Per-hotel, per-kind counter for ACT/NTF numbers (same pattern as the
    finance/service/operations/shifts sequences; kept separate on purpose)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="notifications_sequences",
    )
    kind = models.CharField(max_length=16)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "notifications_number_sequences"
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "kind"],
                name="unique_notifications_sequence_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.hotel_id}:{self.kind}={self.last_number}"


class ActivityCategory(models.TextChoices):
    RESERVATION = "reservation", "Reservation"
    STAY = "stay", "Stay"
    GUEST = "guest", "Guest"
    ROOM = "room", "Room"
    FINANCE = "finance", "Finance"
    SERVICE = "service", "Service"
    OPERATION = "operation", "Operation"
    SHIFT = "shift", "Shift"
    STAFF = "staff", "Staff"
    REPORT = "report", "Report"
    SYSTEM = "system", "System"


class ActivitySeverity(models.TextChoices):
    INFO = "info", "Info"
    SUCCESS = "success", "Success"
    WARNING = "warning", "Warning"
    DANGER = "danger", "Danger"


class NotificationScope(models.TextChoices):
    """Who the event/notification is FOR. ``hotel`` (the default and every
    legacy row) stays inside the hotel console; ``platform`` is addressed to the
    platform owner's own centre and never appears in a hotel console. ``hotel``
    is always kept as a safe reference even on a platform-scoped row (so the
    owner can open the right hotel), so ``hotel`` is never nullable."""

    HOTEL = "hotel", "Hotel"
    PLATFORM = "platform", "Platform"


class ActivityEvent(models.Model):
    """One operational event inside a hotel — the activity-center feed row."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="activity_events"
    )
    scope = models.CharField(
        max_length=16,
        choices=NotificationScope.choices,
        default=NotificationScope.HOTEL,
    )
    event_number = models.CharField(max_length=20)
    event_type = models.CharField(max_length=64)
    category = models.CharField(
        max_length=16,
        choices=ActivityCategory.choices,
        default=ActivityCategory.SYSTEM,
    )
    severity = models.CharField(
        max_length=16,
        choices=ActivitySeverity.choices,
        default=ActivitySeverity.INFO,
    )
    title = models.CharField(max_length=200)
    message = models.CharField(max_length=255, blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_events_acted",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_events_targeted",
    )
    related_object_type = models.CharField(max_length=64, blank=True, default="")
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    related_url = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activity_events"
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "event_number"],
                name="unique_activity_event_number_per_hotel",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "category"]),
            models.Index(fields=["hotel", "occurred_at"]),
            models.Index(fields=["scope", "hotel", "occurred_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_number} {self.event_type} (hotel={self.hotel_id})"


class Notification(models.Model):
    """An in-app notification addressed to ONE hotel member. Recipients see
    only their own inbox; managers get the wider picture through the activity
    center — never through other people's inboxes."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="notifications"
    )
    scope = models.CharField(
        max_length=16,
        choices=NotificationScope.choices,
        default=NotificationScope.HOTEL,
    )
    notification_number = models.CharField(max_length=20)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hotel_notifications",
    )
    activity = models.ForeignKey(
        ActivityEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    category = models.CharField(
        max_length=16,
        choices=ActivityCategory.choices,
        default=ActivityCategory.SYSTEM,
    )
    severity = models.CharField(
        max_length=16,
        choices=ActivitySeverity.choices,
        default=ActivitySeverity.INFO,
    )
    title = models.CharField(max_length=200)
    message = models.CharField(max_length=255, blank=True, default="")
    related_url = models.CharField(max_length=255, blank=True, default="")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    # Optional idempotency key (subscriptions/notifications closure). When set,
    # a recipient can hold at most ONE notification per key — a re-emitted event
    # (e.g. a subscription lifecycle event to the platform owner) never
    # duplicates. NULL keeps the legacy behaviour (a fresh row every time). The
    # key itself carries all scope dimensions, so the constraint is per
    # (recipient, dedup_key) only.
    dedup_key = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "hotel_notifications"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "notification_number"],
                name="unique_notification_number_per_hotel",
            ),
            models.UniqueConstraint(
                fields=["recipient", "dedup_key"],
                condition=models.Q(dedup_key__isnull=False),
                name="unique_notification_dedup_per_recipient",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "recipient", "is_read"]),
            models.Index(fields=["hotel", "recipient", "is_archived"]),
            models.Index(fields=["recipient", "scope", "is_read"]),
            models.Index(fields=["recipient", "scope", "is_archived"]),
            models.Index(fields=["recipient", "scope", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.notification_number} -> user={self.recipient_id} ({self.hotel_id})"
