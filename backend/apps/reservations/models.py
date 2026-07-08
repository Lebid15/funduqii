"""Reservations & availability (Phase 6) — the hotel's internal booking system.

This phase builds the reservation head, its room-type lines, a lightweight
status history, and the data the availability engine reads. It is deliberately
**not** the full guest system, not check-in/check-out, and not money:

- The reservation stores only a **snapshot** of the primary guest's contact
  details (name/phone/email). There is no ``Guest`` profile model — that is a
  later phase.
- There is no ``checked_in``/``checked_out``/``occupied`` status and no
  check-in/out endpoints — those are Phase 7.
- There are no payments, folio or invoices — those are Phase 8.

Everything is scoped to a ``tenancy.Hotel``. A reservation line may only
reference a room type that belongs to the SAME hotel (enforced in
services/serializers).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class ReservationStatus(models.TextChoices):
    HELD = "held", "Held"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


# Statuses that consume inventory. ``held`` is conditional: it only blocks while
# its ``hold_expires_at`` has not passed (evaluated lazily by the availability
# engine — see apps/reservations/availability.py). ``cancelled`` / ``expired``
# never block.
BLOCKING_STATUSES = (ReservationStatus.CONFIRMED, ReservationStatus.HELD)


class ReservationSource(models.TextChoices):
    DIRECT = "direct", "Direct"
    PHONE = "phone", "Phone"
    WALK_IN = "walk_in", "Walk-in"
    OTHER = "other", "Other"


class BookingKind(models.TextChoices):
    """The only two booking kinds the system supports (Phase 8.1).

    - ``instant``: the guest is present now / wants to move in right away.
    - ``future``: the booking is for a later date.

    There is deliberately no quick/full/basic/advanced split — one form, one
    model, two kinds.
    """

    INSTANT = "instant", "Instant"
    FUTURE = "future", "Future"


class ExpectedPaymentMethod(models.TextChoices):
    """Informational only — NOT an actual payment (finance lives in Phase 8)."""

    CASH = "cash", "Cash"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    OTHER = "other", "Other"


class Reservation(models.Model):
    """The head of a booking.

    NOTE: ``primary_guest_*`` are a lightweight SNAPSHOT only, not a guest
    profile. Reserved/occupied/checked-in states do not exist here.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="reservations"
    )
    reservation_number = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16,
        choices=ReservationStatus.choices,
        default=ReservationStatus.CONFIRMED,
    )
    source = models.CharField(
        max_length=16,
        choices=ReservationSource.choices,
        default=ReservationSource.DIRECT,
    )
    booking_kind = models.CharField(
        max_length=16,
        choices=BookingKind.choices,
        default=BookingKind.INSTANT,
    )
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    expected_arrival_time = models.TimeField(null=True, blank=True)

    # Primary guest SNAPSHOT (not a guest profile).
    primary_guest_name = models.CharField(max_length=180)
    primary_guest_phone = models.CharField(max_length=32, blank=True, default="")
    primary_guest_email = models.EmailField(blank=True, default="")
    primary_guest_nationality = models.CharField(
        max_length=100, blank=True, default=""
    )
    primary_guest_document_type = models.CharField(
        max_length=32, blank=True, default=""
    )
    primary_guest_document_number = models.CharField(
        max_length=64, blank=True, default=""
    )

    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)

    # ``notes`` are the INTERNAL notes (staff-facing); ``special_requests``
    # are guest-facing wishes. Both are optional free text.
    notes = models.TextField(blank=True, default="")
    special_requests = models.TextField(blank=True, default="")

    # Where the booking came from, as free text (e.g. an OTA/office/company
    # name). Complements the ``source`` choice field.
    booking_channel_name = models.CharField(max_length=180, blank=True, default="")

    # Informational only — the actual money lives in finance (Phase 8).
    expected_payment_method = models.CharField(
        max_length=16,
        choices=ExpectedPaymentMethod.choices,
        blank=True,
        default="",
    )

    # No-show bookkeeping (free text, optional).
    no_show_reason = models.CharField(max_length=255, blank=True, default="")

    # Cancellation bookkeeping.
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations_cancelled",
    )

    # Only meaningful while status == held.
    hold_expires_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reservations"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "reservation_number"],
                name="unique_reservation_number_per_hotel",
            ),
            models.CheckConstraint(
                check=models.Q(check_out_date__gt=models.F("check_in_date")),
                name="reservation_checkout_after_checkin",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reservation_number} (hotel={self.hotel_id})"

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    @property
    def total_guests(self) -> int:
        return self.adults + self.children


class ReservationRoomLine(models.Model):
    """A requested block of rooms of one type within a reservation."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="reservation_lines"
    )
    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="lines"
    )
    # PROTECT: a room type that is used by a reservation line cannot be hard
    # deleted (Phase 5 already blocks deleting a room type with rooms).
    room_type = models.ForeignKey(
        "rooms.RoomType", on_delete=models.PROTECT, related_name="reservation_lines"
    )
    # Phase 6.1: an OPTIONAL specific room assignment. Assigning a room does NOT
    # mean the guest has arrived — check-in is Phase 7. When set, the room must
    # belong to `room_type`, be bookable, and `quantity` must be 1.
    room = models.ForeignKey(
        "rooms.Room",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reservation_lines",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    adults = models.PositiveSmallIntegerField(null=True, blank=True)
    children = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reservation_room_lines"
        ordering = ["reservation_id", "id"]

    def __str__(self) -> str:
        return f"{self.quantity}× type={self.room_type_id} (res={self.reservation_id})"


class ReservationStatusLog(models.Model):
    """A lightweight per-reservation status history — NOT a general audit log."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="reservation_status_logs",
    )
    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(
        max_length=16, choices=ReservationStatus.choices, blank=True, default=""
    )
    new_status = models.CharField(max_length=16, choices=ReservationStatus.choices)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_status_log_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reservation_status_logs"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return (
            f"res={self.reservation_id} {self.previous_status}->{self.new_status}"
        )
