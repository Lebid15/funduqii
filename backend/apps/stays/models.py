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


class StayRatePeriodSource(models.TextChoices):
    BOOKING = "booking", "Booking"
    EXTENSION = "extension", "Extension"
    OVERRIDE = "override", "Override"
    # A rate set AFTER the fact to fill a coverage gap for a stay that had no
    # reliable agreed rate (legacy data / a booking captured before this table).
    # Always audited (permission + reason); never rewrites an already-billed night.
    LEGACY_REMEDIATION = "legacy_remediation", "Legacy remediation"


class StayRatePeriod(models.Model):
    """The AGREED nightly rate for a contiguous date range of a stay.

    STAYS rate-integrity round — a stay is billed per NIGHT from the period that
    covers that night's date, NOT from a single per-stay rate. The ORIGINAL period
    (``source="booking"``) is created at check-in from the reservation line's
    booking-time snapshot (``ReservationRoomLine.agreed_nightly_rate``); an
    extension adds a new, non-overlapping period ``[old_end, new_end)``. A period's
    ``nightly_rate`` is ``NULL`` ONLY as a booking snapshot that means the agreed
    price is MISSING and MUST be remediated — it is NOT a free night: the posting
    service RAISES on a NULL-rate night (never posts zero, never falls back to the
    live ``RoomType.base_rate``). Periods per stay are non-overlapping half-open
    ranges ``[start_date, end_date)`` (``end_date`` EXCLUSIVE); the central
    rate-period service keeps them disjoint. All writes route through that service.
    ``max_digits``/``decimal_places`` mirror finance ``MONEY_KW``.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="stay_rate_periods"
    )
    stay = models.ForeignKey(
        Stay, on_delete=models.CASCADE, related_name="rate_periods"
    )
    # Half-open range: ``start_date`` inclusive, ``end_date`` EXCLUSIVE.
    start_date = models.DateField()
    end_date = models.DateField()
    # NULL == an explicitly UNPRICED period (skip posting; never a live fallback).
    nightly_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, blank=True, default="")
    source = models.CharField(
        max_length=20, choices=StayRatePeriodSource.choices
    )
    # Audit — set ONLY for an override period (a manual rate that differs from the
    # extension default), which requires a pricing/finance permission + a reason.
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stay_rate_periods_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    override_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stay_rate_periods"
        ordering = ["stay_id", "start_date", "id"]
        constraints = [
            # One period per (stay, start_date) — makes check-in / extension
            # get_or_create idempotent under a retry or concurrent poster.
            models.UniqueConstraint(
                fields=["stay", "start_date"],
                name="uniq_stay_rate_period_start",
            ),
            # FIX 5 (DB hardening): a half-open range must be non-empty, and a
            # priced period must be strictly positive (NULL stays allowed = an
            # explicitly unpriced period).
            models.CheckConstraint(
                check=models.Q(start_date__lt=models.F("end_date")),
                name="stay_rate_period_start_before_end",
            ),
            models.CheckConstraint(
                check=models.Q(nightly_rate__isnull=True)
                | models.Q(nightly_rate__gt=0),
                name="stay_rate_period_rate_positive_or_null",
            ),
            # ITEM 7 (currency hardening): a PRICED period must carry an explicit,
            # non-empty currency (NULL-rate booking snapshots may be blank).
            models.CheckConstraint(
                check=models.Q(nightly_rate__isnull=True)
                | ~models.Q(currency=""),
                name="stay_rate_period_priced_has_currency",
            ),
        ]
        indexes = [
            models.Index(fields=["stay", "start_date"]),
        ]

    def __str__(self) -> str:
        return (
            f"stay={self.stay_id} [{self.start_date}..{self.end_date}) "
            f"@ {self.nightly_rate} ({self.source})"
        )


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
