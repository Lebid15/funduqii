"""Daily room operations (Phase 10): housekeeping, maintenance, lost & found.

These are the operational workflows around the physical rooms — NOT shifts,
daily close, reports, inventory or purchasing (all explicitly deferred).

Deliberate boundaries:
- **Room.status is never written here.** Every room status change goes through
  ``apps.rooms.services.change_room_status`` (the Phase 5 controlled path) from
  ``apps.operations.services`` only — views never touch a room.
- **Occupancy stays derived from Stay.** There is no `occupied` room status and
  nothing in this app introduces one.
- **No hard delete for history.** Tasks/requests/items are cancelled or closed
  (with reasons where required), never deleted — there are no DELETE endpoints.
- **No money.** Nothing here writes finance records.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class OperationsNumberSequence(models.Model):
    """Per-hotel, per-kind counter for operational document numbers (mirrors
    the finance/service sequences; kept separate so operational numbering
    never mixes into financial numbering)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="operations_sequences"
    )
    kind = models.CharField(max_length=16)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "operations_number_sequences"
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "kind"], name="unique_operations_sequence_per_hotel"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.hotel_id}:{self.kind}={self.last_number}"


class OperationPriority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


# --- Housekeeping -------------------------------------------------------------


class HousekeepingTaskType(models.TextChoices):
    CHECKOUT_CLEANING = "checkout_cleaning", "Check-out cleaning"
    DAILY_CLEANING = "daily_cleaning", "Daily cleaning"
    DEEP_CLEANING = "deep_cleaning", "Deep cleaning"
    INSPECTION = "inspection", "Inspection"
    OTHER = "other", "Other"


class HousekeepingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In progress"
    # Final closure: parked here when the hotel requires supervisor
    # inspection — approve completes it, reject sends it back to work.
    AWAITING_INSPECTION = "awaiting_inspection", "Awaiting inspection"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class HousekeepingServiceOutcome(models.TextChoices):
    """The service result recorded when a cleaning task is COMPLETED.

    These four are the ONLY terminal outcomes. ``come_back_later`` is NOT one
    of them — it is a separate, non-terminal event that leaves the task active
    (see ``services.come_back_later_housekeeping_task``). The outcome is a pure
    record of what happened in the room; it NEVER drives room status (occupancy
    stays derived from the in-house Stay).
    """

    CLEANED = "cleaned", "Cleaned"
    GUEST_REFUSED = "guest_refused", "Guest refused"
    DO_NOT_DISTURB = "do_not_disturb", "Do not disturb"
    NO_ACCESS = "no_access", "No access"


class HousekeepingTask(models.Model):
    """A cleaning / preparation task for one room.

    The room is REQUIRED at creation (enforced in the service/serializer) but
    the FK is SET_NULL so historical tasks survive later room deletion.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="housekeeping_tasks"
    )
    task_number = models.CharField(max_length=20)
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_tasks",
    )
    stay = models.ForeignKey(
        "stays.Stay",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_tasks",
    )
    task_type = models.CharField(
        max_length=32,
        choices=HousekeepingTaskType.choices,
        default=HousekeepingTaskType.DAILY_CLEANING,
    )
    status = models.CharField(
        max_length=20,
        choices=HousekeepingStatus.choices,
        default=HousekeepingStatus.PENDING,
    )
    priority = models.CharField(
        max_length=16,
        choices=OperationPriority.choices,
        default=OperationPriority.NORMAL,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_tasks_assigned",
    )
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # The terminal service result, set at completion (blank until then). One of
    # HousekeepingServiceOutcome; NEVER a room status and NEVER `come_back_later`
    # (that is a separate non-terminal event, not an outcome value).
    service_outcome = models.CharField(
        max_length=20,
        choices=HousekeepingServiceOutcome.choices,
        blank=True,
        default="",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    internal_notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_tasks_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_tasks_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_tasks"
        ordering = ["-requested_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "task_number"],
                name="unique_housekeeping_task_number_per_hotel",
            ),
            # Final closure (WP2): at most ONE ACTIVE cleaning task per
            # (hotel, room). ACTIVE = pending / assigned / in_progress /
            # awaiting_inspection (mirrors services.ACTIVE_HK_STATUSES).
            # completed / cancelled are excluded so a room can start a fresh
            # cycle once its task closes. Scoped to room IS NOT NULL so a
            # historical task whose room was later deleted (SET_NULL) is never
            # constrained. Implemented as a partial UNIQUE index — portable on
            # SQLite (dev/tests) and PostgreSQL (production, authoritative).
            models.UniqueConstraint(
                fields=["hotel", "room"],
                condition=Q(
                    status__in=[
                        HousekeepingStatus.PENDING,
                        HousekeepingStatus.ASSIGNED,
                        HousekeepingStatus.IN_PROGRESS,
                        HousekeepingStatus.AWAITING_INSPECTION,
                    ]
                )
                & Q(room__isnull=False),
                name="uniq_active_housekeeping_task_per_room",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "requested_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.task_number} (hotel={self.hotel_id}, {self.status})"


class HousekeepingTaskStatusLog(models.Model):
    """A lightweight per-task status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="housekeeping_status_logs",
    )
    task = models.ForeignKey(
        HousekeepingTask, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=20, blank=True, default="")
    new_status = models.CharField(max_length=20)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_task_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.task_id}: {self.previous_status}->{self.new_status}"


# --- Maintenance ----------------------------------------------------------------


class MaintenanceCategory(models.TextChoices):
    ELECTRICAL = "electrical", "Electrical"
    PLUMBING = "plumbing", "Plumbing"
    HVAC = "hvac", "HVAC"
    FURNITURE = "furniture", "Furniture"
    CLEANING_ISSUE = "cleaning_issue", "Cleaning issue"
    SAFETY = "safety", "Safety"
    OTHER = "other", "Other"


class MaintenanceStatus(models.TextChoices):
    OPEN = "open", "Open"
    ASSIGNED = "assigned", "Assigned"
    IN_PROGRESS = "in_progress", "In progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"


class RoomBlockStatus(models.TextChoices):
    NONE = "none", "None"
    MAINTENANCE = "maintenance", "Maintenance"
    OUT_OF_SERVICE = "out_of_service", "Out of service"


class MaintenanceRequest(models.Model):
    """A maintenance request, optionally tied to a room and/or a stay.

    If it affects room availability the room is moved to ``maintenance`` /
    ``out_of_service`` through the controlled Phase 5 status service. Closing
    NEVER auto-releases the room — the closer explicitly chooses the next room
    status (dirty / available / keep).
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="maintenance_requests"
    )
    request_number = models.CharField(max_length=20)
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests",
    )
    stay = models.ForeignKey(
        "stays.Stay",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests",
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=16,
        choices=MaintenanceCategory.choices,
        default=MaintenanceCategory.OTHER,
    )
    priority = models.CharField(
        max_length=16,
        choices=OperationPriority.choices,
        default=OperationPriority.NORMAL,
    )
    status = models.CharField(
        max_length=16,
        choices=MaintenanceStatus.choices,
        default=MaintenanceStatus.OPEN,
    )
    affects_room_availability = models.BooleanField(default=False)
    room_block_status = models.CharField(
        max_length=16,
        choices=RoomBlockStatus.choices,
        default=RoomBlockStatus.NONE,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests_assigned",
    )
    reported_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    resolution_notes = models.TextField(blank=True, default="")
    internal_notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "maintenance_requests"
        ordering = ["-reported_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "request_number"],
                name="unique_maintenance_request_number_per_hotel",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "reported_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.request_number} (hotel={self.hotel_id}, {self.status})"


class MaintenanceRequestStatusLog(models.Model):
    """A lightweight per-request status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="maintenance_status_logs",
    )
    request = models.ForeignKey(
        MaintenanceRequest, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=16, blank=True, default="")
    new_status = models.CharField(max_length=16)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "maintenance_request_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.request_id}: {self.previous_status}->{self.new_status}"


# --- Lost & Found -----------------------------------------------------------------


class LostFoundCategory(models.TextChoices):
    ELECTRONICS = "electronics", "Electronics"
    DOCUMENTS = "documents", "Documents"
    CLOTHING = "clothing", "Clothing"
    JEWELRY = "jewelry", "Jewelry"
    MONEY = "money", "Money"
    LUGGAGE = "luggage", "Luggage"
    OTHER = "other", "Other"


class LostFoundStatus(models.TextChoices):
    FOUND = "found", "Found"
    STORED = "stored", "Stored"
    CLAIMED = "claimed", "Claimed"
    RETURNED = "returned", "Returned"
    DISPOSED = "disposed", "Disposed"
    CLOSED = "closed", "Closed"


class LostFoundItem(models.Model):
    """A found item, optionally linked to a room / stay / guest.

    Phase 10 stores text records only — no photos, no file uploads, no
    barcodes (explicitly deferred).
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="lost_found_items"
    )
    item_number = models.CharField(max_length=20)
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=16,
        choices=LostFoundCategory.choices,
        default=LostFoundCategory.OTHER,
    )
    status = models.CharField(
        max_length=16,
        choices=LostFoundStatus.choices,
        default=LostFoundStatus.FOUND,
    )
    found_at = models.DateTimeField(default=timezone.now)
    found_location = models.CharField(max_length=160, blank=True, default="")
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_found_items",
    )
    stay = models.ForeignKey(
        "stays.Stay",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_found_items",
    )
    guest = models.ForeignKey(
        "guests.Guest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_found_items",
    )
    found_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_found_items_found",
    )
    stored_location = models.CharField(max_length=160, blank=True, default="")
    claimed_by_name = models.CharField(max_length=180, blank=True, default="")
    claimed_by_phone = models.CharField(max_length=32, blank=True, default="")
    claimed_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    disposed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    internal_notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_found_items_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_found_items_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "lost_found_items"
        ordering = ["-found_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "item_number"],
                name="unique_lost_found_item_number_per_hotel",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "found_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.item_number} (hotel={self.hotel_id}, {self.status})"


class LostFoundItemStatusLog(models.Model):
    """A lightweight per-item status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="lost_found_status_logs",
    )
    item = models.ForeignKey(
        LostFoundItem, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=16, blank=True, default="")
    new_status = models.CharField(max_length=16)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_found_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lost_found_item_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.item_id}: {self.previous_status}->{self.new_status}"
