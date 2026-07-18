"""DRF serializers for hotel settings & media (Phase 4).

Text settings and media are strictly separate: the settings serializer never
accepts or returns image data (no base64, no file fields), and media responses
carry only URLs + metadata. A settings PATCH therefore cannot touch, re-upload,
or re-validate any existing image.
"""
from __future__ import annotations

import re

from rest_framework import serializers

from .models import HotelMedia, HotelSettings, MediaKind, SettingsAuditLog

_PHONE_RE = re.compile(r"^[0-9+()\-\s]{5,32}$")
_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")


def _validate_phoneish(value: str, field: str) -> str:
    if value and not _PHONE_RE.match(value):
        raise serializers.ValidationError(
            {field: "Enter a valid phone number."}
        )
    return value


class HotelSettingsSerializer(serializers.ModelSerializer):
    """Text settings only. `hotel` and timestamps are read-only.

    A field is writable here ONLY if it belongs to a settings group
    (``settings_services.HOTEL_SETTINGS_GROUPS``) — that is what the §9.2
    sectioned UI edits and what the §9.17 audit diffs. Anything else is
    read-only, so there is never a writable-but-unaudited setting:

    - ``business_date`` is the hotel's OPERATIONAL ANCHOR. It advances only via
      the daily close (``shifts.services``); letting a settings PATCH move it
      would bypass the close cycle and corrupt every daily-derived figure
      (finance/shifts/reports/stays). Read-only here, always.
    - ``default_booking_status`` is a dead field (documented "future settings
      only; NOT operations") — §9.19 forbids surfacing/writing a setting with no
      effect.
    """

    class Meta:
        model = HotelSettings
        exclude = ["id"]
        read_only_fields = [
            "hotel",
            "created_at",
            "updated_at",
            "business_date",
            "default_booking_status",
        ]

    def validate_star_rating(self, value):
        if value is not None and not (1 <= value <= 5):
            raise serializers.ValidationError("Star rating must be between 1 and 5.")
        return value

    def validate_latitude(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError(
                "Longitude must be between -180 and 180."
            )
        return value

    def validate_default_currency(self, value):
        if value and len(value) != 3:
            raise serializers.ValidationError(
                "Currency must be a 3-letter code."
            )
        return (value or "").upper()

    def validate_accepted_currencies(self, value):
        """Normalize the accepted-currency list.

        Each entry must be a 3-letter ISO code (case-insensitive on input,
        stored uppercase). Entries are de-duplicated while preserving order.
        An empty list is valid and means "only the default currency is
        accepted"; ``default_currency`` is always implicitly accepted, so no
        entry can conflict with it.
        """
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "accepted_currencies must be a list of 3-letter codes."
            )
        cleaned: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                raise serializers.ValidationError(
                    "Each accepted currency must be a 3-letter code."
                )
            code = entry.strip().upper()
            if not _CURRENCY_CODE_RE.match(code):
                raise serializers.ValidationError(
                    f"'{entry}' is not a valid 3-letter currency code."
                )
            if code not in cleaned:
                cleaned.append(code)
        return cleaned

    def validate_default_phone_country(self, value):
        """ISO-3166-1 alpha-2, stored uppercase. Blank is allowed ("no default").
        Only the shape is validated here — not membership of a country list — so
        the setting never silently rejects a legitimate code."""
        code = (value or "").strip().upper()
        if code and (len(code) != 2 or not code.isalpha()):
            raise serializers.ValidationError(
                "Country must be a 2-letter ISO-3166-1 alpha-2 code."
            )
        return code

    def validate_social_links(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("social_links must be an object.")
        return value

    def validate(self, attrs):
        if "phone" in attrs:
            _validate_phoneish(attrs["phone"], "phone")
        if "whatsapp_number" in attrs:
            _validate_phoneish(attrs["whatsapp_number"], "whatsapp_number")
        return attrs


class SettingsAuditLogSerializer(serializers.ModelSerializer):
    """Read-only audit row: who changed which section, and the field diff."""

    actor = serializers.SerializerMethodField()

    class Meta:
        model = SettingsAuditLog
        fields = ["id", "scope", "section", "actor", "changes", "reason", "created_at"]
        read_only_fields = fields

    def get_actor(self, obj):
        return obj.actor.email if obj.actor_id else None


class HotelMediaSerializer(serializers.ModelSerializer):
    """Read representation — URL + metadata only, never file bytes/base64."""

    url = serializers.SerializerMethodField()
    uploaded_by = serializers.SerializerMethodField()

    class Meta:
        model = HotelMedia
        fields = [
            "id",
            "kind",
            "url",
            "alt_text",
            "sort_order",
            "is_active",
            "uploaded_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_url(self, obj):
        if not obj.file:
            return None
        url = obj.file.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_uploaded_by(self, obj):
        return obj.uploaded_by.email if obj.uploaded_by_id else None


class HotelMediaUploadSerializer(serializers.Serializer):
    """Write serializer for a media upload (multipart)."""

    kind = serializers.ChoiceField(choices=MediaKind.choices)
    file = serializers.FileField()
    alt_text = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class HotelMediaUpdateSerializer(serializers.Serializer):
    """Patch metadata only (never the file) — alt text, order, active flag."""

    alt_text = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )
    sort_order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)
