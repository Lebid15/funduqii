"""Guests (Phase 7) — the hotel's guest directory.

A ``Guest`` is a person known to a hotel. It is scoped to a single
``tenancy.Hotel``; one hotel can never see another hotel's guests. This is a
lightweight profile only — **no document images/attachments** are stored in this
phase (deferred), and **no money** lives here.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from .normalize import normalize_document, normalize_id, normalize_phone


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
    # ``full_name`` stays the legal/display field. Structured parts below are
    # additive (reservations-form rework) — legacy ``full_name`` is NEVER
    # auto-split into them.
    full_name = models.CharField(max_length=180)
    first_name = models.CharField(max_length=80, blank=True, default="")
    last_name = models.CharField(max_length=80, blank=True, default="")
    father_name = models.CharField(max_length=80, blank=True, default="")
    mother_name = models.CharField(max_length=80, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    # The guest explicitly has no email (distinct from "not captured yet").
    no_email = models.BooleanField(default=False)
    nationality = models.CharField(max_length=80, blank=True, default="")
    # Structured national identifier (kept alongside the generic document
    # fields). Uniqueness is enforced per hotel by a PARTIAL constraint below.
    national_id = models.CharField(max_length=80, blank=True, default="")
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

    # Canonical, index-backed lookup keys kept in sync on every save (see
    # ``save`` below). Never edited directly; derived from ``phone`` /
    # ``national_id`` so exact lookup ignores spacing / punctuation.
    phone_normalized = models.CharField(
        max_length=32, blank=True, default="", db_index=True
    )
    national_id_normalized = models.CharField(
        max_length=80, blank=True, default="", db_index=True
    )
    # Canonical document-number key (fold + uppercase + alphanumeric-only),
    # kept in sync on every save. The per-hotel document uniqueness constraint is
    # enforced on THIS normalized key (not the raw number) so "AB-123" / "ab123"
    # cannot both persist and then collide on lookup.
    document_number_normalized = models.CharField(
        max_length=80, blank=True, default="", db_index=True
    )

    class Meta:
        db_table = "guests"
        ordering = ["full_name", "id"]
        constraints = [
            # When a document is recorded, it is unique per hotel + type —
            # enforced on the NORMALIZED number. Blank numbers are allowed and
            # never collide (partial index). Passport stays a normal
            # ``document_type='passport'`` row keyed by this normalized number.
            models.UniqueConstraint(
                fields=["hotel", "document_type", "document_number_normalized"],
                condition=~models.Q(document_number_normalized=""),
                name="unique_guest_document_normalized_per_hotel",
            ),
            # When a national ID is recorded, it is unique per hotel — enforced
            # on the NORMALIZED key so "1234-5678" and "12345678" cannot both
            # persist and then collide on lookup. This uniqueness is LIFETIME
            # (not is_active-scoped): a national id / passport identity stays
            # reserved even after a profile is deactivated. Blank IDs are allowed
            # and never collide (partial index).
            models.UniqueConstraint(
                fields=["hotel", "national_id_normalized"],
                condition=~models.Q(national_id_normalized=""),
                name="unique_guest_national_id_per_hotel",
            ),
            # A phone number is unique per hotel only among ACTIVE profiles: a
            # deactivated guest never blocks reusing the same phone for a live
            # profile. Blank phones never collide (partial index).
            models.UniqueConstraint(
                fields=["hotel", "phone_normalized"],
                condition=models.Q(is_active=True) & ~models.Q(phone_normalized=""),
                name="unique_guest_phone_per_hotel_active",
            ),
        ]

    def save(self, *args, **kwargs):
        # Keep the normalized lookup keys in sync on EVERY save (create,
        # full update, or targeted update_fields). Doing it here — not in the
        # serializer — guarantees the keys are always correct regardless of the
        # write path.
        self.phone_normalized = normalize_phone(self.phone)
        self.national_id_normalized = normalize_id(self.national_id)
        self.document_number_normalized = normalize_document(self.document_number)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if "phone" in update_fields:
                update_fields.add("phone_normalized")
            if "national_id" in update_fields:
                update_fields.add("national_id_normalized")
            if "document_number" in update_fields:
                update_fields.add("document_number_normalized")
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

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
        Guest, on_delete=models.PROTECT, related_name="block_logs"
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
