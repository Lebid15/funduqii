"""Operations domain services (Phase 10) — the single write path.

Views never mutate operations records directly. Every room status change goes
through ``apps.rooms.services.change_room_status`` (the Phase 5 controlled
path) so it is validated and logged in ``RoomStatusLog``.

Room-status rules enforced here:
- Housekeeping may set a dirty/available room to ``cleaning`` when a task
  starts, and back to ``dirty`` or (explicitly, when safe) ``available`` when
  it completes. It may NEVER release a room that is ``maintenance`` /
  ``out_of_service`` / ``archived`` or that has an open blocking maintenance
  request.
- Maintenance may block a room (``maintenance`` / ``out_of_service``) when the
  request affects availability. Closing NEVER auto-releases the room — the
  closer explicitly chooses dirty / available / keep.
- Nothing here ever writes an ``occupied`` status; occupancy stays derived
  from in-house stays (Phase 7 rule).
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import (
    CancellationReasonRequired,
    ClaimantRequired,
    CrossTenantReference,
    DisposalReasonRequired,
    DuplicateActiveTask,
    InspectionReasonRequired,
    InvalidOperationStatusTransition,
    OperationNotEditable,
    RoomBlockedByMaintenance,
    RoomNotReleasable,
)
from apps.rooms.models import Room, RoomStatus
from apps.rooms.services import RoomReleaseCycle, change_room_status
from apps.tenancy.models import HotelMembership

from .models import (
    HousekeepingStatus,
    HousekeepingTask,
    HousekeepingTaskStatusLog,
    HousekeepingTaskType,
    LostFoundItem,
    LostFoundItemStatusLog,
    LostFoundStatus,
    MaintenanceRequest,
    MaintenanceRequestStatusLog,
    MaintenanceStatus,
    OperationsNumberSequence,
    RoomBlockStatus,
)

NUMBER_PREFIXES = {
    "housekeeping": "HK",
    "maintenance": "MT",
    "lost_found": "LF",
}

#: Room statuses housekeeping may move to `cleaning` when a task starts.
CLEANABLE_ROOM_STATUSES = (RoomStatus.DIRTY, RoomStatus.AVAILABLE)
#: Room statuses housekeeping may never override to `available`.
BLOCKED_ROOM_STATUSES = (
    RoomStatus.MAINTENANCE,
    RoomStatus.OUT_OF_SERVICE,
    RoomStatus.ARCHIVED,
)

#: Maintenance statuses considered "open" (may still block a room).
OPEN_MAINTENANCE_STATUSES = (
    MaintenanceStatus.OPEN,
    MaintenanceStatus.ASSIGNED,
    MaintenanceStatus.IN_PROGRESS,
)

#: Active (still workable) statuses per workflow. awaiting_inspection counts
#: as ACTIVE (final closure): the room's cycle is not finished until a
#: supervisor approves, so it also blocks a second task on the same room.
ACTIVE_HK_STATUSES = (
    HousekeepingStatus.PENDING,
    HousekeepingStatus.ASSIGNED,
    HousekeepingStatus.IN_PROGRESS,
    HousekeepingStatus.AWAITING_INSPECTION,
)

#: Severity order for priority sorting (never sort the raw CharField —
#: alphabetical order puts high < low). Lower rank = more urgent.
PRIORITY_RANK = {
    "urgent": 0,
    "high": 1,
    "normal": 2,
    "low": 3,
}


def order_by_priority_rank(qs, *, ordering: str, time_field: str):
    """Order an operations queryset by LOGICAL priority severity.

    The single sort used by BOTH the housekeeping and maintenance lists so the
    two can never diverge. Priority is ranked by :data:`PRIORITY_RANK`
    (urgent → high → normal → low), never by the raw ``priority`` CharField
    (alphabetical would give high < low < normal < urgent).

    ``ordering`` is ``"priority"`` (most urgent first) or ``"-priority"``
    (reverse). Ties break on the newest record first (``-<time_field>``) then
    ``-id`` for a fully deterministic order, matching each model's default
    ``Meta.ordering``. ``time_field`` is the list's own timestamp column
    (``requested_at`` for housekeeping, ``reported_at`` for maintenance).
    """
    from django.db.models import Case, IntegerField, Value, When

    rank = Case(
        *[
            When(priority=value, then=Value(severity))
            for value, severity in PRIORITY_RANK.items()
        ],
        default=Value(9),
        output_field=IntegerField(),
    )
    rank_order = "priority_rank" if ordering == "priority" else "-priority_rank"
    return qs.annotate(priority_rank=rank).order_by(
        rank_order, f"-{time_field}", "-id"
    )


def _hk_record(task, *, event_type, severity, title, message, user=None):
    """Activity entry for a housekeeping task (lazy import, one shape)."""
    from apps.notifications.services import record_activity

    record_activity(
        task.hotel,
        event_type=event_type,
        category="operation",
        severity=severity,
        title=title,
        message=message,
        actor=user,
        related_object=task,
        related_url="/hotel/operations",
    )
ACTIVE_LF_STATUSES = (
    LostFoundStatus.FOUND,
    LostFoundStatus.STORED,
    LostFoundStatus.CLAIMED,
)

#: Forward-only transitions available through the GENERIC status endpoints.
#: Terminal moves (complete/resolve/close/cancel/claim/return/dispose) have
#: their own entry points with their own required inputs.
HK_STATUS_TRANSITIONS = {
    HousekeepingStatus.PENDING: {
        HousekeepingStatus.ASSIGNED,
        HousekeepingStatus.IN_PROGRESS,
    },
    HousekeepingStatus.ASSIGNED: {HousekeepingStatus.IN_PROGRESS},
    HousekeepingStatus.IN_PROGRESS: set(),
    HousekeepingStatus.COMPLETED: set(),
    HousekeepingStatus.CANCELLED: set(),
}
MT_STATUS_TRANSITIONS = {
    MaintenanceStatus.OPEN: {
        MaintenanceStatus.ASSIGNED,
        MaintenanceStatus.IN_PROGRESS,
    },
    MaintenanceStatus.ASSIGNED: {MaintenanceStatus.IN_PROGRESS},
    MaintenanceStatus.IN_PROGRESS: set(),
    MaintenanceStatus.RESOLVED: set(),
    MaintenanceStatus.CLOSED: set(),
    MaintenanceStatus.CANCELLED: set(),
}
LF_STATUS_TRANSITIONS = {
    LostFoundStatus.FOUND: {LostFoundStatus.STORED},
    LostFoundStatus.STORED: set(),
    LostFoundStatus.CLAIMED: set(),
    LostFoundStatus.RETURNED: set(),
    LostFoundStatus.DISPOSED: set(),
    LostFoundStatus.CLOSED: set(),
}


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def next_number(hotel, kind: str) -> str:
    """Allocate the next per-hotel HK/MT/LF number (row-locked; needs a txn)."""
    prefix = NUMBER_PREFIXES[kind]
    seq, _ = OperationsNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel, kind=kind
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"{prefix}{seq.last_number:05d}"


def _check_same_hotel(hotel, *, field: str, obj) -> None:
    if obj is not None and obj.hotel_id != hotel.id:
        raise CrossTenantReference({"field": field})


def _check_assignee(hotel, user) -> None:
    """An assignee must be an ACTIVE member of the same hotel."""
    if user is None:
        return
    is_member = HotelMembership.objects.filter(
        hotel=hotel, user=user, is_active=True
    ).exists()
    if not is_member:
        raise CrossTenantReference({"field": "assigned_to"})


def room_has_blocking_maintenance(room: Room, *, exclude_id=None) -> bool:
    """True when an open maintenance request still blocks this room."""
    qs = MaintenanceRequest.objects.filter(
        room=room,
        affects_room_availability=True,
        status__in=OPEN_MAINTENANCE_STATUSES,
    ).exclude(room_block_status=RoomBlockStatus.NONE)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def _room_has_active_housekeeping(room: Room) -> bool:
    """True while the room's cleaning cycle is not finished — an ACTIVE task
    exists (pending / assigned / in_progress / awaiting_inspection). The task
    being resolved by the current release path is completed BEFORE this check,
    so it never counts against its own release."""
    return HousekeepingTask.objects.filter(
        room=room, status__in=ACTIVE_HK_STATUSES
    ).exists()


def _ensure_room_releasable(room: Room, *, exclude_request_id=None) -> None:
    """Guard for any attempt to mark a room `available` from operations.

    Ordering matters: the maintenance guards run FIRST and keep raising the
    maintenance-specific ``RoomBlockedByMaintenance`` (backward-compat with the
    409s already asserted). The NEW generic conditions (dirty room / active
    cleaning task) raise ``RoomNotReleasable`` with a neutral ``details.reason``.
    """
    if room.status in BLOCKED_ROOM_STATUSES and exclude_request_id is None:
        raise RoomBlockedByMaintenance({"room": room.id, "status": room.status})
    if room_has_blocking_maintenance(room, exclude_id=exclude_request_id):
        raise RoomBlockedByMaintenance({"room": room.id, "reason": "open_request"})
    if room.status == RoomStatus.DIRTY:
        raise RoomNotReleasable({"reason": "room_dirty"})
    if _room_has_active_housekeeping(room):
        raise RoomNotReleasable({"reason": "active_housekeeping"})


def _lock_room(room_id):
    """Row-lock the room for a read-then-write status transition (``SELECT ...
    FOR UPDATE``). Must run inside a transaction; a no-op on SQLite (dev/tests).
    Returns the locked instance, or ``None`` when the record has no room."""
    if room_id is None:
        return None
    return Room.objects.select_for_update().get(pk=room_id)


def _release_room(
    room: Room,
    *,
    user,
    note: str,
    cycle_source: RoomReleaseCycle,
    exclude_request_id=None,
) -> None:
    """The ONE operations path to ``available`` — releasability is re-checked
    HERE and only then does the rooms controlled path run with the internal
    ``cycle_source`` marker. Every release funnels through this helper, so a
    future path cannot reach ``change_room_status(..., AVAILABLE)`` without the
    checks (bypass is prevented by construction). ``room`` must already be
    row-locked by the caller."""
    _ensure_room_releasable(room, exclude_request_id=exclude_request_id)
    if room.status != RoomStatus.AVAILABLE:
        change_room_status(
            room,
            RoomStatus.AVAILABLE,
            note=note,
            user=user,
            cycle_source=cycle_source,
        )


# --- Housekeeping ---------------------------------------------------------------


def _hk_log(task, previous, new, user, note=""):
    HousekeepingTaskStatusLog.objects.create(
        hotel=task.hotel,
        task=task,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


def _hk_start(task: HousekeepingTask, user) -> None:
    """Side effects of moving a task to in_progress."""
    task.started_at = task.started_at or timezone.now()
    # Row-lock the room for this read-then-write status transition (runs inside
    # the caller's atomic block) so start-cleaning cannot race a concurrent
    # maintenance block (AVAILABLE -> MAINTENANCE) on the same room. Status
    # logic is unchanged.
    room = _lock_room(task.room_id)
    if room is not None and room.status in CLEANABLE_ROOM_STATUSES:
        change_room_status(
            room,
            RoomStatus.CLEANING,
            note=f"Housekeeping {task.task_number}",
            user=user,
        )


@transaction.atomic
def create_housekeeping_task(
    hotel,
    *,
    user=None,
    room,
    stay=None,
    task_type=HousekeepingTaskType.DAILY_CLEANING,
    priority,
    assigned_to=None,
    notes="",
    internal_notes="",
    on_active="raise",
) -> HousekeepingTask | None:
    _check_same_hotel(hotel, field="room", obj=room)
    _check_same_hotel(hotel, field="stay", obj=stay)
    _check_assignee(hotel, assigned_to)
    # Final closure: at most ONE active task per room. The room row is
    # locked so two concurrent creations serialize; automatic callers
    # (check-out / room move) pass on_active="skip" so an existing active
    # task never breaks their own transaction.
    room = Room.objects.select_for_update().get(pk=room.pk)
    if HousekeepingTask.objects.filter(
        hotel=hotel, room=room, status__in=ACTIVE_HK_STATUSES
    ).exists():
        if on_active == "skip":
            return None
        raise DuplicateActiveTask({"room": room.id})
    actor = _actor(user)
    # DB-backed backstop: the partial-unique constraint
    # ``uniq_active_housekeeping_task_per_room`` (migration 0003) is the last
    # line of defence if a concurrent active task slips past the
    # select_for_update() + exists() guard above (e.g. a race the row lock did
    # not serialize). The INSERT runs inside a savepoint so a violation rolls
    # back only the failed INSERT (and its sequence bump) and surfaces as a
    # clean 409 — never a raw 500 — while automatic callers still skip.
    try:
        with transaction.atomic():
            task = HousekeepingTask.objects.create(
                hotel=hotel,
                task_number=next_number(hotel, "housekeeping"),
                room=room,
                stay=stay,
                task_type=task_type,
                status=(
                    HousekeepingStatus.ASSIGNED
                    if assigned_to
                    else HousekeepingStatus.PENDING
                ),
                priority=priority,
                assigned_to=assigned_to,
                notes=notes or "",
                internal_notes=internal_notes or "",
                created_by=actor,
                updated_by=actor,
            )
    except IntegrityError:
        if on_active == "skip":
            return None
        raise DuplicateActiveTask({"room": room.id})
    _hk_log(task, "", task.status, user)
    # Phase 14: activity + notifications (lazy import).
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="housekeeping.task_created",
        category="operation",
        severity="info",
        title=f"Housekeeping task {task.task_number} created",
        message=f"Room {room.number} · {task.task_type}",
        actor=user,
        related_object=task,
        related_url="/hotel/operations",
    )
    return task


@transaction.atomic
def create_checkout_cleaning_task(stay, *, user=None) -> HousekeepingTask | None:
    """Auto-create ONE check-out cleaning task for a stay (idempotent).

    Called from the Phase 7 check-out service inside its transaction. Creating
    the task cannot realistically fail (no external dependencies), and a
    second check-out of the same stay is already impossible upstream — the
    exists() check below keeps it idempotent regardless.
    """
    if HousekeepingTask.objects.filter(
        hotel=stay.hotel,
        stay=stay,
        task_type=HousekeepingTaskType.CHECKOUT_CLEANING,
    ).exists():
        return None
    from .models import OperationPriority

    # on_active="skip": if the room already carries an active task (e.g. a
    # manual deep-clean), check-out must never fail — the room is already on
    # housekeeping's plate.
    return create_housekeeping_task(
        stay.hotel,
        user=user,
        room=stay.room,
        stay=stay,
        task_type=HousekeepingTaskType.CHECKOUT_CLEANING,
        priority=OperationPriority.NORMAL,
        on_active="skip",
    )


@transaction.atomic
def update_housekeeping_task(task: HousekeepingTask, *, user=None, **meta) -> HousekeepingTask:
    """Edit task metadata (type/priority/notes) while it is still active."""
    if task.status not in ACTIVE_HK_STATUSES:
        raise OperationNotEditable({"status": task.status})
    old_priority = task.priority
    for field in ("task_type", "priority", "notes", "internal_notes"):
        if field in meta:
            setattr(task, field, meta[field])
    task.updated_by = _actor(user)
    task.save()
    if task.priority != old_priority:
        _hk_record(
            task,
            event_type="housekeeping.priority_changed",
            severity="info",
            title=f"Housekeeping task {task.task_number} priority changed",
            message=f"{old_priority} → {task.priority}",
            user=user,
        )
    return task


@transaction.atomic
def assign_housekeeping_task(task: HousekeepingTask, *, assigned_to, user=None) -> HousekeepingTask:
    if task.status not in ACTIVE_HK_STATUSES:
        raise OperationNotEditable({"status": task.status})
    _check_assignee(task.hotel, assigned_to)
    previous_status = task.status
    previous_assignee = task.assigned_to
    task.assigned_to = assigned_to
    if task.status == HousekeepingStatus.PENDING and assigned_to is not None:
        task.status = HousekeepingStatus.ASSIGNED
    elif assigned_to is None and task.status == HousekeepingStatus.ASSIGNED:
        # Final closure: unassigning returns the task to the open pool.
        task.status = HousekeepingStatus.PENDING
    task.updated_by = _actor(user)
    task.save()
    if task.status != previous_status:
        _hk_log(task, previous_status, task.status, user)
    if previous_assignee != assigned_to:
        if assigned_to is None:
            event, title_verb = "housekeeping.task_unassigned", "unassigned"
        elif previous_assignee is None:
            event, title_verb = "housekeeping.task_assigned", "assigned"
        else:
            event, title_verb = "housekeeping.task_reassigned", "reassigned"
        _hk_record(
            task,
            event_type=event,
            severity="info",
            title=f"Housekeeping task {task.task_number} {title_verb}",
            message=(
                f"{previous_assignee.email if previous_assignee else '—'} → "
                f"{assigned_to.email if assigned_to else '—'}"
            ),
            user=user,
        )
    return task


@transaction.atomic
def change_housekeeping_status(
    task: HousekeepingTask, *, new_status, user=None, note=""
) -> HousekeepingTask:
    if new_status in (HousekeepingStatus.COMPLETED, HousekeepingStatus.CANCELLED):
        # Terminal moves have their own entry points (safety flag / reason).
        raise InvalidOperationStatusTransition({"reason": "use_dedicated_endpoint"})
    if new_status not in HK_STATUS_TRANSITIONS.get(task.status, set()):
        raise InvalidOperationStatusTransition({"from": task.status, "to": new_status})
    previous = task.status
    task.status = new_status
    if new_status == HousekeepingStatus.IN_PROGRESS:
        _hk_start(task, user)
    task.updated_by = _actor(user)
    task.save()
    _hk_log(task, previous, new_status, user, note)
    if new_status == HousekeepingStatus.IN_PROGRESS:
        _hk_record(
            task,
            event_type="housekeeping.task_started",
            severity="info",
            title=f"Housekeeping task {task.task_number} started",
            message=f"Room {task.room.number}" if task.room_id else "",
            user=user,
        )
    return task


def _inspection_required(hotel) -> bool:
    """The per-hotel inspection policy (safe when settings don't exist yet)."""
    settings_obj = getattr(hotel, "settings", None)
    return bool(
        settings_obj and settings_obj.housekeeping_inspection_required
    )


@transaction.atomic
def complete_housekeeping_task(
    task: HousekeepingTask, *, user=None, mark_room_available=False, note=""
) -> HousekeepingTask:
    if task.status not in ACTIVE_HK_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": task.status, "to": HousekeepingStatus.COMPLETED}
        )
    # Inspection policy (final closure): with the hotel setting ON, the
    # attendant's completion parks the task for a supervisor — the room is
    # NOT released and mark_room_available is ignored. Approving is the only
    # path to completed. (A task already awaiting inspection can only move
    # through approve/reject, never through this endpoint again.)
    if task.status == HousekeepingStatus.AWAITING_INSPECTION:
        raise InvalidOperationStatusTransition(
            {"from": task.status, "reason": "use_inspection_endpoint"}
        )
    if _inspection_required(task.hotel):
        previous = task.status
        task.status = HousekeepingStatus.AWAITING_INSPECTION
        task.started_at = task.started_at or timezone.now()
        task.updated_by = _actor(user)
        task.save()
        _hk_log(task, previous, task.status, user, note)
        _hk_record(
            task,
            event_type="housekeeping.awaiting_inspection",
            severity="info",
            title=f"Housekeeping task {task.task_number} awaiting inspection",
            message=f"Room {task.room.number}" if task.room_id else "",
            user=user,
        )
        return task
    previous = task.status
    task.status = HousekeepingStatus.COMPLETED
    task.started_at = task.started_at or timezone.now()
    task.completed_at = timezone.now()
    task.updated_by = _actor(user)
    task.save()
    # Row-lock the room for the read-then-write status transition. The task is
    # already COMPLETED above, so it never counts against its own release.
    room = _lock_room(task.room_id)
    if room is not None:
        if mark_room_available:
            # ONE release helper: never override a hard block or an open
            # blocking request, and never release a dirty room or one that
            # still has another active cleaning task.
            _release_room(
                room,
                user=user,
                note=f"Housekeeping {task.task_number} completed",
                cycle_source=RoomReleaseCycle.HOUSEKEEPING_RELEASE,
            )
        elif room.status == RoomStatus.CLEANING:
            # Task done but the room was not released — back to dirty so it
            # stays visibly not-ready (explicit release only).
            change_room_status(
                room,
                RoomStatus.DIRTY,
                note=f"Housekeeping {task.task_number} completed (not released)",
                user=user,
            )
    _hk_log(task, previous, HousekeepingStatus.COMPLETED, user, note)
    from apps.notifications.services import record_activity

    record_activity(
        task.hotel,
        event_type="housekeeping.task_completed",
        category="operation",
        severity="success",
        title=f"Housekeeping task {task.task_number} completed",
        message=f"Room {room.number}" if room is not None else "",
        actor=user,
        related_object=task,
        related_url="/hotel/operations",
    )
    return task


@transaction.atomic
def cancel_housekeeping_task(task: HousekeepingTask, *, reason, user=None) -> HousekeepingTask:
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    if task.status not in ACTIVE_HK_STATUSES:
        raise OperationNotEditable({"status": task.status})
    previous = task.status
    task.status = HousekeepingStatus.CANCELLED
    task.cancelled_at = timezone.now()
    task.cancellation_reason = reason.strip()
    task.updated_by = _actor(user)
    task.save()
    # Row-lock the room for the read-then-write status transition.
    room = _lock_room(task.room_id)
    if room is not None and room.status == RoomStatus.CLEANING:
        # The task that (likely) put the room into `cleaning` is gone; the
        # room goes back to dirty rather than staying in a stale state.
        change_room_status(
            room,
            RoomStatus.DIRTY,
            note=f"Housekeeping {task.task_number} cancelled",
            user=user,
        )
    _hk_log(task, previous, HousekeepingStatus.CANCELLED, user, reason.strip())
    _hk_record(
        task,
        event_type="housekeeping.task_cancelled",
        severity="warning",
        title=f"Housekeeping task {task.task_number} cancelled",
        message=reason.strip(),
        user=user,
    )
    return task


@transaction.atomic
def approve_inspection(task: HousekeepingTask, *, user=None, note="") -> HousekeepingTask:
    """Supervisor approval: the task completes and the room is released —
    unless maintenance still blocks it (maintenance stays the master)."""
    if task.status != HousekeepingStatus.AWAITING_INSPECTION:
        raise InvalidOperationStatusTransition(
            {"from": task.status, "to": HousekeepingStatus.COMPLETED}
        )
    # Row-lock the room for the read-then-write release.
    room = _lock_room(task.room_id)
    previous = task.status
    # Complete the task BEFORE the releasability check so this (awaiting-
    # inspection = ACTIVE) task never counts against its own release. If the
    # check then refuses (e.g. maintenance appeared), the whole atomic block
    # rolls the completion back and the task stays awaiting inspection.
    task.status = HousekeepingStatus.COMPLETED
    task.completed_at = timezone.now()
    task.updated_by = _actor(user)
    task.save()
    if room is not None:
        _release_room(
            room,
            user=user,
            note=f"Housekeeping {task.task_number} inspection approved",
            cycle_source=RoomReleaseCycle.HOUSEKEEPING_RELEASE,
        )
    _hk_log(task, previous, HousekeepingStatus.COMPLETED, user, note or "inspection approved")
    _hk_record(
        task,
        event_type="housekeeping.inspection_approved",
        severity="success",
        title=f"Housekeeping task {task.task_number} inspection approved",
        message=f"Room {room.number}" if room is not None else "",
        user=user,
    )
    return task


@transaction.atomic
def reject_inspection(task: HousekeepingTask, *, reason, user=None) -> HousekeepingTask:
    """Supervisor rejection: the room goes back to dirty and the task returns
    to in_progress so the attendant can finish it again. The rejection reason
    is mandatory and preserved in the status log."""
    if not (reason or "").strip():
        raise InspectionReasonRequired()
    if task.status != HousekeepingStatus.AWAITING_INSPECTION:
        raise InvalidOperationStatusTransition(
            {"from": task.status, "to": HousekeepingStatus.IN_PROGRESS}
        )
    previous = task.status
    task.status = HousekeepingStatus.IN_PROGRESS
    task.updated_by = _actor(user)
    task.save()
    # Row-lock the room for the read-then-write status transition.
    room = _lock_room(task.room_id)
    if room is not None and room.status in (
        RoomStatus.CLEANING,
        RoomStatus.AVAILABLE,
    ):
        change_room_status(
            room,
            RoomStatus.DIRTY,
            note=f"Housekeeping {task.task_number} inspection rejected",
            user=user,
        )
    _hk_log(task, previous, HousekeepingStatus.IN_PROGRESS, user, reason.strip())
    _hk_record(
        task,
        event_type="housekeeping.inspection_rejected",
        severity="warning",
        title=f"Housekeeping task {task.task_number} inspection rejected",
        message=reason.strip(),
        user=user,
    )
    return task


# --- Maintenance ------------------------------------------------------------------


def _mt_log(request, previous, new, user, note=""):
    MaintenanceRequestStatusLog.objects.create(
        hotel=request.hotel,
        request=request,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


def _apply_room_block(request: MaintenanceRequest, user) -> None:
    """Move the room into the request's block status (maintenance/oos)."""
    if (
        request.room_id is None
        or not request.affects_room_availability
        or request.room_block_status == RoomBlockStatus.NONE
    ):
        return
    target = (
        RoomStatus.MAINTENANCE
        if request.room_block_status == RoomBlockStatus.MAINTENANCE
        else RoomStatus.OUT_OF_SERVICE
    )
    # Row-lock the room for the read-then-write block transition.
    room = _lock_room(request.room_id)
    if room.status in (target, RoomStatus.ARCHIVED):
        return
    change_room_status(
        room,
        target,
        note=f"Maintenance {request.request_number}: {request.title}"[:255],
        user=user,
    )


@transaction.atomic
def create_maintenance_request(
    hotel,
    *,
    user=None,
    room=None,
    stay=None,
    title,
    description="",
    category,
    priority,
    affects_room_availability=False,
    room_block_status=RoomBlockStatus.NONE,
    assigned_to=None,
    internal_notes="",
) -> MaintenanceRequest:
    _check_same_hotel(hotel, field="room", obj=room)
    _check_same_hotel(hotel, field="stay", obj=stay)
    _check_assignee(hotel, assigned_to)
    actor = _actor(user)
    request = MaintenanceRequest.objects.create(
        hotel=hotel,
        request_number=next_number(hotel, "maintenance"),
        room=room,
        stay=stay,
        title=title,
        description=description or "",
        category=category,
        priority=priority,
        status=(
            MaintenanceStatus.ASSIGNED if assigned_to else MaintenanceStatus.OPEN
        ),
        affects_room_availability=affects_room_availability,
        room_block_status=room_block_status,
        assigned_to=assigned_to,
        internal_notes=internal_notes or "",
        created_by=actor,
        updated_by=actor,
    )
    _apply_room_block(request, user)
    _mt_log(request, "", request.status, user)
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="maintenance.request_created",
        category="operation",
        severity="warning",
        title=f"Maintenance request {request.request_number} created",
        message=f"{request.title}" + (f" · Room {room.number}" if room else ""),
        actor=user,
        related_object=request,
        related_url="/hotel/operations",
    )
    return request


@transaction.atomic
def update_maintenance_request(
    request: MaintenanceRequest, *, user=None, **meta
) -> MaintenanceRequest:
    """Edit request metadata while it is still open/assigned/in_progress.

    Changing the block fields to a blocking value applies it to the room
    immediately; changing them back to none NEVER auto-releases the room —
    release happens only through the explicit close action.
    """
    if request.status not in OPEN_MAINTENANCE_STATUSES:
        raise OperationNotEditable({"status": request.status})
    for field in (
        "title",
        "description",
        "category",
        "priority",
        "internal_notes",
        "affects_room_availability",
        "room_block_status",
    ):
        if field in meta:
            setattr(request, field, meta[field])
    request.updated_by = _actor(user)
    request.save()
    _apply_room_block(request, user)
    return request


@transaction.atomic
def assign_maintenance_request(
    request: MaintenanceRequest, *, assigned_to, user=None
) -> MaintenanceRequest:
    if request.status not in OPEN_MAINTENANCE_STATUSES:
        raise OperationNotEditable({"status": request.status})
    _check_assignee(request.hotel, assigned_to)
    previous = request.status
    request.assigned_to = assigned_to
    if request.status == MaintenanceStatus.OPEN and assigned_to is not None:
        request.status = MaintenanceStatus.ASSIGNED
    request.updated_by = _actor(user)
    request.save()
    if request.status != previous:
        _mt_log(request, previous, request.status, user)
    return request


@transaction.atomic
def change_maintenance_status(
    request: MaintenanceRequest, *, new_status, user=None, note=""
) -> MaintenanceRequest:
    if new_status in (
        MaintenanceStatus.RESOLVED,
        MaintenanceStatus.CLOSED,
        MaintenanceStatus.CANCELLED,
    ):
        raise InvalidOperationStatusTransition({"reason": "use_dedicated_endpoint"})
    if new_status not in MT_STATUS_TRANSITIONS.get(request.status, set()):
        raise InvalidOperationStatusTransition(
            {"from": request.status, "to": new_status}
        )
    previous = request.status
    request.status = new_status
    if new_status == MaintenanceStatus.IN_PROGRESS:
        request.started_at = request.started_at or timezone.now()
    request.updated_by = _actor(user)
    request.save()
    _mt_log(request, previous, new_status, user, note)
    return request


@transaction.atomic
def resolve_maintenance_request(
    request: MaintenanceRequest, *, user=None, resolution_notes="", note=""
) -> MaintenanceRequest:
    if request.status not in OPEN_MAINTENANCE_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": request.status, "to": MaintenanceStatus.RESOLVED}
        )
    previous = request.status
    request.status = MaintenanceStatus.RESOLVED
    request.resolved_at = timezone.now()
    if resolution_notes:
        request.resolution_notes = resolution_notes
    request.updated_by = _actor(user)
    request.save()
    _mt_log(request, previous, MaintenanceStatus.RESOLVED, user, note)
    from apps.notifications.services import record_activity

    record_activity(
        request.hotel,
        event_type="maintenance.request_resolved",
        category="operation",
        severity="success",
        title=f"Maintenance request {request.request_number} resolved",
        message=request.title,
        actor=user,
        related_object=request,
        related_url="/hotel/operations",
    )
    return request


ROOM_NEXT_STATUS_CHOICES = ("keep", "dirty", "available")


@transaction.atomic
def close_maintenance_request(
    request: MaintenanceRequest, *, user=None, room_next_status="keep", note=""
) -> MaintenanceRequest:
    """Close a RESOLVED request; the closer explicitly picks the room's next
    status (keep / dirty / available) — no dangerous automatic release."""
    if request.status != MaintenanceStatus.RESOLVED:
        raise InvalidOperationStatusTransition(
            {"from": request.status, "to": MaintenanceStatus.CLOSED}
        )
    previous = request.status
    request.status = MaintenanceStatus.CLOSED
    request.closed_at = timezone.now()
    request.updated_by = _actor(user)
    request.save()
    # Row-lock the room for the read-then-write transition.
    room = _lock_room(request.room_id)
    if room is not None and room_next_status != "keep":
        if room.status == RoomStatus.ARCHIVED:
            raise InvalidOperationStatusTransition({"reason": "room_archived"})
        note_txt = f"Maintenance {request.request_number} closed"[:255]
        if room_next_status == "available":
            # Release through the ONE helper: another open blocking request — or
            # a dirty / still-being-cleaned room — keeps it out of inventory.
            # The maintenance-close cycle is the only one authorized to clear
            # this request's own maintenance/out-of-service block.
            _release_room(
                room,
                user=user,
                note=note_txt,
                cycle_source=RoomReleaseCycle.MAINTENANCE_CLOSE,
                exclude_request_id=request.id,
            )
        elif room.status != RoomStatus.DIRTY:
            change_room_status(room, RoomStatus.DIRTY, note=note_txt, user=user)
    _mt_log(request, previous, MaintenanceStatus.CLOSED, user, note)
    from apps.notifications.services import record_activity

    record_activity(
        request.hotel,
        event_type="maintenance.request_closed",
        category="operation",
        severity="info",
        title=f"Maintenance {request.request_number} closed",
        message=f"room next status: {room_next_status}",
        actor=user,
        related_object=request,
        related_url="/hotel/operations",
    )
    return request


@transaction.atomic
def cancel_maintenance_request(
    request: MaintenanceRequest, *, reason, user=None
) -> MaintenanceRequest:
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    if request.status not in OPEN_MAINTENANCE_STATUSES:
        raise OperationNotEditable({"status": request.status})
    previous = request.status
    request.status = MaintenanceStatus.CANCELLED
    request.cancelled_at = timezone.now()
    request.cancellation_reason = reason.strip()
    request.updated_by = _actor(user)
    request.save()
    # If THIS request blocked the room and nothing else still blocks it, the
    # room drops to dirty (never straight to available — it needs inspection).
    # Row-lock the room for the read-then-write transition.
    room = _lock_room(request.room_id)
    if (
        room is not None
        and request.affects_room_availability
        and request.room_block_status != RoomBlockStatus.NONE
        and room.status in (RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE)
        and not room_has_blocking_maintenance(room, exclude_id=request.id)
    ):
        change_room_status(
            room,
            RoomStatus.DIRTY,
            note=f"Maintenance {request.request_number} cancelled"[:255],
            user=user,
        )
    _mt_log(request, previous, MaintenanceStatus.CANCELLED, user, reason.strip())
    from apps.notifications.services import record_activity

    record_activity(
        request.hotel,
        event_type="maintenance.request_cancelled",
        category="operation",
        severity="warning",
        title=f"Maintenance {request.request_number} cancelled",
        message=reason.strip(),
        actor=user,
        related_object=request,
        related_url="/hotel/operations",
    )
    return request


# --- Lost & Found -----------------------------------------------------------------


def _lf_log(item, previous, new, user, note=""):
    LostFoundItemStatusLog.objects.create(
        hotel=item.hotel,
        item=item,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


@transaction.atomic
def create_lost_found_item(
    hotel,
    *,
    user=None,
    title,
    description="",
    category,
    status=LostFoundStatus.FOUND,
    found_at=None,
    found_location="",
    room=None,
    stay=None,
    guest=None,
    stored_location="",
    notes="",
    internal_notes="",
) -> LostFoundItem:
    _check_same_hotel(hotel, field="room", obj=room)
    _check_same_hotel(hotel, field="stay", obj=stay)
    _check_same_hotel(hotel, field="guest", obj=guest)
    actor = _actor(user)
    item = LostFoundItem.objects.create(
        hotel=hotel,
        item_number=next_number(hotel, "lost_found"),
        title=title,
        description=description or "",
        category=category,
        status=status,
        found_at=found_at or timezone.now(),
        found_location=found_location or "",
        room=room,
        stay=stay,
        guest=guest,
        found_by=actor,
        stored_location=stored_location or "",
        notes=notes or "",
        internal_notes=internal_notes or "",
        created_by=actor,
        updated_by=actor,
    )
    _lf_log(item, "", item.status, user)
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="lost_found.item_created",
        category="operation",
        severity="info",
        title=f"Lost & found {item.item_number} recorded",
        message=f"{item.title}"
        + (f" · room {room.number}" if room is not None else ""),
        actor=user,
        related_object=item,
        related_url="/hotel/operations",
    )
    return item


@transaction.atomic
def update_lost_found_item(item: LostFoundItem, *, user=None, refs=None, **meta) -> LostFoundItem:
    """Edit item metadata/links while it is still found/stored/claimed."""
    if item.status not in ACTIVE_LF_STATUSES:
        raise OperationNotEditable({"status": item.status})
    refs = refs or {}
    for field in ("room", "stay", "guest"):
        if field in refs:
            _check_same_hotel(item.hotel, field=field, obj=refs[field])
            setattr(item, field, refs[field])
    for field in (
        "title",
        "description",
        "category",
        "found_location",
        "stored_location",
        "notes",
        "internal_notes",
    ):
        if field in meta:
            setattr(item, field, meta[field])
    item.updated_by = _actor(user)
    item.save()
    return item


@transaction.atomic
def change_lost_found_status(
    item: LostFoundItem, *, new_status, user=None, note=""
) -> LostFoundItem:
    """Generic move: only found→stored; the rest use dedicated actions."""
    if new_status not in LF_STATUS_TRANSITIONS.get(item.status, set()):
        raise InvalidOperationStatusTransition({"from": item.status, "to": new_status})
    previous = item.status
    item.status = new_status
    item.updated_by = _actor(user)
    item.save()
    _lf_log(item, previous, new_status, user, note)
    return item


@transaction.atomic
def claim_lost_found_item(
    item: LostFoundItem, *, user=None, claimed_by_name="", claimed_by_phone="", note=""
) -> LostFoundItem:
    if item.status not in (LostFoundStatus.FOUND, LostFoundStatus.STORED):
        raise InvalidOperationStatusTransition(
            {"from": item.status, "to": LostFoundStatus.CLAIMED}
        )
    if not (claimed_by_name or "").strip() and item.guest_id is None:
        raise ClaimantRequired()
    previous = item.status
    item.status = LostFoundStatus.CLAIMED
    item.claimed_by_name = (claimed_by_name or "").strip() or item.claimed_by_name
    item.claimed_by_phone = (claimed_by_phone or "").strip() or item.claimed_by_phone
    item.claimed_at = timezone.now()
    item.updated_by = _actor(user)
    item.save()
    _lf_log(item, previous, LostFoundStatus.CLAIMED, user, note)
    return item


@transaction.atomic
def return_lost_found_item(
    item: LostFoundItem, *, user=None, claimed_by_name="", claimed_by_phone="", note=""
) -> LostFoundItem:
    if item.status not in ACTIVE_LF_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": item.status, "to": LostFoundStatus.RETURNED}
        )
    name = (claimed_by_name or "").strip() or item.claimed_by_name
    # A returned item must record WHO received it: a claimant name or a guest.
    if not name and item.guest_id is None:
        raise ClaimantRequired()
    previous = item.status
    item.status = LostFoundStatus.RETURNED
    item.claimed_by_name = name
    item.claimed_by_phone = (claimed_by_phone or "").strip() or item.claimed_by_phone
    item.claimed_at = item.claimed_at or timezone.now()
    item.returned_at = timezone.now()
    item.updated_by = _actor(user)
    item.save()
    _lf_log(item, previous, LostFoundStatus.RETURNED, user, note)
    from apps.notifications.services import record_activity

    record_activity(
        item.hotel,
        event_type="lost_found.item_returned",
        category="operation",
        severity="success",
        title=f"Lost & found {item.item_number} returned",
        message=name,
        actor=user,
        related_object=item,
        related_url="/hotel/operations",
    )
    return item


@transaction.atomic
def dispose_lost_found_item(item: LostFoundItem, *, reason, user=None) -> LostFoundItem:
    if item.status not in (LostFoundStatus.FOUND, LostFoundStatus.STORED):
        raise InvalidOperationStatusTransition(
            {"from": item.status, "to": LostFoundStatus.DISPOSED}
        )
    if not (reason or "").strip():
        raise DisposalReasonRequired()
    previous = item.status
    item.status = LostFoundStatus.DISPOSED
    item.disposed_at = timezone.now()
    item.updated_by = _actor(user)
    item.save()
    _lf_log(item, previous, LostFoundStatus.DISPOSED, user, reason.strip())
    from apps.notifications.services import record_activity

    record_activity(
        item.hotel,
        event_type="lost_found.item_disposed",
        category="operation",
        severity="warning",
        title=f"Lost & found {item.item_number} disposed",
        message=reason.strip(),
        actor=user,
        related_object=item,
        related_url="/hotel/operations",
    )
    return item


@transaction.atomic
def close_lost_found_item(item: LostFoundItem, *, user=None, note="") -> LostFoundItem:
    if item.status not in (LostFoundStatus.RETURNED, LostFoundStatus.DISPOSED):
        raise InvalidOperationStatusTransition(
            {"from": item.status, "to": LostFoundStatus.CLOSED}
        )
    previous = item.status
    item.status = LostFoundStatus.CLOSED
    item.closed_at = timezone.now()
    item.updated_by = _actor(user)
    item.save()
    _lf_log(item, previous, LostFoundStatus.CLOSED, user, note)
    return item
