"""Shifts, shift handover and the operational daily close (Phase 12).

This is the hotel's DAILY WORK organizer — NOT attendance, NOT payroll, NOT
HR and NOT a full accounting close:

- A **Shift** is one staffer's working session with a cash drawer: opening
  float, movements attached through the finance services, and a counted
  closing amount whose difference from the expected amount requires a reason.
- A **ShiftHandover** passes an ongoing/ended shift to another member with
  summary notes and pending tasks; the recipient accepts or rejects it.
- A **DailyClose** snapshots one business date (payments, expenses, service
  postings, arrivals/departures, shifts) and locks SAFE integrated flows for
  that date. The snapshot documents; finance records stay the only source of
  financial truth.

No hard delete anywhere; money is Decimal-only; nothing here creates or
mutates finance records — attachment happens inside ``apps.finance.services``.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

MONEY_KW = dict(max_digits=12, decimal_places=2)
ZERO = Decimal("0.00")


class ShiftsNumberSequence(models.Model):
    """Per-hotel, per-kind counter for SH/HO/DC numbers (same pattern as the
    finance/service/operations sequences; kept separate on purpose)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="shifts_sequences"
    )
    kind = models.CharField(max_length=16)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "shifts_number_sequences"
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "kind"], name="unique_shifts_sequence_per_hotel"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.hotel_id}:{self.kind}={self.last_number}"


class ShiftStatus(models.TextChoices):
    OPEN = "open", "Open"
    # Reserved for a future asynchronous/night-audit close flow. Phase 12
    # closes a shift atomically in one transaction, so nothing ever sits in
    # this intermediate state (documented decision).
    CLOSING = "closing", "Closing"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"


class Shift(models.Model):
    """One working session with a cash drawer.

    A user may hold at most ONE open shift per hotel (DB-enforced). A hotel
    MAY run several open shifts at once (different staffers — documented
    decision); the daily close then requires all of them closed first.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="shifts"
    )
    shift_number = models.CharField(max_length=20)
    business_date = models.DateField()
    status = models.CharField(
        max_length=16, choices=ShiftStatus.choices, default=ShiftStatus.OPEN
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts_opened",
    )
    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shifts_responsible",
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    opening_cash_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    expected_cash_amount = models.DecimalField(**MONEY_KW, default=ZERO)
    actual_cash_amount = models.DecimalField(**MONEY_KW, null=True, blank=True)
    cash_difference = models.DecimalField(**MONEY_KW, default=ZERO)
    difference_reason = models.CharField(max_length=255, blank=True, default="")
    opening_notes = models.CharField(max_length=255, blank=True, default="")
    closing_notes = models.CharField(max_length=255, blank=True, default="")
    internal_notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shifts_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shifts"
        ordering = ["-opened_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "shift_number"],
                name="unique_shift_number_per_hotel",
            ),
            # One OPEN shift per responsible user per hotel.
            models.UniqueConstraint(
                fields=["hotel", "responsible_user"],
                condition=models.Q(status="open"),
                name="unique_open_shift_per_user_per_hotel",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
            models.Index(fields=["hotel", "business_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.shift_number} (hotel={self.hotel_id}, {self.status})"


class ShiftStatusLog(models.Model):
    """A lightweight per-shift status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="shift_status_logs"
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=16, blank=True, default="")
    new_status = models.CharField(max_length=16)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shift_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shift_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.shift_id}: {self.previous_status}->{self.new_status}"


class HandoverStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class ShiftHandover(models.Model):
    """Passing a shift's context to another member: notes, pending tasks and
    drawer remarks. Accepted handovers are frozen."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="shift_handovers"
    )
    handover_number = models.CharField(max_length=20)
    from_shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT, related_name="handovers"
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="handovers_received",
    )
    status = models.CharField(
        max_length=16, choices=HandoverStatus.choices, default=HandoverStatus.DRAFT
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True, default="")
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    summary_notes = models.CharField(max_length=255, blank=True, default="")
    pending_tasks_notes = models.CharField(max_length=255, blank=True, default="")
    cash_notes = models.CharField(max_length=255, blank=True, default="")
    guest_notes = models.CharField(max_length=255, blank=True, default="")
    maintenance_notes = models.CharField(max_length=255, blank=True, default="")
    lost_found_notes = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handovers_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handovers_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shift_handovers"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "handover_number"],
                name="unique_handover_number_per_hotel",
            ),
        ]
        indexes = [
            models.Index(fields=["hotel", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.handover_number} (hotel={self.hotel_id}, {self.status})"


class ShiftHandoverStatusLog(models.Model):
    """A lightweight per-handover status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="handover_status_logs",
    )
    handover = models.ForeignKey(
        ShiftHandover, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=16, blank=True, default="")
    new_status = models.CharField(max_length=16)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="handover_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shift_handover_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.handover_id}: {self.previous_status}->{self.new_status}"


class DailyCloseStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    CLOSED = "closed", "Closed"
    # Reserved: reopening a closed day is deliberately NOT built in Phase 12
    # (documented). The choice exists so a future reopen flow needs no schema
    # change; `daily_close.reopen` is registered but unused.
    REOPENED = "reopened", "Reopened"


class DailyClose(models.Model):
    """The operational close of one business date.

    ``snapshot_json``/``totals_json`` DOCUMENT the day; the finance records
    remain the single source of financial truth. Closing never deletes or
    rewrites anything — it locks SAFE integrated flows for that date.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="daily_closes"
    )
    close_number = models.CharField(max_length=20)
    business_date = models.DateField()
    status = models.CharField(
        max_length=16, choices=DailyCloseStatus.choices, default=DailyCloseStatus.DRAFT
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_closes_closed",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_closes_reopened",
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.CharField(max_length=255, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    snapshot_json = models.JSONField(default=dict, blank=True)
    totals_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "daily_closes"
        ordering = ["-business_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "business_date"],
                name="unique_daily_close_per_hotel_date",
            ),
            models.UniqueConstraint(
                fields=["hotel", "close_number"],
                name="unique_daily_close_number_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.close_number} {self.business_date} (hotel={self.hotel_id}, {self.status})"


class DailyCloseStatusLog(models.Model):
    """A lightweight per-close status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="daily_close_status_logs",
    )
    daily_close = models.ForeignKey(
        DailyClose, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=16, blank=True, default="")
    new_status = models.CharField(max_length=16)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_close_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "daily_close_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.daily_close_id}: {self.previous_status}->{self.new_status}"
