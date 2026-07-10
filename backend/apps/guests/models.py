"""Guests (Phase 7) — the hotel's guest directory.

A ``Guest`` is a person known to a hotel. It is scoped to a single
``tenancy.Hotel``; one hotel can never see another hotel's guests. This is a
lightweight profile only — **no document images/attachments** are stored in this
phase (deferred), and **no money** lives here.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class DocumentType(models.TextChoices):
    NATIONAL_ID = "national_id", "National ID"
    PASSPORT = "passport", "Passport"
    DRIVING_LICENSE = "driving_license", "Driving license"
    OTHER = "other", "Other"


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"
    UNSPECIFIED = "unspecified", "Unspecified"


class Guest(models.Model):
    """A guest known to a hotel (directory entry, not an account)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="guests"
    )
    full_name = models.CharField(max_length=180)
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    nationality = models.CharField(max_length=80, blank=True, default="")
    document_type = models.CharField(
        max_length=20, choices=DocumentType.choices, blank=True, default=""
    )
    document_number = models.CharField(max_length=80, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=16, choices=Gender.choices, blank=True, default=""
    )
    address = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    # --- VIP (final closure) — a simple flag, no tiers/loyalty/money. ------
    is_vip = models.BooleanField(default=False)
    vip_marked_at = models.DateTimeField(null=True, blank=True)
    vip_marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guests_vip_marked",
    )

    # --- Hotel-scoped block (final closure). The CURRENT block lives here;
    # the full history (old reasons survive an unblock) lives in
    # GuestBlockLog. Guest rows are per-hotel, so this can never leak into
    # or block another hotel.
    is_blocked = models.BooleanField(default=False)
    block_reason = models.CharField(max_length=255, blank=True, default="")
    blocked_at = models.DateTimeField(null=True, blank=True)
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guests_blocked",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guests_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guests_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "guests"
        ordering = ["full_name", "id"]
        constraints = [
            # When a document is recorded, it is unique per hotel + type. Blank
            # document numbers are allowed and never collide (partial index).
            models.UniqueConstraint(
                fields=["hotel", "document_type", "document_number"],
                condition=~models.Q(document_number=""),
                name="unique_guest_document_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} (hotel={self.hotel_id})"


class GuestBlockAction(models.TextChoices):
    BLOCKED = "blocked", "Blocked"
    UNBLOCKED = "unblocked", "Unblocked"


class GuestBlockLog(models.Model):
    """Immutable history of block/unblock actions on a guest.

    Unblocking clears the CURRENT block fields on ``Guest`` but never touches
    these rows — the old reason, actor and time survive forever.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="guest_block_logs"
    )
    guest = models.ForeignKey(
        Guest, on_delete=models.CASCADE, related_name="block_logs"
    )
    action = models.CharField(max_length=16, choices=GuestBlockAction.choices)
    # Mandatory for `blocked`; an optional note for `unblocked`.
    reason = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_block_log_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "guest_block_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"guest={self.guest_id} {self.action}"
