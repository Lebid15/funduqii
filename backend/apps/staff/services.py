"""Staff & permissions management services (Phase 11 + final closure) — the
single write path.

This app deliberately owns NO models: it manages the Phase 2 foundation
(``tenancy.HotelMembership`` + ``rbac.HotelPermissionGrant``) through the
existing rbac services. There are no fixed roles anywhere: ``job_title`` is a
descriptive label only, and permission grants are the single source of truth
for access (a manager membership holds every hotel permission by type).

Safety rules enforced here (final closure completes the set):
- The last ACTIVE manager of a hotel can never be deactivated, demoted, or
  deleted; the PRIMARY manager is additionally protected on all three.
- A non-manager can never grant a permission they do not hold themselves
  (no escalation); a user can NEVER edit their own membership's grants.
- No self-management of sensitive lifecycle actions (deactivate / promote /
  demote / delete / change-email).
- Manager-only actions (promote/demote) require the ACTOR to be a real
  manager — holding the task permission alone is not enough.
- Deactivation is refused while the employee has an OPEN shift.
- Deletion is a narrow exception: allowed ONLY when the membership (and, for
  a user delete, the whole account) carries zero operational/financial/
  security trace; otherwise deactivation is the only path.
- Platform-owner accounts are never linked or managed as hotel staff.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.common.exceptions import (
    CannotEditOwnPermissions,
    CrossTenantIdentity,
    EmailAlreadyRegistered,
    InvalidMembershipType,
    LastManagerProtected,
    ManagerPermissionsNotEditable,
    MembershipAlreadyExists,
    NotAManager,
    OperationNotEditable,
    PermissionEscalationBlocked,
    PlatformOwnerNotManageable,
    PrimaryManagerProtected,
    SelfActionBlocked,
    StaffHasOpenShift,
    StaffHasTrace,
    UnknownPermission,
)
from apps.rbac.registry import PERMISSIONS_BY_SECTION, is_valid_permission
from apps.rbac.services import get_active_membership, get_hotel_permissions
from apps.rbac.models import HotelPermissionGrant
from apps.tenancy.models import HotelMembership, MembershipType

User = get_user_model()


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def _record(hotel, *, event_type, title, message="", actor=None, target_user=None,
            membership=None, severity="info"):
    """One staff activity event through the Phase 14 system (lazy import)."""
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type=event_type,
        category="staff",
        severity=severity,
        title=title,
        message=message,
        actor=actor,
        target_user=target_user,
        related_object=membership,
        related_url="/hotel/staff",
    )


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


def _guard_not_self(membership, actor) -> None:
    if actor is not None and membership.user_id == getattr(actor, "id", None):
        raise SelfActionBlocked({"membership": membership.id})


def _require_actor_is_manager(hotel, actor) -> None:
    """Manager-only lifecycle actions: holding the task grant is not enough —
    the actor must actually be a manager of this hotel."""
    membership = get_active_membership(actor, hotel)
    if membership is None or not membership.is_manager:
        raise NotAManager()


def active_manager_count(hotel) -> int:
    return HotelMembership.objects.filter(
        hotel=hotel,
        membership_type=MembershipType.MANAGER,
        is_active=True,
        user__is_active=True,
    ).count()


def _assert_manager_removable(membership, *, action: str) -> None:
    """Under the caller's transaction: lock the hotel's active manager rows,
    recount, and refuse if the target is the last active manager or the
    primary manager. ``action`` is only used for clarity in the raised error.
    """
    if not membership.is_manager:
        return
    if membership.is_primary_manager:
        raise PrimaryManagerProtected({"membership": membership.id, "action": action})
    # Lock every active manager membership of this hotel so two concurrent
    # deactivate/demote/delete attempts serialize and cannot both pass.
    manager_ids = list(
        HotelMembership.objects.select_for_update()
        .filter(
            hotel=membership.hotel,
            membership_type=MembershipType.MANAGER,
            is_active=True,
            user__is_active=True,
        )
        .values_list("id", flat=True)
    )
    if membership.id in manager_ids and len(manager_ids) <= 1:
        raise LastManagerProtected({"membership": membership.id, "action": action})


# --- Create / link -----------------------------------------------------------


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
    _record(
        hotel,
        event_type="staff.created",
        title=f"Staff member {full_name} created",
        message=f"{email} · {len(codes)} permission(s)",
        actor=actor,
        target_user=user,
        membership=membership,
        severity="success",
    )
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
    _record(
        hotel,
        event_type="staff.linked_existing_user",
        title=f"Existing user {user.full_name} linked as staff",
        message=f"{user.email} · {len(codes)} permission(s)",
        actor=actor,
        target_user=user,
        membership=membership,
        severity="success",
    )
    return membership


# --- Descriptive update ------------------------------------------------------


@transaction.atomic
def update_staff_member(membership: HotelMembership, *, actor=None, **fields) -> HotelMembership:
    """Update DESCRIPTIVE fields only — never membership type, activity or
    permissions (those have their own guarded entry points). Email is the
    login identity and changes only through ``change_staff_email``.

    Records ``staff.updated`` with the OLD → NEW values of the fields that
    actually changed; nothing is recorded when nothing changes.
    """
    changes = {}
    user_fields = ("full_name", "phone")
    membership_fields = ("job_title", "staff_code", "notes")
    user_dirty = []
    for field in user_fields:
        if field in fields:
            new = fields[field]
            old = getattr(membership.user, field)
            if new != old:
                changes[field] = (old, new)
                setattr(membership.user, field, new)
                user_dirty.append(field)
    for field in membership_fields:
        if field in fields:
            new = fields[field]
            old = getattr(membership, field)
            if new != old:
                changes[field] = (old, new)
                setattr(membership, field, new)
    if not changes:
        return membership
    if user_dirty:
        membership.user.save(update_fields=user_dirty)
    membership.updated_by = _actor(actor)
    membership.save()
    diff = " · ".join(f"{f}: '{o}' → '{n}'" for f, (o, n) in changes.items())
    _record(
        membership.hotel,
        event_type="staff.updated",
        title=f"Staff member {membership.user.full_name} updated",
        message=diff,
        actor=actor,
        target_user=membership.user,
        membership=membership,
    )
    return membership


# --- Deactivate / reactivate -------------------------------------------------


@transaction.atomic
def deactivate_staff_member(
    membership: HotelMembership, *, actor=None, reason=""
) -> HotelMembership:
    membership = HotelMembership.objects.select_for_update().select_related("user").get(
        pk=membership.pk
    )
    _guard_not_self(membership, actor)
    if not membership.is_active:
        raise OperationNotEditable({"reason": "already_inactive"})
    _assert_manager_removable(membership, action="deactivate")
    # Staff closure: never deactivate an employee mid-shift (lazy import).
    from apps.shifts.models import Shift, ShiftStatus

    if Shift.objects.filter(
        hotel=membership.hotel,
        responsible_user=membership.user,
        status=ShiftStatus.OPEN,
    ).exists():
        raise StaffHasOpenShift({"membership": membership.id})
    membership.is_active = False
    membership.deactivated_at = timezone.now()
    membership.deactivation_reason = (reason or "").strip()
    membership.updated_by = _actor(actor)
    membership.save()
    _record(
        membership.hotel,
        event_type="staff.deactivated",
        title=f"Staff member {membership.user.full_name} deactivated",
        message=membership.deactivation_reason,
        actor=actor,
        target_user=membership.user,
        membership=membership,
        severity="warning",
    )
    return membership


@transaction.atomic
def reactivate_staff_member(membership: HotelMembership, *, actor=None) -> HotelMembership:
    membership = HotelMembership.objects.select_for_update().select_related("user").get(
        pk=membership.pk
    )
    if membership.is_active:
        raise OperationNotEditable({"reason": "already_active"})
    membership.is_active = True
    membership.deactivated_at = None
    membership.deactivation_reason = ""
    membership.updated_by = _actor(actor)
    membership.save()
    _record(
        membership.hotel,
        event_type="staff.reactivated",
        title=f"Staff member {membership.user.full_name} reactivated",
        actor=actor,
        target_user=membership.user,
        membership=membership,
        severity="success",
    )
    return membership


# --- Promote / demote --------------------------------------------------------


@transaction.atomic
def promote_to_manager(membership: HotelMembership, *, actor=None) -> HotelMembership:
    """Promote a staff membership to manager. The individual grants are kept
    but become inert while the membership is a manager (a manager holds every
    permission by type); they take effect again on a later demote."""
    _require_actor_is_manager(membership.hotel, actor)
    membership = HotelMembership.objects.select_for_update().select_related("user").get(
        pk=membership.pk
    )
    _guard_not_self(membership, actor)
    if membership.membership_type != MembershipType.STAFF:
        raise InvalidMembershipType({"expected": "staff", "actual": membership.membership_type})
    membership.membership_type = MembershipType.MANAGER
    membership.updated_by = _actor(actor)
    membership.save(update_fields=["membership_type", "updated_by", "updated_at"])
    _record(
        membership.hotel,
        event_type="staff.promoted_to_manager",
        title=f"{membership.user.full_name} promoted to manager",
        message="staff → manager",
        actor=actor,
        target_user=membership.user,
        membership=membership,
        severity="success",
    )
    return membership


@transaction.atomic
def demote_to_staff(membership: HotelMembership, *, actor=None) -> HotelMembership:
    """Demote a manager membership to staff. Refused for the last active
    manager and for the primary manager. The preserved individual grants
    become the source of access again."""
    _require_actor_is_manager(membership.hotel, actor)
    membership = HotelMembership.objects.select_for_update().select_related("user").get(
        pk=membership.pk
    )
    _guard_not_self(membership, actor)
    if membership.membership_type != MembershipType.MANAGER:
        raise InvalidMembershipType({"expected": "manager", "actual": membership.membership_type})
    _assert_manager_removable(membership, action="demote")
    membership.membership_type = MembershipType.STAFF
    membership.updated_by = _actor(actor)
    membership.save(update_fields=["membership_type", "updated_by", "updated_at"])
    _record(
        membership.hotel,
        event_type="staff.demoted_to_staff",
        title=f"{membership.user.full_name} demoted to staff",
        message="manager → staff",
        actor=actor,
        target_user=membership.user,
        membership=membership,
        severity="warning",
    )
    return membership


# --- Permissions -------------------------------------------------------------


@transaction.atomic
def set_staff_permissions(
    membership: HotelMembership, *, actor=None, codes
) -> list[str]:
    """Bulk-replace a staff membership's grants (transaction-safe).

    A user can NEVER edit their own membership's grants (self-service access is
    forbidden regardless of what changes). Managers are refused: they hold
    every permission by membership type, so grants on them would be dead data.
    """
    # Self-edit is refused BEFORE anything else — covers add/remove/replace and
    # even re-sending the identical set.
    if actor is not None and membership.user_id == getattr(actor, "id", None):
        raise CannotEditOwnPermissions({"membership": membership.id})
    if membership.is_manager:
        raise ManagerPermissionsNotEditable()
    cleaned = _validate_codes(codes)
    current = set(
        HotelPermissionGrant.objects.filter(membership=membership).values_list(
            "code", flat=True
        )
    )
    added = [c for c in cleaned if c not in current]
    removed = sorted(current - set(cleaned))
    _guard_escalation(membership.hotel, actor, added)

    HotelPermissionGrant.objects.filter(membership=membership).exclude(
        code__in=cleaned
    ).delete()
    for code in added:
        HotelPermissionGrant.objects.get_or_create(membership=membership, code=code)
    membership.updated_by = _actor(actor)
    membership.save(update_fields=["updated_by", "updated_at"])
    if added or removed:
        _record(
            membership.hotel,
            event_type="staff.permissions_updated",
            title=f"Permissions updated for {membership.user.full_name}",
            message=(
                f"+{len(added)} added ({', '.join(added) or '—'}) · "
                f"-{len(removed)} removed ({', '.join(removed) or '—'})"
            ),
            actor=actor,
            target_user=membership.user,
            membership=membership,
        )
    return cleaned


@transaction.atomic
def reset_staff_password(membership: HotelMembership, *, actor=None, password) -> None:
    """Local temporary-password reset (no email is ever sent — deferred). The
    password is never echoed nor recorded in any activity event."""
    if membership.user.is_platform_owner:
        raise PlatformOwnerNotManageable()
    _validate_password(password)
    membership.user.set_password(password)
    membership.user.save(update_fields=["password"])
    membership.updated_by = _actor(actor)
    membership.save(update_fields=["updated_by", "updated_at"])


# --- Email change ------------------------------------------------------------


def _other_membership_count(user, *, exclude_hotel) -> int:
    """Memberships of ``user`` in OTHER hotels — active OR historical. Email is
    a global login identity, so any other tenancy makes it cross-tenant."""
    return HotelMembership.objects.filter(user=user).exclude(hotel=exclude_hotel).count()


@transaction.atomic
def change_staff_email(membership: HotelMembership, *, actor=None, new_email) -> HotelMembership:
    """Change the login email of a single-hotel user, under its own permission.

    Refused when the user's identity spans more than one tenant (any other
    membership — active or historical — or a platform role): that global
    identity is not a single hotel's to change.
    """
    membership = HotelMembership.objects.select_for_update().select_related("user").get(
        pk=membership.pk
    )
    _guard_not_self(membership, actor)
    user = membership.user
    if user.is_platform_owner:
        raise PlatformOwnerNotManageable()
    if _other_membership_count(user, exclude_hotel=membership.hotel) > 0:
        raise CrossTenantIdentity({"user": user.id})
    normalized = User.objects.normalize_email(new_email)
    if User.objects.filter(email__iexact=normalized).exclude(pk=user.pk).exists():
        raise EmailAlreadyRegistered({"email": normalized})
    old_email = user.email
    if normalized == old_email:
        return membership
    user.email = normalized
    user.save(update_fields=["email"])
    membership.updated_by = _actor(actor)
    membership.save(update_fields=["updated_by", "updated_at"])
    _record(
        membership.hotel,
        event_type="staff.email_changed",
        title=f"Email changed for {user.full_name}",
        message=f"'{old_email}' → '{normalized}'",
        actor=actor,
        target_user=user,
        membership=membership,
        severity="warning",
    )
    return membership


# --- Guarded deletion --------------------------------------------------------
#
# Every model below carries a ``hotel`` FK plus one or more actor FKs. The
# maps drive an exists()-loop: the FIRST hit proves a trace and stops the scan.
# Missing an entry would risk deleting an account that still has history, so
# this list mirrors every audit/actor field in the codebase.

#: (app_label, model_name, [actor field names]) — hotel-scoped trace.
_TRACE_MAP = [
    ("shifts", "Shift", ["responsible_user", "opened_by", "created_by", "updated_by"]),
    ("shifts", "ShiftStatusLog", ["changed_by"]),
    ("shifts", "ShiftHandover", ["to_user", "created_by", "updated_by"]),
    ("shifts", "ShiftHandoverStatusLog", ["changed_by"]),
    ("shifts", "DailyClose", ["closed_by", "reopened_by"]),
    ("shifts", "DailyCloseStatusLog", ["changed_by"]),
    ("reservations", "Reservation", ["cancelled_by", "created_by", "updated_by"]),
    ("reservations", "ReservationStatusLog", ["changed_by"]),
    ("stays", "Stay", ["checked_in_by", "checked_out_by"]),
    ("stays", "StayStatusLog", ["changed_by"]),
    ("finance", "Folio", ["closed_by", "voided_by", "created_by", "updated_by"]),
    ("finance", "FolioCharge", ["voided_by", "created_by"]),
    ("finance", "Payment", ["voided_by", "created_by"]),
    ("finance", "Invoice", ["voided_by", "created_by"]),
    ("finance", "Expense", ["voided_by", "created_by", "updated_by"]),
    ("services", "ServiceOrder", ["cancelled_by", "posted_by", "settled_by", "created_by", "updated_by"]),
    ("services", "ServiceOrderItem", ["cancelled_by"]),
    ("services", "ServiceOrderStatusLog", ["changed_by"]),
    ("services", "RestaurantTable", ["created_by", "updated_by"]),
    ("operations", "HousekeepingTask", ["assigned_to", "created_by", "updated_by"]),
    ("operations", "HousekeepingTaskStatusLog", ["changed_by"]),
    ("operations", "MaintenanceRequest", ["assigned_to", "created_by", "updated_by"]),
    ("operations", "MaintenanceRequestStatusLog", ["changed_by"]),
    ("operations", "LostFoundItem", ["created_by", "updated_by"]),
    ("operations", "LostFoundItemStatusLog", ["changed_by"]),
    ("rooms", "Room", ["status_changed_by"]),
    ("rooms", "RoomStatusLog", ["changed_by"]),
    ("guests", "Guest", ["created_by", "updated_by"]),
    ("guests", "GuestBlockLog", ["created_by"]),
    ("notifications", "ActivityEvent", ["actor", "target_user"]),
]


def _has_trace(user, *, hotel=None) -> bool:
    """Any actor/audit reference to ``user`` — scoped to ``hotel`` when given,
    otherwise global. Also counts memberships-created-by and status changes.
    """
    from django.apps import apps as django_apps

    for app_label, model_name, fields in _TRACE_MAP:
        model = django_apps.get_model(app_label, model_name)
        q = Q()
        for field in fields:
            q |= Q(**{field: user})
        qs = model.objects.filter(q)
        if hotel is not None:
            qs = qs.filter(hotel=hotel)
        if qs.exists():
            return True
    # Memberships/hotels this user created or last changed (tenancy layer).
    membership_qs = HotelMembership.objects.filter(
        Q(created_by=user) | Q(updated_by=user)
    ).exclude(user=user)
    if hotel is not None:
        membership_qs = membership_qs.filter(hotel=hotel)
    if membership_qs.exists():
        return True
    return False


@transaction.atomic
def delete_staff_membership(membership: HotelMembership, *, actor=None, delete_user=False) -> dict:
    """Delete a CLEAN membership (and optionally its now-orphan user). Refused
    outright when any operational/financial/security trace exists — then
    deactivation is the only path. Never a blind cascade.
    """
    membership = HotelMembership.objects.select_for_update().select_related("user").get(
        pk=membership.pk
    )
    _guard_not_self(membership, actor)
    user = membership.user
    if user.is_platform_owner:
        raise PlatformOwnerNotManageable()
    # Manager protections apply to deletion too.
    _assert_manager_removable(membership, action="delete")
    # A membership with any trace inside its hotel can never be deleted.
    if _has_trace(user, hotel=membership.hotel):
        raise StaffHasTrace({"membership": membership.id, "scope": "hotel"})

    hotel = membership.hotel
    full_name = user.full_name
    email = user.email
    membership_id = membership.id
    HotelPermissionGrant.objects.filter(membership=membership).delete()
    membership.delete()
    # target_user is intentionally NOT set on delete events: the account may be
    # removed next, and an audit record must never create a self-referential
    # trace that blocks its own user deletion. The name is kept in the message.
    _record(
        hotel,
        event_type="staff.membership_deleted",
        title=f"Staff membership of {full_name} deleted",
        message=f"{email} (no operational history)",
        actor=actor,
        target_user=None,
        membership=None,
        severity="danger",
    )
    result = {"membership_deleted": membership_id, "user_deleted": None}

    if delete_user:
        # A user is deletable ONLY when it is fully clean and orphan.
        other = HotelMembership.objects.filter(user=user).exists()
        clean = (
            not other
            and not user.is_platform_owner
            and not user.is_staff
            and not user.is_superuser
            and not _has_trace(user, hotel=None)
            and not HotelMembership.objects.filter(
                Q(created_by=user) | Q(updated_by=user)
            ).exists()
        )
        if clean:
            user_id = user.id
            user.delete()
            _record(
                hotel,
                event_type="staff.user_deleted",
                title=f"User account {full_name} deleted",
                message=f"{email} (fully clean, no global history)",
                actor=actor,
                target_user=None,
                membership=None,
                severity="danger",
            )
            result["user_deleted"] = user_id
        # If not clean: the membership is already gone; the user is kept.
    return result


# --- Registry / overview -----------------------------------------------------


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
