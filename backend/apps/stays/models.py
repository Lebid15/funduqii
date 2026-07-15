"""Stays / occupancy (Phase 7) — the physical presence of guests in rooms.

A ``Stay`` is created at **check-in** and closed at **check-out**. It is the
operational layer built *on top of* a reservation (Phase 6) and a room
(Phase 5): the front desk admits a confirmed reservation into a specific room.

Important design decisions:
- **Occupancy is DERIVED, never a manual `room.status`.** A room is "occupied"
  iff it has an active (`in_house`) stay — we do NOT add an `occupied` value to
  the Phase 5 `Room.status` (which stays for manual housekeeping states only).
- **No money.** Check-out is operational only — no folio, payment, or invoice.
  Any financial settlement is Phase 8.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class StayStatus(models.TextChoices):
    IN_HOUSE = "in_house", "In house"
    CHECKED_OUT = "checked_out", "Checked out"
    CANCELLED = "cancelled", "Cancelled"


class Stay(models.Model):
    """One guest party occupying one room, from check-in to check-out."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="stays"
    )
    # A stay is normally created from a confirmed reservation, but the FKs are
    # nullable so history survives if a reservation/line is ever removed.
    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stays",
    )
    reservation_line = models.ForeignKey(
        "reservations.ReservationRoomLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stays",
    )
    room = models.ForeignKey(
        "rooms.Room", on_delete=models.PROTECT, related_name="stays"
    )
    primary_guest = models.ForeignKey(
        "guests.Guest", on_delete=models.PROTECT, related_name="primary_stays"
    )
    status = models.CharField(
        max_length=16, choices=StayStatus.choices, default=StayStatus.IN_HOUSE
    )
    planned_check_in_date = models.DateField()
    planned_check_out_date = models.DateField()
    # STAYS ITEM-3 — the AGREED nightly rate captured ONCE at check-in from the
    # reservation line's room type (``RoomType.base_rate``). It is the single
    # source of truth for this stay's per-night room bill: a later catalog
    # change to ``base_rate`` never alters an in-progress stay's nightly charge.
    # NULL for an unpriced room type at admission, and for stays created before
    # this field existed (the night service then falls back to the live rate).
    # ``max_digits``/``decimal_places`` mirror finance ``MONEY_KW`` (12, 2).
    nightly_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    actual_check_in_at = models.DateTimeField()
    actual_check_out_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stays_checked_in",
    )
    checked_out_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stays_checked_out",
    )
    check_in_notes = models.CharField(max_length=255, blank=True, default="")
    check_out_notes = models.CharField(max_length=255, blank=True, default="")
    checkout_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stays"
        ordering = ["-actual_check_in_at", "-id"]
        constraints = [
            # A physical room can hold at most one in-house stay at a time —
            # this DB-enforces "no double occupancy".
            models.UniqueConstraint(
                fields=["room"],
                condition=models.Q(status="in_house"),
                name="unique_in_house_stay_per_room",
            ),
        ]

    def __str__(self) -> str:
        return f"stay room={self.room_id} ({self.status})"

    @property
    def nights(self) -> int:
        return (self.planned_check_out_date - self.planned_check_in_date).days


class StayGuestRole(models.TextChoices):
    PRIMARY = "primary", "Primary"
    COMPANION = "companion", "Companion"


class StayGuest(models.Model):
    """A guest attached to a stay (one primary + optional companions)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="stay_guests"
    )
    stay = models.ForeignKey(Stay, on_delete=models.CASCADE, related_name="guests")
    guest = models.ForeignKey(
        "guests.Guest", on_delete=models.PROTECT, related_name="stay_links"
    )
    role = models.CharField(
        max_length=16,
        choices=StayGuestRole.choices,
        default=StayGuestRole.COMPANION,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stay_guests"
        ordering = ["stay_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["stay", "guest"], name="unique_guest_per_stay"
            ),
            models.UniqueConstraint(
                fields=["stay"],
                condition=models.Q(role="primary"),
                name="unique_primary_guest_per_stay",
            ),
        ]

    def __str__(self) -> str:
        return f"stay={self.stay_id} guest={self.guest_id} ({self.role})"


class StayStatusLog(models.Model):
    """A lightweight per-stay status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="stay_status_logs"
    )
    stay = models.ForeignKey(
        Stay, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(
        max_length=16, choices=StayStatus.choices, blank=True, default=""
    )
    new_status = models.CharField(max_length=16, choices=StayStatus.choices)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stay_status_log_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stay_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"stay={self.stay_id} {self.previous_status}->{self.new_status}"
