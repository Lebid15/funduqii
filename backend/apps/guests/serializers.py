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
from .normalize import normalize_id
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
            "first_name",
            "last_name",
            "father_name",
            "mother_name",
            "phone",
            "email",
            "no_email",
            "nationality",
            "national_id",
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
        # Fail CLOSED: mask when there is NO request context OR the caller lacks
        # ``guests.view_sensitive_data``. A missing request can never be treated
        # as authorized (``can_view_sensitive(None)`` is False anyway) — this
        # matches the reservations serializers and prevents leaking the raw
        # ``national_id`` / ``document_number`` when a serializer is used out of
        # a request cycle.
        if request is None or not can_view_sensitive(request):
            # The generic document number AND the structured national ID are
            # both sensitive — mask both for callers without the permission.
            data["document_number"] = mask_document(instance.document_number)
            data["national_id"] = mask_document(instance.national_id)
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

    def validate_national_id(self, value):
        # A masked value must never round-trip back into the profile.
        if value and "•" in value:
            raise serializers.ValidationError(
                "Enter the real national ID (masked values are rejected)."
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
        # Mirror the DB partial constraint (unique_guest_national_id_per_hotel),
        # which is enforced on the NORMALIZED value, so a duplicate national ID
        # returns a clean 400, not a raw IntegrityError. Two differently-typed
        # IDs ("1234-5678" / "12345678") normalize to the same key and collide.
        national_id = attrs.get(
            "national_id", getattr(self.instance, "national_id", "")
        )
        national_id_normalized = normalize_id(national_id)
        if national_id_normalized:
            qs = Guest.objects.filter(
                hotel=hotel, national_id_normalized=national_id_normalized
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"national_id": "A guest with this national ID already exists."}
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
