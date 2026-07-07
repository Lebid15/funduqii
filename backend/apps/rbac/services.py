"""Permission services — the backend source of truth for authorization.

Rules enforced here:
- A permission code must exist in the registry (unknown codes are rejected).
- Only an *active* user with an *active* membership in the given hotel is
  considered; otherwise no permission is held.
- A hotel manager holds every permission of their hotel by default.
- Staff hold only explicitly granted permissions.
- A grant is valid only inside the hotel it belongs to.
"""
from __future__ import annotations

from apps.common.exceptions import UnknownPermission
from apps.tenancy.models import HotelMembership, MembershipType

from .models import HotelPermissionGrant
from .registry import ALL_PERMISSIONS, is_valid_permission


def _require_known(code: str) -> None:
    if not is_valid_permission(code):
        raise UnknownPermission(f"Unknown permission code: {code}")


def get_active_membership(user, hotel) -> HotelMembership | None:
    if user is None or not user.is_authenticated or not user.is_active:
        return None
    membership = HotelMembership.objects.filter(user=user, hotel=hotel).first()
    if membership is None or not membership.is_active:
        return None
    return membership


def has_hotel_permission(user, hotel, code: str) -> bool:
    _require_known(code)
    membership = get_active_membership(user, hotel)
    if membership is None:
        return False
    if membership.membership_type == MembershipType.MANAGER:
        return True
    return HotelPermissionGrant.objects.filter(
        membership=membership, code=code
    ).exists()


def get_hotel_permissions(user, hotel) -> list[str]:
    membership = get_active_membership(user, hotel)
    if membership is None:
        return []
    if membership.membership_type == MembershipType.MANAGER:
        return sorted(ALL_PERMISSIONS)
    return sorted(
        HotelPermissionGrant.objects.filter(membership=membership).values_list(
            "code", flat=True
        )
    )


def grant_permission(membership: HotelMembership, code: str) -> HotelPermissionGrant:
    """Assign a permission to a staff membership (idempotent)."""
    _require_known(code)
    grant, _ = HotelPermissionGrant.objects.get_or_create(
        membership=membership, code=code
    )
    return grant


def revoke_permission(membership: HotelMembership, code: str) -> None:
    HotelPermissionGrant.objects.filter(membership=membership, code=code).delete()
