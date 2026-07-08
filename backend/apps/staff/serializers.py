"""Serializers for staff & permissions management (Phase 11).

Write serializers validate SHAPE only; every business rule (uniqueness,
last-manager protection, escalation guard, registry validation) lives in the
domain services. Passwords are write-only and never serialized back.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.tenancy.models import HotelMembership


class StaffListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    is_manager = serializers.BooleanField(read_only=True)
    permission_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = HotelMembership
        fields = [
            "id", "user_id", "full_name", "email", "phone", "membership_type",
            "is_manager", "is_active", "job_title", "staff_code",
            "permission_count", "created_at",
        ]
        read_only_fields = fields


class StaffDetailSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    is_manager = serializers.BooleanField(read_only=True)
    permissions = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=""
    )
    updated_by_name = serializers.CharField(
        source="updated_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = HotelMembership
        fields = [
            "id", "user_id", "full_name", "email", "phone", "membership_type",
            "is_manager", "is_active", "is_primary_manager", "job_title",
            "staff_code", "notes", "deactivated_at", "deactivation_reason",
            "permissions", "created_by_name", "updated_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_permissions(self, membership) -> list[str]:
        return sorted(
            membership.permission_grants.values_list("code", flat=True)
        )


class StaffCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    staff_code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, default=list
    )


class LinkExistingUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    staff_code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, default=list
    )


class StaffUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, required=False)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    job_title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    staff_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DeactivateSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class PermissionsPutSerializer(serializers.Serializer):
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=64), allow_empty=True
    )


class ResetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, write_only=True)
