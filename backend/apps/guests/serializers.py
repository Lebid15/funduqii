"""DRF serializers for guests (Phase 7).

Hotel scoping is enforced by the views (queryset + ``hotel=request.hotel`` on
save). Field formats and per-hotel document uniqueness are validated here.
"""
from __future__ import annotations

import re

from rest_framework import serializers

from .models import Guest

_PHONE_RE = re.compile(r"^[0-9+\-\s()]{4,32}$")


class GuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guest
        fields = [
            "id",
            "full_name",
            "phone",
            "email",
            "nationality",
            "document_type",
            "document_number",
            "date_of_birth",
            "gender",
            "address",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_full_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("A guest name is required.")
        return value.strip()

    def validate_phone(self, value):
        if value and not _PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate(self, attrs):
        hotel = self.context["request"].hotel
        doc_type = attrs.get(
            "document_type", getattr(self.instance, "document_type", "")
        )
        doc_number = attrs.get(
            "document_number", getattr(self.instance, "document_number", "")
        )
        if doc_number:
            qs = Guest.objects.filter(
                hotel=hotel, document_type=doc_type, document_number=doc_number
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"document_number": "A guest with this document already exists."}
                )
        return attrs
