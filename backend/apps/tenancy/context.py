"""Tenant context resolution.

The current hotel is selected per-request via the ``X-Hotel-ID`` header. A user
may only operate inside a hotel where they hold an *active* membership; a
platform owner is NOT treated as hotel staff unless they have an explicit
membership. Sending an ID for a hotel the user does not belong to is rejected.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.common.exceptions import (
    HotelContextRequired,
    HotelNotFound,
    MembershipInactive,
    NoHotelMembership,
    UserInactive,
)

from .models import Hotel, HotelMembership

HOTEL_ID_HEADER = "X-Hotel-ID"
_HOTEL_ID_META_KEY = "HTTP_X_HOTEL_ID"
_CACHE_ATTR = "_funduqii_hotel_context"


@dataclass(frozen=True)
class HotelContext:
    hotel: Hotel
    membership: HotelMembership


def get_hotel_id_from_request(request) -> str | None:
    raw = request.META.get(_HOTEL_ID_META_KEY)
    return raw or None


def resolve_hotel_context(request, *, required: bool = True) -> HotelContext | None:
    """Resolve and validate the current hotel context for ``request``.

    Raises a typed, translatable error when the context is required but missing
    or invalid. Returns ``None`` only when ``required=False`` and no header is
    present. The result is cached on the request.
    """
    cached = getattr(request, _CACHE_ATTR, None)
    if cached is not None:
        return cached

    raw = get_hotel_id_from_request(request)
    if not raw:
        if required:
            raise HotelContextRequired()
        return None

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        # Authentication is enforced by permission classes; be defensive here.
        raise NoHotelMembership()
    if not user.is_active:
        raise UserInactive()

    if not str(raw).isdigit():
        raise HotelNotFound()
    hotel = Hotel.objects.filter(pk=int(raw)).first()
    if hotel is None:
        raise HotelNotFound()

    membership = HotelMembership.objects.filter(user=user, hotel=hotel).first()
    if membership is None:
        raise NoHotelMembership()
    if not membership.is_active:
        raise MembershipInactive()

    context = HotelContext(hotel=hotel, membership=membership)
    setattr(request, _CACHE_ATTR, context)
    return context
