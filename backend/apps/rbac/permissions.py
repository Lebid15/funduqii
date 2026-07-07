"""Reusable DRF permission classes.

These are the enforcement points every sensitive endpoint will use in later
phases. Hiding a button is not protection: authorization is decided here, on
the backend, and rejected requests raise typed, translatable errors.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.accounts.models import AccountType
from apps.common.exceptions import PermissionDenied, UserInactive
from apps.tenancy.context import resolve_hotel_context

from .services import has_hotel_permission


class IsAuthenticatedAndActive(BasePermission):
    """Require an authenticated, active user."""

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False  # -> 401 not_authenticated
        if not user.is_active:
            raise UserInactive()
        return True


class IsPlatformOwner(IsAuthenticatedAndActive):
    """Require the platform owner account type (platform scope)."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.user.account_type == AccountType.PLATFORM_OWNER


class HasHotelMembership(IsAuthenticatedAndActive):
    """Require an active membership in the hotel named by X-Hotel-ID.

    On success, attaches ``request.hotel``, ``request.hotel_membership`` and
    ``request.hotel_context`` for downstream use.
    """

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        context = resolve_hotel_context(request, required=True)
        request.hotel_context = context
        request.hotel = context.hotel
        request.hotel_membership = context.membership
        return True


class BaseHotelPermission(HasHotelMembership):
    """Require a specific ``section.operation`` permission in the current hotel.

    Set ``required_permission`` on a subclass (see :func:`HasHotelPermission`)
    or on the view.
    """

    required_permission: str | None = None

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        code = self.required_permission or getattr(view, "required_permission", None)
        if not code:
            raise ValueError(
                "BaseHotelPermission requires 'required_permission' on the "
                "permission class or the view."
            )
        if not has_hotel_permission(request.user, request.hotel, code):
            raise PermissionDenied()
        return True


def HasHotelPermission(code: str):
    """Factory returning a permission class bound to ``code``.

    Usage: ``permission_classes = [HasHotelPermission("reservations.view")]``.
    """
    return type(
        f"HasHotelPermission_{code.replace('.', '_')}",
        (BaseHotelPermission,),
        {"required_permission": code},
    )
