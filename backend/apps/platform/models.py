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
