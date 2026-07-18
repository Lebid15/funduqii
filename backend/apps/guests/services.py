"""Guest-profile services (final closure round): VIP, hotel-scoped block,
delete hardening, document masking and activity logging — the ONE controlled
path for every guest state change. Views never mutate these flags directly.

Nothing here touches reservations, stays or folios: the guests section reads
operational history, it never rewrites it.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import BlockReasonRequired, GuestBlocked

from .models import Guest, GuestBlockAction, GuestBlockLog

# Stay statuses that count as a REAL stay for directory visibility and stats
# (cancelled stays never count; reservations without a stay never count).
REAL_STAY_STATUSES = ("in_house", "checked_out")


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def _record(guest, *, event_type, severity, title, message, user=None):
    # Phase 14 activity system (lazy import keeps app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        guest.hotel,
        event_type=event_type,
        category="guest",
        severity=severity,
        title=title,
        message=message,
        actor=user,
        related_object=guest,
        related_url="/hotel/guests",
    )


def mask_document(number: str) -> str:
    """Central masking rule: only the last four characters stay visible.

    Applied at the API layer (serializers/profile) for callers without
    ``guests.view_sensitive_data`` — the frontend never decides this.
    """
    if not number:
        return ""
    if len(number) <= 4:
        return "••••"
    return f"••••{number[-4:]}"


def record_guest_created(guest, *, user=None):
    _record(
        guest,
        event_type="guest.created",
        severity="info",
        title=f"Guest profile created: {guest.full_name}",
        message=guest.phone or "—",
        user=user,
    )


def record_guest_reactivated(guest, *, user=None):
    """Log that a previously-deactivated profile was reused and reactivated by
    the central identity resolution service (GUESTS central identity). The
    reactivation itself is written by that service; this only records the audit
    event so the history shows WHY the profile came back to life."""
    _record(
        guest,
        event_type="guest.reactivated",
        severity="info",
        title=f"Guest profile reactivated: {guest.full_name}",
        message="reused by central identity resolution",
        user=user,
    )


def record_guest_updated(guest, *, old_values, user=None):
    """Log a profile edit. Old/new values are included for the sensitive
    identity fields — except document numbers, which are logged MASKED."""
    changes = []
    if old_values.get("full_name") != guest.full_name:
        changes.append(f"name: {old_values['full_name']} → {guest.full_name}")
    if old_values.get("phone") != guest.phone:
        changes.append(f"phone: {old_values['phone'] or '—'} → {guest.phone or '—'}")
    if old_values.get("document_type") != guest.document_type or old_values.get(
        "document_number"
    ) != guest.document_number:
        changes.append(
            "document: "
            f"{old_values.get('document_type') or '—'} "
            f"{mask_document(old_values.get('document_number', ''))or '—'} → "
            f"{guest.document_type or '—'} {mask_document(guest.document_number) or '—'}"
        )
    _record(
        guest,
        event_type="guest.updated",
        severity="info",
        title=f"Guest profile updated: {guest.full_name}",
        message="; ".join(changes) if changes else "profile fields updated",
        user=user,
    )


@transaction.atomic
def set_vip(guest, *, vip: bool, user=None) -> Guest:
    """Mark / unmark a guest as VIP — a plain flag, no tiers and no money."""
    guest = Guest.objects.select_for_update().get(pk=guest.pk)
    if guest.is_vip == vip:
        return guest
    guest.is_vip = vip
    guest.vip_marked_at = timezone.now() if vip else None
    guest.vip_marked_by = _actor(user) if vip else None
    guest.updated_by = _actor(user)
    guest.save(
        update_fields=[
            "is_vip", "vip_marked_at", "vip_marked_by", "updated_by", "updated_at",
        ]
    )
    _record(
        guest,
        event_type="guest.vip_marked" if vip else "guest.vip_unmarked",
        severity="info",
        title=(
            f"Guest marked VIP: {guest.full_name}"
            if vip
            else f"Guest VIP removed: {guest.full_name}"
        ),
        message="",
        user=user,
    )
    return guest


@transaction.atomic
def block_guest(guest, *, reason: str, user=None) -> Guest:
    """Block a guest INSIDE this hotel only (Guest rows are hotel-scoped, so
    a block can never reach another hotel). The reason is mandatory and the
    action is appended to the immutable block history."""
    if not (reason or "").strip():
        raise BlockReasonRequired()
    guest = Guest.objects.select_for_update().get(pk=guest.pk)
    guest.is_blocked = True
    guest.block_reason = reason.strip()
    guest.blocked_at = timezone.now()
    guest.blocked_by = _actor(user)
    guest.updated_by = _actor(user)
    guest.save(
        update_fields=[
            "is_blocked", "block_reason", "blocked_at", "blocked_by",
            "updated_by", "updated_at",
        ]
    )
    GuestBlockLog.objects.create(
        hotel=guest.hotel,
        guest=guest,
        action=GuestBlockAction.BLOCKED,
        reason=reason.strip(),
        created_by=_actor(user),
    )
    _record(
        guest,
        event_type="guest.blocked",
        severity="warning",
        title=f"Guest blocked: {guest.full_name}",
        message=reason.strip(),
        user=user,
    )
    return guest


@transaction.atomic
def unblock_guest(guest, *, note: str = "", user=None) -> Guest:
    """Lift the current block. The old reason survives in GuestBlockLog."""
    guest = Guest.objects.select_for_update().get(pk=guest.pk)
    if not guest.is_blocked:
        return guest
    guest.is_blocked = False
    guest.block_reason = ""
    guest.blocked_at = None
    guest.blocked_by = None
    guest.updated_by = _actor(user)
    guest.save(
        update_fields=[
            "is_blocked", "block_reason", "blocked_at", "blocked_by",
            "updated_by", "updated_at",
        ]
    )
    GuestBlockLog.objects.create(
        hotel=guest.hotel,
        guest=guest,
        action=GuestBlockAction.UNBLOCKED,
        reason=(note or "").strip(),
        created_by=_actor(user),
    )
    _record(
        guest,
        event_type="guest.unblocked",
        severity="info",
        title=f"Guest unblocked: {guest.full_name}",
        message=(note or "").strip(),
        user=user,
    )
    return guest


def guest_has_operational_traces(guest) -> bool:
    """True when ANY operational history references the guest — stays (any
    role), folios, lost & found, reservations (upcoming or historical), a
    reservation-occupant link, or a block-log entry. Such a profile is never
    hard-deleted; it is deactivated so its history (and its identity, for the
    block guard) is preserved (Decision 7)."""
    if guest.stay_links.exists() or guest.primary_stays.exists():
        return True
    if guest.folios.exists():
        return True
    if guest.lost_found_items.exists():
        return True
    # A guest carrying a reservation (as primary guest or a named occupant) — an
    # upcoming booking included — keeps history and must not hard-delete.
    if guest.reservations.exists() or guest.reservation_occupancies.exists():
        return True
    # A block-log entry is security history; the guest FK is PROTECTed, so a hard
    # delete would raise anyway — deactivate instead.
    if guest.block_logs.exists():
        return True
    return False


@transaction.atomic
def deactivate_or_delete(guest, *, user=None) -> str:
    """Delete hardening: a guest with ANY operational trace is deactivated
    (history preserved); only a truly untouched profile hard-deletes.
    Returns ``"deactivated"`` or ``"deleted"`` so the UI can say the truth."""
    if guest_has_operational_traces(guest):
        if guest.is_active:
            guest.is_active = False
            guest.updated_by = _actor(user)
            guest.save(update_fields=["is_active", "updated_by", "updated_at"])
        _record(
            guest,
            event_type="guest.deactivated",
            severity="info",
            title=f"Guest deactivated: {guest.full_name}",
            message="history preserved",
            user=user,
        )
        return "deactivated"
    name = guest.full_name
    _record(
        guest,
        event_type="guest.deleted",
        severity="info",
        title=f"Guest deleted: {name}",
        message="no operational history",
        user=user,
    )
    guest.delete()
    return "deleted"


def ensure_guest_not_blocked(*guests) -> None:
    """Refuse operations for any blocked guest (used by check-in)."""
    for guest in guests:
        if guest is not None and guest.is_blocked:
            raise GuestBlocked({"guest": guest.id})
