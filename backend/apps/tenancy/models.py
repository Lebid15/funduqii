"""Minimal multi-tenant foundation for Phase 2.

This is intentionally the *smallest* model needed to attach users to hotels so
we can enforce isolation and permissions. It is NOT hotel management: no
settings, images, public profile, packages, or subscriptions here — those come
in their own phases.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class HotelStatus(models.TextChoices):
    SETUP = "setup", "Setup"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class Hotel(models.Model):
    """A tenant. Minimal foundation only."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=140, unique=True)
    status = models.CharField(
        max_length=16,
        choices=HotelStatus.choices,
        default=HotelStatus.SETUP,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hotels"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class MembershipType(models.TextChoices):
    MANAGER = "manager", "Manager"
    STAFF = "staff", "Staff"


class HotelMembership(models.Model):
    """Links a user to a hotel with a membership type. A manager holds all of
    the hotel's permissions by default; staff hold only granted permissions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="hotel_memberships",
    )
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    membership_type = models.CharField(
        max_length=16,
        choices=MembershipType.choices,
        default=MembershipType.STAFF,
    )
    is_active = models.BooleanField(default=True)
    is_primary_manager = models.BooleanField(default=False)
    # Descriptive staff fields (Phase 11). `job_title` is a DESCRIPTIVE label
    # only — it never grants or restricts access; permission grants are the
    # single source of truth for what a member can do.
    job_title = models.CharField(max_length=120, blank=True, default="")
    staff_code = models.CharField(max_length=32, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivation_reason = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hotel_users"
        ordering = ["hotel_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "hotel"],
                name="unique_user_hotel_membership",
            ),
            models.UniqueConstraint(
                fields=["hotel"],
                condition=models.Q(is_primary_manager=True),
                name="unique_primary_manager_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.hotel_id} ({self.membership_type})"

    @property
    def is_manager(self) -> bool:
        return self.membership_type == MembershipType.MANAGER
