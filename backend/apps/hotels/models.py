"""Hotel settings and media (Phase 4).

This is the hotel's OWN configuration — identity, contact, location, policies,
operational defaults, and visual media — kept deliberately separate from the
minimal ``tenancy.Hotel`` tenant entity. It is NOT hotel operations: no floors,
rooms, reservations, guests, money, etc. — those are later phases.

Media (logo/cover/gallery) are stored as files via the configured storage
backend and are managed through their own endpoints, never inlined into the
settings payload and never as base64.
"""
from __future__ import annotations

from django.conf import settings as django_settings
from django.db import models

LANGUAGE_CHOICES = [("ar", "Arabic"), ("en", "English"), ("tr", "Turkish")]

SMOKING_CHOICES = [
    ("not_allowed", "Not allowed"),
    ("allowed", "Allowed"),
    ("designated", "Designated areas"),
]
PET_CHOICES = [
    ("not_allowed", "Not allowed"),
    ("allowed", "Allowed"),
    ("on_request", "On request"),
]


class HotelSettings(models.Model):
    """One settings record per hotel (OneToOne with the tenant)."""

    hotel = models.OneToOneField(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="settings",
    )

    # --- Identity ---------------------------------------------------------
    display_name = models.CharField(max_length=255, blank=True, default="")
    legal_name = models.CharField(max_length=255, blank=True, default="")
    short_description = models.CharField(max_length=280, blank=True, default="")
    description = models.TextField(blank=True, default="")
    star_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    default_language = models.CharField(
        max_length=2, choices=LANGUAGE_CHOICES, default="en"
    )
    default_currency = models.CharField(max_length=3, default="USD")
    timezone = models.CharField(max_length=64, default="UTC")

    # --- Contact ----------------------------------------------------------
    phone = models.CharField(max_length=32, blank=True, default="")
    whatsapp_number = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    website_url = models.URLField(blank=True, default="")
    facebook_url = models.URLField(blank=True, default="")
    instagram_url = models.URLField(blank=True, default="")
    # Extra/free-form links only (non-secret). Not an integration.
    social_links = models.JSONField(default=dict, blank=True)

    # --- Location ---------------------------------------------------------
    country = models.CharField(max_length=80, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    area = models.CharField(max_length=120, blank=True, default="")
    address_line = models.CharField(max_length=255, blank=True, default="")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    # Stored values only — no Google Maps API call, no geocoding in Phase 4.
    map_url = models.URLField(blank=True, default="")
    google_place_id = models.CharField(max_length=255, blank=True, default="")
    location_notes = models.CharField(max_length=255, blank=True, default="")

    # --- Policies ---------------------------------------------------------
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    cancellation_policy = models.TextField(blank=True, default="")
    child_policy = models.TextField(blank=True, default="")
    pet_policy = models.CharField(
        max_length=16, choices=PET_CHOICES, default="not_allowed"
    )
    smoking_policy = models.CharField(
        max_length=16, choices=SMOKING_CHOICES, default="not_allowed"
    )
    extra_bed_policy = models.TextField(blank=True, default="")
    important_notes = models.TextField(blank=True, default="")

    # --- Operational defaults (future settings only; NOT operations) ------
    # These are stored preferences to be honored by LATER phases. Phase 4 does
    # NOT build reservations or a public website because of these fields.
    default_booking_status = models.CharField(
        max_length=16, blank=True, default=""
    )
    allow_public_booking = models.BooleanField(default=False)
    require_guest_phone = models.BooleanField(default=True)
    require_guest_document = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hotel_settings"
        verbose_name = "Hotel settings"
        verbose_name_plural = "Hotel settings"

    def __str__(self) -> str:
        return f"settings(hotel={self.hotel_id})"


def hotel_media_upload_to(instance: "HotelMedia", filename: str) -> str:
    return f"hotels/{instance.hotel_id}/{instance.kind}/{filename}"


class MediaKind(models.TextChoices):
    LOGO = "logo", "Logo"
    COVER = "cover", "Cover"
    GALLERY = "gallery", "Gallery"


class HotelMedia(models.Model):
    """A stored image asset for a hotel. Files live in storage, not the DB."""

    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="media",
    )
    kind = models.CharField(max_length=16, choices=MediaKind.choices)
    file = models.FileField(upload_to=hotel_media_upload_to)
    alt_text = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_hotel_media",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hotel_media"
        ordering = ["kind", "sort_order", "id"]
        constraints = [
            # At most one ACTIVE logo and one ACTIVE cover per hotel.
            models.UniqueConstraint(
                fields=["hotel"],
                condition=models.Q(kind="logo", is_active=True),
                name="unique_active_logo_per_hotel",
            ),
            models.UniqueConstraint(
                fields=["hotel"],
                condition=models.Q(kind="cover", is_active=True),
                name="unique_active_cover_per_hotel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}(hotel={self.hotel_id}, id={self.pk})"
