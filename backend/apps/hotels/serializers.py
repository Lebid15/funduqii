"""DRF serializers for hotel settings & media (Phase 4).

Text settings and media are strictly separate: the settings serializer never
accepts or returns image data (no base64, no file fields), and media responses
carry only URLs + metadata. A settings PATCH therefore cannot touch, re-upload,
or re-validate any existing image.
"""
from __future__ import annotations

import re

from rest_framework import serializers

from .models import HotelMedia, HotelSettings, MediaKind

_PHONE_RE = re.compile(r"^[0-9+()\-\s]{5,32}$")


def _validate_phoneish(value: str, field: str) -> str:
    if value and not _PHONE_RE.match(value):
        raise serializers.ValidationError(
            {field: "Enter a valid phone number."}
        )
    return value


class HotelSettingsSerializer(serializers.ModelSerializer):
    """Text settings only. `hotel` and timestamps are read-only."""

    class Meta:
        model = HotelSettings
        exclude = ["id"]
        read_only_fields = ["hotel", "created_at", "updated_at"]

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
