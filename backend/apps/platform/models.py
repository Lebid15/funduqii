"""Platform-level settings (Phase 3).

A single row of basic configuration the platform owner controls. Deliberately
limited: this is NOT the public-website configuration (content, header, images,
SEO) and NOT real integration settings (maps keys, WhatsApp) — those belong to
the public-website and integrations phases. Values here are plain configuration,
no secrets.
"""
from __future__ import annotations

from django.db import models


class PlatformSettings(models.Model):
    """Singleton settings row (always pk=1)."""

    platform_name = models.CharField(max_length=140, default="Funduqii")
    support_email = models.EmailField(blank=True, default="")
    support_phone = models.CharField(max_length=32, blank=True, default="")
    # Stored as a plain value only; no real WhatsApp integration in Phase 3.
    support_whatsapp = models.CharField(max_length=32, blank=True, default="")
    website_url = models.URLField(blank=True, default="")
    default_language = models.CharField(
        max_length=2,
        choices=[("ar", "Arabic"), ("en", "English"), ("tr", "Turkish")],
        default="en",
    )
    default_currency = models.CharField(max_length=3, default="USD")
    default_trial_days = models.PositiveIntegerField(default=14)
    # Reserved switches — surfaced now, enforced in their own later phases.
    allow_public_registration = models.BooleanField(default=False)
    maintenance_mode = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_settings"
        verbose_name = "Platform settings"
        verbose_name_plural = "Platform settings"

    def __str__(self) -> str:
        return self.platform_name

    def save(self, *args, **kwargs):
        # Enforce the singleton: there is only ever one settings row.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "PlatformSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def _blank_i18n() -> dict:
    """Default value for a translatable text override: empty per locale.

    An empty string means "use the built-in translation from the frontend
    dictionaries" — the owner only overrides what they want to change.
    """
    return {"ar": "", "en": "", "tr": ""}


class PlatformPublicSettings(models.Model):
    """Singleton admin controls for the PUBLIC website (Phase 16).

    Deliberately NOT a CMS: no page builder, no drag/drop, no rich editor.
    Label texts are per-locale overrides (ar/en/tr) that fall back to the
    built-in dictionary translations when left empty. Everything here is
    public by design — no secrets may live in this model.
    """

    # --- Header: link/button visibility + label overrides -------------------
    show_home_link = models.BooleanField(default=True)
    show_hotels_link = models.BooleanField(default=True)
    show_contact_link = models.BooleanField(default=True)
    show_book_now_button = models.BooleanField(default=True)
    show_trial_button = models.BooleanField(default=True)
    header_home_label = models.JSONField(default=_blank_i18n, blank=True)
    header_hotels_label = models.JSONField(default=_blank_i18n, blank=True)
    header_contact_label = models.JSONField(default=_blank_i18n, blank=True)
    header_book_now_label = models.JSONField(default=_blank_i18n, blank=True)
    header_trial_label = models.JSONField(default=_blank_i18n, blank=True)

    # --- Hero / home ---------------------------------------------------------
    hero_title = models.JSONField(default=_blank_i18n, blank=True)
    hero_subtitle = models.JSONField(default=_blank_i18n, blank=True)
    hero_primary_button_label = models.JSONField(default=_blank_i18n, blank=True)
    hero_primary_button_url = models.CharField(max_length=300, blank=True, default="")
    hero_secondary_button_label = models.JSONField(default=_blank_i18n, blank=True)
    hero_secondary_button_url = models.CharField(max_length=300, blank=True, default="")

    # --- Public platform contact ---------------------------------------------
    public_phone = models.CharField(max_length=32, blank=True, default="")
    public_whatsapp_display = models.CharField(max_length=32, blank=True, default="")
    public_email = models.EmailField(blank=True, default="")
    public_address = models.CharField(max_length=255, blank=True, default="")
    facebook_url = models.URLField(blank=True, default="")
    instagram_url = models.URLField(blank=True, default="")
    website_url = models.URLField(blank=True, default="")

    # --- Footer ---------------------------------------------------------------
    footer_text = models.JSONField(default=_blank_i18n, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_public_settings"
        verbose_name = "Platform public settings"
        verbose_name_plural = "Platform public settings"

    def __str__(self) -> str:
        return "Public site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "PlatformPublicSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
