"""Serialization helpers and the JWT token serializer for accounts.

Output is snake_case (DRF default). The frontend mirrors these shapes as
API DTOs.
"""
from __future__ import annotations

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class FunduqiiTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds the account type as a claim. Inactive users are rejected by the
    parent serializer (authentication fails with ``no_active_account``)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["account_type"] = user.account_type
        return token


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "avatar_url": user.avatar_url,
        "account_type": user.account_type,
        "is_platform_owner": user.is_platform_owner,
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def serialize_membership_summary(membership) -> dict:
    return {
        "hotel_id": membership.hotel_id,
        "hotel_name": membership.hotel.name,
        "hotel_slug": membership.hotel.slug,
        "membership_type": membership.membership_type,
        "is_primary_manager": membership.is_primary_manager,
        "is_active": membership.is_active,
    }


def serialize_hotel_context(hotel, membership, permissions) -> dict:
    return {
        "hotel_id": hotel.id,
        "hotel_name": hotel.name,
        "hotel_slug": hotel.slug,
        "membership_type": membership.membership_type,
        "is_primary_manager": membership.is_primary_manager,
        "permissions": list(permissions),
    }
