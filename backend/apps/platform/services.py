"""Platform-owner services for tenant (hotel) management.

Creating a hotel and (optionally) its primary manager touches three apps
(accounts, tenancy, rbac), so the composition lives here behind a transaction
rather than in a serializer. Kept minimal for Phase 3: a hotel is a bare tenant
(name/slug/status) and a manager is a hotel user with a primary manager
membership. No hotel settings, images, rooms, etc.
"""
from __future__ import annotations

from django.db import transaction

from apps.accounts.models import AccountType, User
from apps.tenancy.models import Hotel, HotelMembership, MembershipType


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
    return Hotel.objects.create(**fields)


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
