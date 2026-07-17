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

from datetime import time

from django.conf import settings as django_settings
from django.db import models

LANGUAGE_CHOICES = [("ar", "Arabic"), ("en", "English"), ("tr", "Turkish")]

# Effective check-out time fallback (Reservations rework). ``check_out_time``
# below stays a nullable schema field — this is NOT a DB default. It is only the
# fallback used when computing an expected-departure datetime for a hotel that
# has not configured its own check-out time. Consumed via
# ``effective_check_out_time`` by any package that derives expected departure.
DEFAULT_CHECK_OUT_TIME = time(12, 0)

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
FACILITY_TYPE_CHOICES = [
    ("hotel", "Hotel"),
    ("apartments", "Apartments"),
    ("resort", "Resort"),
    ("motel", "Motel"),
    ("guesthouse", "Guest house"),
    ("other", "Other"),
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
    # §9.3 facility type — surfaced on the public site + printing/identity.
    facility_type = models.CharField(
        max_length=20, choices=FACILITY_TYPE_CHOICES, default="hotel"
    )
    default_language = models.CharField(
        max_length=2, choices=LANGUAGE_CHOICES, default="en"
    )
    default_currency = models.CharField(max_length=3, default="USD")
    # Accepted payment currencies (Reservations rework). Multi-currency lives at
    # the PAYMENT layer only — the reservation/folio currency stays the
    # ``default_currency`` (base currency). Each entry is a 3-letter uppercase
    # ISO code. An EMPTY list means "only the default currency is accepted";
    # ``default_currency`` is ALWAYS implicitly accepted whether or not it is
    # listed here.
    accepted_currencies = models.JSONField(default=list, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")

    # Daily closing (Phase 12 final closure): the hotel's ONE stored operational
    # date. It is decoupled from the wall clock — the day advances ONLY when the
    # daily close rolls it forward by one. Nullable for legacy/new rows;
    # ``get_business_date`` falls back to the timezone-computed date (a pure
    # read, never persisted) until the first close establishes a stored value.
    business_date = models.DateField(null=True, blank=True)

    # Housekeeping final closure: when enabled, an attendant's "complete"
    # parks the task at awaiting_inspection and only a supervisor with
    # `housekeeping.inspect` can approve (room released) or reject (room
    # back to dirty, task back to in_progress). Default OFF — existing
    # hotels keep today's behavior unchanged.
    housekeeping_inspection_required = models.BooleanField(default=False)

    # Restaurant & café final closure: the two FIXED service outlets can be
    # switched off per hotel. Disabling only blocks NEW orders/tables/catalog
    # rows for that outlet (and hides its creation UI) — existing data stays
    # readable and reportable. Default ON — current hotels are unchanged.
    restaurant_enabled = models.BooleanField(default=True)
    cafe_enabled = models.BooleanField(default=True)

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

    # --- Public website publishing (Phase 15) ------------------------------
    # The PUBLIC display reuses the identity/contact/location/policy fields
    # above (deliberate — no duplicated public_* copies). Only what did not
    # exist is added here. `allow_public_booking` (Phase 4) is the public
    # booking switch.
    public_is_listed = models.BooleanField(default=False)
    public_slug = models.SlugField(
        max_length=140, unique=True, null=True, blank=True
    )
    public_booking_requires_confirmation = models.BooleanField(default=True)
    public_min_nights = models.PositiveSmallIntegerField(null=True, blank=True)
    public_max_nights = models.PositiveSmallIntegerField(null=True, blank=True)
    public_terms_text = models.TextField(blank=True, default="")
    public_sort_order = models.IntegerField(default=0)
    public_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hotel_settings"
        verbose_name = "Hotel settings"
        verbose_name_plural = "Hotel settings"

    def __str__(self) -> str:
        return f"settings(hotel={self.hotel_id})"


def effective_check_out_time(hotel_settings: "HotelSettings | None") -> time:
    """Return the effective check-out time for expected-departure math.

    Uses the hotel's configured ``check_out_time`` when set, otherwise falls
    back to :data:`DEFAULT_CHECK_OUT_TIME`. This is a pure read — it never
    persists anything and does not alter the nullable ``check_out_time`` schema.
    """
    if hotel_settings is not None and hotel_settings.check_out_time is not None:
        return hotel_settings.check_out_time
    return DEFAULT_CHECK_OUT_TIME


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


class SettingsAuditScope(models.TextChoices):
    HOTEL = "hotel", "Hotel"
    PLATFORM = "platform", "Platform"


class SettingsAuditLog(models.Model):
    """Central audit trail for settings changes (§9.17/§9.19).

    One row per settings update (hotel OR platform), recording who changed what:
    the section, the actor, and a field-level diff of previous -> new values. It
    is append-only (never edited/deleted) and holds no image bytes or secrets —
    only the changed setting fields. Hotel-scoped rows carry the tenant; platform
    rows have ``hotel = NULL`` and ``scope = platform``.
    """

    scope = models.CharField(
        max_length=16,
        choices=SettingsAuditScope.choices,
        default=SettingsAuditScope.HOTEL,
    )
    hotel = models.ForeignKey(
        "tenancy.Hotel",
        on_delete=models.CASCADE,
        related_name="settings_audit_logs",
        null=True,
        blank=True,
    )
    section = models.CharField(max_length=40)
    actor = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settings_changes",
    )
    # {field: {"old": <json>, "new": <json>}} — only the fields that changed.
    changes = models.JSONField(default=dict)
    reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "settings_audit_logs"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["hotel", "-created_at"]),
            models.Index(fields=["scope", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.section} (hotel={self.hotel_id}) @ {self.created_at:%Y-%m-%d}"
