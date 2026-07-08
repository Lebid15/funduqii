"""Staff & permissions management services (Phase 11) — the single write path.

This app deliberately owns NO models: it manages the Phase 2 foundation
(``tenancy.HotelMembership`` + ``rbac.HotelPermissionGrant``) through the
existing rbac services. There are no fixed roles anywhere: ``job_title`` is a
descriptive label only, and permission grants are the single source of truth
for access (a manager membership holds every hotel permission by type).

Safety rules enforced here:
- The last ACTIVE manager of a hotel can never be deactivated.
- A non-manager can never grant a permission they do not hold themselves
  (no self- or peer-escalation); removals are always allowed.
- A manager's grants are not editable (they already hold everything by type).
- Platform-owner accounts are never linked or managed as hotel staff.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.common.exceptions import (
    EmailAlreadyRegistered,
    LastManagerProtected,
    ManagerPermissionsNotEditable,
    MembershipAlreadyExists,
    OperationNotEditable,
    PermissionEscalationBlocked,
    PlatformOwnerNotManageable,
    UnknownPermission,
)
from apps.rbac.registry import PERMISSIONS_BY_SECTION, is_valid_permission
from apps.rbac.services import get_active_membership, get_hotel_permissions
from apps.rbac.models import HotelPermissionGrant
from apps.tenancy.models import HotelMembership, MembershipType

User = get_user_model()


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def _validate_password(password: str) -> None:
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": exc.messages})


def _validate_codes(codes) -> list[str]:
    cleaned = sorted({(c or "").strip() for c in codes if (c or "").strip()})
    for code in cleaned:
        if not is_valid_permission(code):
            raise UnknownPermission(f"Unknown permission code: {code}")
    return cleaned


def _guard_escalation(hotel, actor, added_codes) -> None:
    """A non-manager may only grant permissions they hold themselves."""
    if not added_codes:
        return
    membership = get_active_membership(actor, hotel)
    if membership is not None and membership.is_manager:
        return
    held = set(get_hotel_permissions(actor, hotel))
    for code in added_codes:
        if code not in held:
            raise PermissionEscalationBlocked({"code": code})


def active_manager_count(hotel) -> int:
    return HotelMembership.objects.filter(
        hotel=hotel,
        membership_type=MembershipType.MANAGER,
        is_active=True,
        user__is_active=True,
    ).count()


@transaction.atomic
def create_staff_member(
    hotel,
    *,
    actor=None,
    email,
    full_name,
    password,
    phone="",
    job_title="",
    staff_code="",
    notes="",
    permissions=(),
) -> HotelMembership:
    """Create a NEW user account and attach it to the hotel as staff.

    There is no email invitation flow (deliberately deferred): the temporary
    password is handed to the employee outside the system, and it is never
    returned by any API response.
    """
    email = User.objects.normalize_email(email)
    if User.objects.filter(email__iexact=email).exists():
        raise EmailAlreadyRegistered({"email": email})
    _validate_password(password)
    codes = _validate_codes(permissions)
    _guard_escalation(hotel, actor, codes)

    user = User.objects.create_user(
        email=email, password=password, full_name=full_name, phone=phone or ""
    )
    membership = HotelMembership.objects.create(
        user=user,
        hotel=hotel,
        membership_type=MembershipType.STAFF,
        job_title=job_title or "",
        staff_code=staff_code or "",
        notes=notes or "",
        created_by=_actor(actor),
        updated_by=_actor(actor),
    )
    for code in codes:
        HotelPermissionGrant.objects.get_or_create(membership=membership, code=code)
    return membership


@transaction.atomic
def link_existing_user(
    hotel,
    *,
    actor=None,
    user,
    job_title="",
    staff_code="",
    notes="",
    permissions=(),
) -> HotelMembership:
    """Attach an EXISTING user to the hotel as staff.

    Platform-owner accounts are refused outright (documented decision): the
    platform scope and the hotel scope stay strictly separated, so an owner
    can never quietly become hotel staff.
    """
    if user.is_platform_owner:
        raise PlatformOwnerNotManageable()
    if HotelMembership.objects.filter(user=user, hotel=hotel).exists():
        raise MembershipAlreadyExists({"email": user.email})
    codes = _validate_codes(permissions)
    _guard_escalation(hotel, actor, codes)

    membership = HotelMembership.objects.create(
        user=user,
        hotel=hotel,
        membership_type=MembershipType.STAFF,
        job_title=job_title or "",
        staff_code=staff_code or "",
        notes=notes or "",
        created_by=_actor(actor),
        updated_by=_actor(actor),
    )
    for code in codes:
        HotelPermissionGrant.objects.get_or_create(membership=membership, code=code)
    return membership


@transaction.atomic
def update_staff_member(membership: HotelMembership, *, actor=None, **fields) -> HotelMembership:
    """Update DESCRIPTIVE fields only — never membership type, activity or
    permissions (those have their own guarded entry points). Email is the
    login identity and is immutable here."""
    user_dirty = False
    for field in ("full_name", "phone"):
        if field in fields:
            setattr(membership.user, field, fields[field])
            user_dirty = True
    if user_dirty:
        membership.user.save(update_fields=["full_name", "phone"])
    for field in ("job_title", "staff_code", "notes"):
        if field in fields:
            setattr(membership, field, fields[field])
    membership.updated_by = _actor(actor)
    membership.save()
    return membership


@transaction.atomic
def deactivate_staff_member(
    membership: HotelMembership, *, actor=None, reason=""
) -> HotelMembership:
    if not membership.is_active:
        raise OperationNotEditable({"reason": "already_inactive"})
    if membership.is_manager and active_manager_count(membership.hotel) <= 1:
        # Never leave a hotel without an active manager able to run it.
        raise LastManagerProtected()
    membership.is_active = False
    membership.deactivated_at = timezone.now()
    membership.deactivation_reason = (reason or "").strip()
    membership.updated_by = _actor(actor)
    membership.save()
    return membership


@transaction.atomic
def reactivate_staff_member(membership: HotelMembership, *, actor=None) -> HotelMembership:
    if membership.is_active:
        raise OperationNotEditable({"reason": "already_active"})
    membership.is_active = True
    membership.deactivated_at = None
    membership.deactivation_reason = ""
    membership.updated_by = _actor(actor)
    membership.save()
    return membership


@transaction.atomic
def set_staff_permissions(
    membership: HotelMembership, *, actor=None, codes
) -> list[str]:
    """Bulk-replace a staff membership's grants (transaction-safe).

    Managers are refused: they hold every permission by membership type, so
    grants on them would be dead data pretending to matter.
    """
    if membership.is_manager:
        raise ManagerPermissionsNotEditable()
    cleaned = _validate_codes(codes)
    current = set(
        HotelPermissionGrant.objects.filter(membership=membership).values_list(
            "code", flat=True
        )
    )
    added = [c for c in cleaned if c not in current]
    _guard_escalation(membership.hotel, actor, added)

    HotelPermissionGrant.objects.filter(membership=membership).exclude(
        code__in=cleaned
    ).delete()
    for code in added:
        HotelPermissionGrant.objects.get_or_create(membership=membership, code=code)
    membership.updated_by = _actor(actor)
    membership.save(update_fields=["updated_by", "updated_at"])
    return cleaned


@transaction.atomic
def reset_staff_password(membership: HotelMembership, *, actor=None, password) -> None:
    """Local temporary-password reset (no email is ever sent — deferred)."""
    if membership.user.is_platform_owner:
        raise PlatformOwnerNotManageable()
    _validate_password(password)
    membership.user.set_password(password)
    membership.user.save(update_fields=["password"])
    membership.updated_by = _actor(actor)
    membership.save(update_fields=["updated_by", "updated_at"])


def permission_registry_payload() -> list[dict]:
    """The registry grouped by section — the UI builds the matrix from this
    (nothing is hardcoded client-side)."""
    return [
        {
            "section": section,
            "operations": operations,
            "codes": [f"{section}.{op}" for op in operations],
        }
        for section, operations in PERMISSIONS_BY_SECTION.items()
    ]


def staff_overview(hotel) -> dict:
    memberships = HotelMembership.objects.filter(hotel=hotel)
    active = memberships.filter(is_active=True)
    staff_active = active.filter(membership_type=MembershipType.STAFF)
    with_grants = staff_active.filter(permission_grants__isnull=False).distinct()
    return {
        "total_staff": memberships.count(),
        "active_staff": active.count(),
        "inactive_staff": memberships.filter(is_active=False).count(),
        "managers": active.filter(membership_type=MembershipType.MANAGER).count(),
        "staff_with_permissions": with_grants.count(),
        "staff_without_permissions": staff_active.count() - with_grants.count(),
    }
