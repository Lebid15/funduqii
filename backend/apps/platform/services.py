"""Platform-owner services for tenant (hotel) management.

Creating a hotel and (optionally) its primary manager touches three apps
(accounts, tenancy, rbac), so the composition lives here behind a transaction
rather than in a serializer. Kept minimal for Phase 3: a hotel is a bare tenant
(name/slug/status) and a manager is a hotel user with a primary manager
membership. No hotel settings, images, rooms, etc.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccountType, User
from apps.common.exceptions import (
    InvalidHotelStatusTransition,
    SuspensionReasonRequired,
)
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType


def get_primary_manager(hotel: Hotel) -> User | None:
    membership = (
        HotelMembership.objects.filter(hotel=hotel, is_primary_manager=True)
        .select_related("user")
        .first()
    )
    return membership.user if membership else None


@transaction.atomic
def create_hotel(*, name: str, slug: str, status: str | None = None) -> Hotel:
    fields = {"name": name, "slug": slug}
    if status:
        fields["status"] = status
    hotel = Hotel.objects.create(**fields)
    # Notifications closure: the platform owner is notified of a new hotel. Kept
    # to the platform scope only (hotel staff — who may not exist yet — are not
    # notified); dedup_key prevents a duplicate registration notification.
    from apps.notifications.services import notify_platform_owners

    notify_platform_owners(
        event_type="platform.hotel_registered",
        title=f"New hotel registered: {hotel.name}",
        message=f"Hotel '{hotel.name}' was created.",
        hotel=hotel,
        related_url=f"/platform/hotels/{hotel.id}",
        dedup_key=f"platform.hotel_registered:platform:{hotel.id}",
    )
    return hotel


# --- Hotel status lifecycle (Phase 16) ---------------------------------------


def _record_hotel_event(hotel, *, event_type, title, message="", actor=None):
    """Surface a platform status action in the hotel's activity feed
    (category `system` → the hotel's managers only; Phase 14 pattern)."""
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type=event_type,
        title=title,
        message=message,
        actor=actor,
        related_object=hotel,
    )


def _set_hotel_status(hotel, status, *, reason="", actor=None) -> Hotel:
    hotel.status = status
    hotel.suspension_reason = reason
    hotel.status_changed_at = timezone.now()
    hotel.status_changed_by = actor if getattr(actor, "is_authenticated", False) else None
    hotel.save(
        update_fields=[
            "status",
            "suspension_reason",
            "status_changed_at",
            "status_changed_by",
            "updated_at",
        ]
    )
    return hotel


@transaction.atomic
def activate_hotel(hotel: Hotel, *, actor=None) -> Hotel:
    """Move a hotel from setup to active. Suspended hotels use unsuspend."""
    if hotel.status != HotelStatus.SETUP:
        raise InvalidHotelStatusTransition()
    return _set_hotel_status(hotel, HotelStatus.ACTIVE, actor=actor)


@transaction.atomic
def suspend_hotel(hotel: Hotel, *, reason: str, actor=None) -> Hotel:
    """Suspend a hotel — a REASON and the acting user are recorded.

    Suspension deletes nothing: reads stay available, important writes are
    refused (`hotel_suspended`), and the hotel disappears from the public
    site (Phase 15 filters on ACTIVE).
    """
    if not (reason or "").strip():
        raise SuspensionReasonRequired()
    if hotel.status == HotelStatus.SUSPENDED:
        raise InvalidHotelStatusTransition()
    hotel = _set_hotel_status(
        hotel, HotelStatus.SUSPENDED, reason=reason.strip()[:255], actor=actor
    )
    _record_hotel_event(
        hotel,
        event_type="hotel.suspended",
        title="The hotel was suspended by the platform",
        message=reason.strip()[:255],
        actor=actor,
    )
    return hotel


@transaction.atomic
def unsuspend_hotel(hotel: Hotel, *, actor=None) -> Hotel:
    """Lift a suspension: back to active. Operations resume according to the
    hotel's subscription state (enforcement stays in charge)."""
    if hotel.status != HotelStatus.SUSPENDED:
        raise InvalidHotelStatusTransition()
    hotel = _set_hotel_status(hotel, HotelStatus.ACTIVE, actor=actor)
    _record_hotel_event(
        hotel,
        event_type="hotel.unsuspended",
        title="The hotel suspension was lifted",
        actor=actor,
    )
    return hotel


@transaction.atomic
def set_primary_manager(
    hotel: Hotel,
    *,
    email: str,
    full_name: str,
    password: str,
) -> User:
    """Create (or reuse) a hotel user and make them the hotel's primary manager.

    Any existing primary manager for the hotel is demoted to a normal manager so
    the single-primary-manager invariant holds. If a user with ``email`` already
    exists they are reused (must be a hotel user); otherwise a new hotel user is
    created.
    """
    email = email.strip().lower()
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            account_type=AccountType.HOTEL_USER,
        )

    # Demote any current primary manager to keep the unique-primary invariant.
    HotelMembership.objects.filter(hotel=hotel, is_primary_manager=True).exclude(
        user=user
    ).update(is_primary_manager=False)

    membership, _ = HotelMembership.objects.get_or_create(
        hotel=hotel,
        user=user,
        defaults={
            "membership_type": MembershipType.MANAGER,
            "is_primary_manager": True,
            "is_active": True,
        },
    )
    # Ensure an existing membership is promoted to primary manager.
    updates = {}
    if membership.membership_type != MembershipType.MANAGER:
        membership.membership_type = MembershipType.MANAGER
        updates["membership_type"] = MembershipType.MANAGER
    if not membership.is_primary_manager:
        membership.is_primary_manager = True
        updates["is_primary_manager"] = True
    if not membership.is_active:
        membership.is_active = True
        updates["is_active"] = True
    if updates:
        membership.save(update_fields=[*updates.keys(), "updated_at"])

    return user
