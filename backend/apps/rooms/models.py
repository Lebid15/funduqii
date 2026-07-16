"""Floors, room types and rooms (Phase 5) — the hotel's first operational data.

This is the physical inventory of a hotel: its floors, the room types it offers,
and the actual rooms with a basic MANUAL status. It is NOT reservations,
availability, guests, or money — those are later phases.

Everything is scoped to a ``tenancy.Hotel``. A room may only reference a floor
and a room type that belong to the SAME hotel (enforced in services/serializers).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Floor(models.Model):
    """A floor / wing within a hotel."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="floors"
    )
    name = models.CharField(max_length=120)
    number = models.CharField(max_length=32, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "floors"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.name} (hotel={self.hotel_id})"


class BedType(models.TextChoices):
    SINGLE = "single", "Single"
    DOUBLE = "double", "Double"
    TWIN = "twin", "Twin"
    KING = "king", "King"
    QUEEN = "queen", "Queen"
    SUITE = "suite", "Suite"


class RoomType(models.Model):
    """A category of room offered by a hotel (e.g. Standard Double)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="room_types"
    )
    name = models.CharField(max_length=140)
    code = models.CharField(max_length=32)
    description = models.TextField(blank=True, default="")
    base_capacity = models.PositiveSmallIntegerField(default=1)
    max_capacity = models.PositiveSmallIntegerField(default=1)
    bed_type = models.CharField(
        max_length=16, choices=BedType.choices, blank=True, default=""
    )
    amenities = models.JSONField(default=list, blank=True)
    # Reference value only — NOT a pricing/billing system (built later).
    base_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    # --- Public website display (Phase 15) --------------------------------
    # Capacity display reuses base/max_capacity (deliberate). `base_rate`
    # stays the internal reference; `public_base_price` overrides it on the
    # public site when set.
    public_is_visible = models.BooleanField(default=False)
    public_name = models.CharField(max_length=140, blank=True, default="")
    public_description = models.TextField(blank=True, default="")
    public_base_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    public_sort_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "room_types"
        ordering = ["sort_order", "name"]
        constraints = [
            # `code` is unique within a hotel (but reusable across hotels).
            models.UniqueConstraint(
                fields=["hotel", "code"], name="unique_room_type_code_per_hotel"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.code}] (hotel={self.hotel_id})"


class RoomStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    DIRTY = "dirty", "Dirty"
    CLEANING = "cleaning", "Cleaning"
    MAINTENANCE = "maintenance", "Maintenance"
    OUT_OF_SERVICE = "out_of_service", "Out of service"
    ARCHIVED = "archived", "Archived"


# Statuses that require a note when a room is moved into them.
NOTE_REQUIRED_STATUSES = (RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE)


class Room(models.Model):
    """A physical room. `status` here is MANUAL housekeeping/ops state only.

    NOTE: `reserved` / `occupied` are intentionally absent — those are
    system-derived from reservations and check-in in later phases (6/7), never a
    manual status set here.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="rooms"
    )
    floor = models.ForeignKey(
        Floor, on_delete=models.PROTECT, related_name="rooms"
    )
    room_type = models.ForeignKey(
        RoomType, on_delete=models.PROTECT, related_name="rooms"
    )
    number = models.CharField(max_length=32)
    display_name = models.CharField(max_length=140, blank=True, default="")
    # --- Per-room EFFECTIVE features (Round 2 §6.1, ADDITIVE) --------------
    # Features are NEVER copied from the type onto the room. Instead a room
    # keeps only its DELTAS against the live type list:
    #   feature_additions  = extra features this room has that its type lacks
    #   feature_exclusions = inherited type features this room removes
    # The merged, deduped, ordered result is `effective_features` (property
    # below). Empty lists (the default) reproduce the pre-§6.1 behaviour
    # exactly: the room simply mirrors its type's amenities.
    feature_additions = models.JSONField(default=list, blank=True)
    feature_exclusions = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16, choices=RoomStatus.choices, default=RoomStatus.AVAILABLE
    )
    status_note = models.CharField(max_length=255, blank=True, default="")
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_status_changes",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rooms"
        ordering = ["floor__sort_order", "number"]
        constraints = [
            # Room number is unique within a hotel (reusable across hotels).
            models.UniqueConstraint(
                fields=["hotel", "number"], name="unique_room_number_per_hotel"
            ),
        ]

    def __str__(self) -> str:
        return f"Room {self.number} (hotel={self.hotel_id})"

    @property
    def effective_features(self) -> list[str]:
        """The room's real feature list = TypeDefaults − Exclusions + Additions.

        SOLE effective-merge computation for §6.1 — reuse it everywhere
        (operational board, serializers, tests). Rules:

        * Start from the LIVE ``room_type.amenities`` IN ORDER. Because the
          type list is read live, editing a type's amenities flows to every
          room that does not exclude the changed feature — no backfill.
        * Drop any feature listed in ``feature_exclusions`` (an excluded
          feature is NEVER present in the result).
        * Append ``feature_additions`` that are not already present, in order.
        * The result is ORDERED and DEDUPED (a feature appears at most once).

        Note on ``room_type`` changes: additions/exclusions are room-scoped
        strings, so they SURVIVE a type change; the effective list simply
        recomputes against the NEW type's amenities.
        """
        exclusions = {
            f for f in (self.feature_exclusions or []) if isinstance(f, str)
        }
        result: list[str] = []
        seen: set[str] = set()
        for feature in self.room_type.amenities or []:
            if not isinstance(feature, str):
                continue
            if feature in exclusions or feature in seen:
                continue
            result.append(feature)
            seen.add(feature)
        for feature in self.feature_additions or []:
            if not isinstance(feature, str):
                continue
            # An excluded feature is NEVER included, even if a stale/direct DB
            # write left it in both lists (validation blocks this on the API).
            if feature in exclusions or feature in seen:
                continue
            result.append(feature)
            seen.add(feature)
        return result


class RoomStatusLog(models.Model):
    """A lightweight operational log of ROOM STATUS changes only.

    This is NOT a general audit log — just a per-room status history.
    """

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.CASCADE, related_name="room_status_logs"
    )
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="status_logs"
    )
    previous_status = models.CharField(max_length=16, choices=RoomStatus.choices)
    new_status = models.CharField(max_length=16, choices=RoomStatus.choices)
    note = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_status_log_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "room_status_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"room={self.room_id} {self.previous_status}->{self.new_status}"
