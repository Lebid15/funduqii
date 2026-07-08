"""Notification/activity domain services (Phase 14) — the ONE creation path.

Domain services (reservations, stays, finance, services, operations, shifts,
staff) call :func:`record_activity` after their own successful write. This
module then:

1. stores an :class:`ActivityEvent` (scrubbed metadata, internal-only URL),
2. fans out :class:`Notification` rows to the RIGHT recipients — active
   members of the same hotel who are managers or hold a view permission for
   the event's category. The actor never notifies themselves; a deactivated
   member never receives anything; nothing crosses hotels.

Nothing here mutates operational data, and there are NO external channels
(no WhatsApp/email/SMS/push) — deliberately.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.tenancy.models import HotelMembership, MembershipType

from .models import (
    ActivityCategory,
    ActivityEvent,
    ActivitySeverity,
    Notification,
    NotificationsNumberSequence,
)

NUMBER_PREFIXES = {"activity": "ACT", "notification": "NTF"}

#: Metadata keys that must never be stored (case-insensitive substring match).
SENSITIVE_KEY_PARTS = ("password", "token", "secret", "authorization", "api_key", "apikey")

#: Which view permission codes make a member a recipient for a category.
#: A manager always qualifies. `system`/`report` events go to managers only.
CATEGORY_VIEW_CODES: dict[str, tuple[str, ...]] = {
    ActivityCategory.RESERVATION: ("reservations.view", "stays.view"),
    ActivityCategory.STAY: ("stays.view", "reservations.view"),
    ActivityCategory.GUEST: ("guests.view",),
    ActivityCategory.ROOM: ("rooms.view",),
    ActivityCategory.FINANCE: ("finance.view", "expenses.view"),
    ActivityCategory.SERVICE: ("services.view", "service_orders.view"),
    ActivityCategory.OPERATION: (
        "housekeeping.view",
        "maintenance.view",
        "lost_found.view",
    ),
    ActivityCategory.SHIFT: ("shifts.view", "daily_close.view"),
    ActivityCategory.STAFF: ("staff.view",),
    ActivityCategory.REPORT: (),
    ActivityCategory.SYSTEM: (),
}


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def next_number(hotel, kind: str) -> str:
    """Allocate the next per-hotel ACT/NTF number (row-locked; needs a txn)."""
    prefix = NUMBER_PREFIXES[kind]
    seq, _ = NotificationsNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel, kind=kind
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"{prefix}{seq.last_number:05d}"


def safe_metadata(metadata) -> dict:
    """Keep only primitive values and drop secret-looking keys."""
    if not isinstance(metadata, dict):
        return {}
    out = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if any(part in lowered for part in SENSITIVE_KEY_PARTS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)[:64]] = value if not isinstance(value, str) else value[:255]
    return out


def safe_related_url(url) -> str:
    """Internal application paths only — never an arbitrary external link."""
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("/") or url.startswith("//") or ":" in url.split("?")[0]:
        return ""
    return url[:255]


def eligible_recipients(hotel, category, *, exclude_user=None):
    """Active members of THIS hotel who should see events of `category`:
    managers always; staff only with a matching view permission grant."""
    codes = CATEGORY_VIEW_CODES.get(category, ())
    qs = HotelMembership.objects.filter(
        hotel=hotel, is_active=True, user__is_active=True
    )
    condition = Q(membership_type=MembershipType.MANAGER)
    if codes:
        condition |= Q(permission_grants__code__in=codes)
    qs = qs.filter(condition)
    if exclude_user is not None and getattr(exclude_user, "id", None):
        qs = qs.exclude(user_id=exclude_user.id)
    seen: set[int] = set()
    users = []
    for membership in qs.select_related("user"):
        if membership.user_id in seen:
            continue
        seen.add(membership.user_id)
        users.append(membership.user)
    return users


@transaction.atomic
def create_notification(
    hotel,
    *,
    recipient,
    category=ActivityCategory.SYSTEM,
    severity=ActivitySeverity.INFO,
    title,
    message="",
    related_url="",
    activity=None,
) -> Notification | None:
    """Create ONE in-app notification. The recipient must be an ACTIVE member
    of the hotel — anything else is silently skipped (never an error path
    that could break the domain operation that triggered it)."""
    is_member = HotelMembership.objects.filter(
        hotel=hotel, user=recipient, is_active=True, user__is_active=True
    ).exists()
    if not is_member:
        return None
    return Notification.objects.create(
        hotel=hotel,
        notification_number=next_number(hotel, "notification"),
        recipient=recipient,
        activity=activity,
        category=category,
        severity=severity,
        title=title[:200],
        message=(message or "")[:255],
        related_url=safe_related_url(related_url),
    )


@transaction.atomic
def record_activity(
    hotel,
    *,
    event_type,
    category=ActivityCategory.SYSTEM,
    severity=ActivitySeverity.INFO,
    title,
    message="",
    actor=None,
    target_user=None,
    related_object=None,
    related_url="",
    metadata=None,
    notify=True,
) -> ActivityEvent:
    """Record one operational event and (optionally) fan out notifications to
    the permission-matched recipients. This is the ONLY creation path."""
    event = ActivityEvent.objects.create(
        hotel=hotel,
        event_number=next_number(hotel, "activity"),
        event_type=event_type[:64],
        category=category,
        severity=severity,
        title=title[:200],
        message=(message or "")[:255],
        actor=_actor(actor),
        target_user=target_user,
        related_object_type=(
            related_object.__class__.__name__ if related_object is not None else ""
        ),
        related_object_id=(
            getattr(related_object, "pk", None) if related_object is not None else None
        ),
        related_url=safe_related_url(related_url),
        metadata_json=safe_metadata(metadata),
    )
    if notify:
        for user in eligible_recipients(hotel, category, exclude_user=actor):
            create_notification(
                hotel,
                recipient=user,
                category=category,
                severity=severity,
                title=event.title,
                message=event.message,
                related_url=event.related_url,
                activity=event,
            )
    return event


# --- Recipient-side operations (user-state only) ------------------------------------


@transaction.atomic
def mark_read(notification: Notification) -> Notification:
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at"])
    return notification


@transaction.atomic
def mark_all_read(hotel, user) -> int:
    now = timezone.now()
    return Notification.objects.filter(
        hotel=hotel, recipient=user, is_read=False
    ).update(is_read=True, read_at=now)


@transaction.atomic
def archive(notification: Notification) -> Notification:
    if not notification.is_archived:
        notification.is_archived = True
        notification.archived_at = timezone.now()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
        notification.save(
            update_fields=["is_archived", "archived_at", "is_read", "read_at"]
        )
    return notification
