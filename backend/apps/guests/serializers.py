"""DRF serializers for guests (Phase 7 + final closure).

Hotel scoping is enforced by the views (queryset + ``hotel=request.hotel`` on
save). Field formats and per-hotel document uniqueness are validated here.

Sensitive data: the document number is MASKED at this API layer for callers
without ``guests.view_sensitive_data`` — hiding it in the frontend alone is
not protection. VIP/block flags are read-only here; they change only through
the dedicated service endpoints.
"""
from __future__ import annotations

import re

from rest_framework import serializers

from .models import Guest
from .services import mask_document

_PHONE_RE = re.compile(r"^[0-9+\-\s()]{4,32}$")


def can_view_sensitive(request) -> bool:
    from apps.rbac.services import has_hotel_permission

    user = getattr(request, "user", None)
    hotel = getattr(request, "hotel", None)
    if user is None or hotel is None:
        return False
    return has_hotel_permission(user, hotel, "guests.view_sensitive_data")


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
            "is_vip",
            "is_blocked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_vip", "is_blocked", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not can_view_sensitive(request):
            data["document_number"] = mask_document(instance.document_number)
        return data

    def validate_full_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("A guest name is required.")
        return value.strip()

    def validate_phone(self, value):
        if value and not _PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate_document_number(self, value):
        # A masked value must never round-trip back into the profile.
        if value and "•" in value:
            raise serializers.ValidationError(
                "Enter the real document number (masked values are rejected)."
            )
        return (value or "").strip()

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


class GuestBlockSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class GuestUnblockSerializer(serializers.Serializer):
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class GuestVipSerializer(serializers.Serializer):
    vip = serializers.BooleanField()
