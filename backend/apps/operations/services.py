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
    ClaimProofRequired,
    CrossTenantReference,
    DisposalReasonRequired,
    DuplicateActiveTask,
    FoundItemActivelyMatched,
    FoundItemAlreadyMatched,
    FoundItemNotMatchable,
    InspectionReasonRequired,
    InvalidOperationStatusTransition,
    LostReportReasonRequired,
    OperationNotEditable,
    RecipientContactRequired,
    RoomBlockedByMaintenance,
    RoomNotReleasable,
)
from apps.rooms.models import Room, RoomStatus
from apps.rooms.services import RoomReleaseCycle, change_room_status
from apps.tenancy.models import HotelMembership

from .models import (
    HousekeepingServiceOutcome,
    HousekeepingStatus,
    HousekeepingTask,
    HousekeepingTaskStatusLog,
    HousekeepingTaskType,
    LostFoundCategory,
    LostFoundClaimProofType,
    LostFoundItem,
    LostFoundItemStatusLog,
    LostFoundStatus,
    LostReport,
    LostReportStatus,
    LostReportStatusLog,
    MaintenanceRequest,
    MaintenanceRequestStatusLog,
    MaintenanceStatus,
    OperationsNumberSequence,
    RoomBlockStatus,
)

#: WP7 — categories that require stronger proof on handover (claim / return).
#: These are the ACTUAL ``LostFoundCategory`` values (money / jewelry /
#: documents); no new categories were introduced.
SENSITIVE_LOST_FOUND_CATEGORIES = frozenset(
    {
        LostFoundCategory.MONEY,
        LostFoundCategory.JEWELRY,
        LostFoundCategory.DOCUMENTS,
    }
)

#: The maximum characters kept for an ``identity_last4`` proof — a privacy cap
#: so a full national id / passport / card number is never stored.
IDENTITY_LAST4_MAX_LEN = 4

NUMBER_PREFIXES = {
    "housekeeping": "HK",
    "maintenance": "MT",
    "lost_found": "LF",
    "lost_report": "LR",
}

#: A found item is MATCHABLE to a lost report unless it is already terminally
#: handed over / gone (owner rule): matchable = NOT in {returned, disposed,
#: closed}. So found / stored / claimed items are matchable.
NON_MATCHABLE_FOUND_STATUSES = frozenset(
    {
        LostFoundStatus.RETURNED,
        LostFoundStatus.DISPOSED,
        LostFoundStatus.CLOSED,
    }
)

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

#: Active (still open) lost-report statuses — editable + counted as "open".
ACTIVE_LR_STATUSES = (LostReportStatus.OPEN, LostReportStatus.SEARCHING)

#: Forward-only transitions available through the GENERIC lost-report status
#: endpoint. Everything else has its own entry point with its own required
#: inputs: confirm_match (→matched), unmatch (matched→searching, reason),
#: handover (matched→returned, proof), close_unfound / cancel (reason). From
#: ``matched`` the ONLY exits are handover (returned) or unmatch (searching) —
#: never a direct close/cancel.
LR_STATUS_TRANSITIONS = {
    LostReportStatus.OPEN: {LostReportStatus.SEARCHING},
    LostReportStatus.SEARCHING: set(),
    LostReportStatus.MATCHED: set(),
    LostReportStatus.RETURNED: set(),
    LostReportStatus.CLOSED_UNFOUND: set(),
    LostReportStatus.CANCELLED: set(),
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


def _room_is_occupied(room: Room | None) -> bool:
    """Occupancy is DERIVED from ``Stay`` — the single source of truth. A room
    with an IN-HOUSE stay is occupied; there is no ``occupied`` room status and
    this app never introduces one.

    Callers that branch cleaning behaviour on this MUST have the room row-locked
    inside the surrounding atomic block so the read is consistent with the
    completion (a concurrent check-in/check-out on the same room serialises
    behind that lock). ``Stay.room`` is a per-hotel FK, so filtering by room
    alone already scopes to the room's hotel.
    """
    if room is None:
        return False
    from apps.stays.models import Stay, StayStatus

    return Stay.objects.filter(room=room, status=StayStatus.IN_HOUSE).exists()


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
    # maintenance block (AVAILABLE -> MAINTENANCE) on the same room.
    room = _lock_room(task.room_id)
    # Occupancy gate (read under the lock): an OCCUPIED room's status is NEVER
    # changed by the cleaning lifecycle. The cleaning is tracked by the TASK,
    # not the room status — check-in's in-house-Stay guard already prevents
    # double-booking, so leaving the room `available` is safe. Only a VACANT
    # cleanable room flips to `cleaning`.
    if (
        room is not None
        and room.status in CLEANABLE_ROOM_STATUSES
        and not _room_is_occupied(room)
    ):
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
    task: HousekeepingTask,
    *,
    user=None,
    mark_room_available=False,
    note="",
    service_outcome=HousekeepingServiceOutcome.CLEANED,
) -> HousekeepingTask:
    if task.status not in ACTIVE_HK_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": task.status, "to": HousekeepingStatus.COMPLETED}
        )
    # The service result is recorded on completion. `come_back_later` is NOT a
    # valid outcome (it is a separate non-terminal event); the endpoint's
    # serializer rejects it, and a blank/absent value here means the routine
    # "cleaned" result.
    outcome = service_outcome or HousekeepingServiceOutcome.CLEANED
    # Inspection policy (final closure): with the hotel setting ON, the
    # attendant's completion parks the task for a supervisor — the room is
    # NOT released and mark_room_available is ignored. Approving is the only
    # path to completed. (A task already awaiting inspection can only move
    # through approve/reject, never through this endpoint again.) The declared
    # outcome is stored now so it survives the park → approve round-trip.
    if task.status == HousekeepingStatus.AWAITING_INSPECTION:
        raise InvalidOperationStatusTransition(
            {"from": task.status, "reason": "use_inspection_endpoint"}
        )
    if _inspection_required(task.hotel):
        previous = task.status
        task.status = HousekeepingStatus.AWAITING_INSPECTION
        task.started_at = task.started_at or timezone.now()
        task.service_outcome = outcome
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
    task.service_outcome = outcome
    task.updated_by = _actor(user)
    task.save()
    # Row-lock the room for the read-then-write status transition. The task is
    # already COMPLETED above, so it never counts against its own release.
    room = _lock_room(task.room_id)
    # Occupancy is DERIVED from the in-house Stay and read HERE, under the same
    # atomic block that holds the room row-lock. The room-status behaviour
    # branches on occupancy — NOT on task_type: an occupied room's status is
    # left UNCHANGED (no release, no dirty, NO RoomStatusLog from completion),
    # because occupancy already keeps it out of inventory. Only a VACANT room
    # follows the existing check-out cleaning behaviour.
    if room is not None and not _room_is_occupied(room):
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
        message=(
            (f"Room {room.number} · " if room is not None else "") + f"outcome: {outcome}"
        ),
        actor=user,
        related_object=task,
        related_url="/hotel/operations",
    )
    return task


@transaction.atomic
def come_back_later_housekeeping_task(
    task: HousekeepingTask, *, user=None, note=""
) -> HousekeepingTask:
    """Record a NON-TERMINAL ``come_back_later`` event on an active task.

    Used when the attendant cannot service the room right now (guest asleep,
    door chained, "please come back later") but the task is NOT finished. The
    task STAYS ACTIVE — its status is left exactly as it was so it can be
    revisited and completed later — and the event is written to BOTH the
    per-task status log and the activity log so there is an audit trail. This
    is deliberately NOT a completion and NOT a ``service_outcome`` value; there
    is no scheduling system, just the event plus the task staying open.
    """
    if task.status not in (
        HousekeepingStatus.PENDING,
        HousekeepingStatus.ASSIGNED,
        HousekeepingStatus.IN_PROGRESS,
    ):
        # Only workable states can be deferred. awaiting_inspection is the
        # supervisor's queue, and completed/cancelled are terminal.
        raise InvalidOperationStatusTransition(
            {"from": task.status, "reason": "not_deferrable"}
        )
    # Status is intentionally UNCHANGED; we only stamp who touched it and log
    # the event (previous == new marks a revisit rather than a transition).
    task.updated_by = _actor(user)
    task.save(update_fields=["updated_by", "updated_at"])
    _hk_log(task, task.status, task.status, user, note or "come_back_later")
    _hk_record(
        task,
        event_type="housekeeping.come_back_later",
        severity="info",
        title=f"Housekeeping task {task.task_number} — come back later",
        message=(note or "")[:255] or (f"Room {task.room.number}" if task.room_id else ""),
        user=user,
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
    # Occupancy gate (read under the lock): never touch an OCCUPIED room's
    # status. Only a VACANT room left in `cleaning` by this task drops to dirty.
    if (
        room is not None
        and room.status == RoomStatus.CLEANING
        and not _room_is_occupied(room)
    ):
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
    """Supervisor approval: the task completes. A VACANT room is released —
    unless maintenance still blocks it (maintenance stays the master). An
    OCCUPIED room's status is left UNCHANGED (no release, no RoomStatusLog):
    this is the primary in-stay completion path on inspection-enabled hotels,
    and finishing an in-stay cleaning must never corrupt an occupied room."""
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
    # Occupancy gate (read under the lock): only a VACANT room is released.
    if room is not None and not _room_is_occupied(room):
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
    """Supervisor rejection: the task returns to in_progress so the attendant
    can finish it again. A VACANT room goes back to dirty; an OCCUPIED room's
    status is left UNCHANGED (the cleaning lifecycle never mutates an occupied
    room). The rejection reason is mandatory and preserved in the status log."""
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
    # Occupancy gate (read under the lock): only a VACANT room drops to dirty.
    if (
        room is not None
        and room.status in (RoomStatus.CLEANING, RoomStatus.AVAILABLE)
        and not _room_is_occupied(room)
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


def _resolve_claim_proof(
    item: LostFoundItem,
    *,
    claim_proof_type: str,
    claim_proof_reference: str,
    name: str,
    phone: str,
    has_guest: bool,
    require_contact: bool = False,
) -> tuple[str, str]:
    """Validate the handover requirements for a claim / return and return the
    (proof_type, proof_reference) to store.

    The effective proof falls back to what is ALREADY on the item (so a return
    after a proofed claim need not re-enter it), mirroring the name/phone
    fallback. PRIVACY: the returned reference is bounded and NEVER contains a
    full id/passport/card number — for ``identity_last4`` anything longer than
    four characters is rejected outright (for ALL categories, not only the
    sensitive ones).

    * SENSITIVE categories (money / jewelry / documents): require a recipient
      name, a phone OR a linked guest, a ``claim_proof_type`` and a non-empty
      ``claim_proof_reference`` (the short verification description for
      ``ownership_description``). Any missing piece -> :class:`ClaimProofRequired`
      (422) with a neutral ``details.reason`` (never the value). Unaffected by
      ``require_contact`` — this branch already demands name + phone-or-guest.
    * NORMAL categories:
      - ``require_contact`` FALSE (the CLAIM path, unchanged): a recipient name
        OR a linked guest (:class:`ClaimantRequired`). Proof is NOT required.
      - ``require_contact`` TRUE (the RETURN / handover path): a recipient name
        is always required (:class:`ClaimantRequired` if missing) AND a phone OR
        a linked guest (:class:`RecipientContactRequired` if BOTH missing), so a
        handover is never weaker than the found-item return the frontend already
        enforces. Proof is still NOT required for a normal category.
    """
    proof_type = (claim_proof_type or "").strip() or item.claim_proof_type
    proof_reference = (claim_proof_reference or "").strip() or item.claim_proof_reference
    # Privacy guard (unconditional): identity_last4 keeps at most the last 4
    # characters — a longer value is refused rather than truncated/stored.
    if (
        proof_type == LostFoundClaimProofType.IDENTITY_LAST4
        and len(proof_reference) > IDENTITY_LAST4_MAX_LEN
    ):
        raise ClaimProofRequired({"reason": "identity_last4_too_long"})
    if item.category in SENSITIVE_LOST_FOUND_CATEGORIES:
        if not name:
            raise ClaimProofRequired({"reason": "recipient_name_required"})
        if not phone and not has_guest:
            raise ClaimProofRequired({"reason": "phone_or_guest_required"})
        if not proof_type:
            raise ClaimProofRequired({"reason": "proof_type_required"})
        # Covers ownership_description's "non-empty short description" rule too.
        if not proof_reference:
            raise ClaimProofRequired({"reason": "proof_reference_required"})
    elif require_contact:
        # Handover (return) contract for NORMAL categories: name is mandatory and
        # a phone-or-guest contact is mandatory — never weaker than the sensitive
        # branch's name + phone-or-guest minimum.
        if not name:
            raise ClaimantRequired()
        if not phone and not has_guest:
            raise RecipientContactRequired()
    elif not name and not has_guest:
        raise ClaimantRequired()
    return proof_type, proof_reference


def _found_item_actively_matched(item: "LostFoundItem", *, exclude_report_id=None) -> bool:
    """True iff a lost report ACTIVELY holds this found item (report
    status == ``matched``). Mirrors the partial-unique
    ``uniq_matched_found_item_active_report`` condition exactly."""
    qs = LostReport.objects.filter(
        hotel_id=item.hotel_id,
        matched_found_item=item,
        status=LostReportStatus.MATCHED,
    )
    if exclude_report_id is not None:
        qs = qs.exclude(pk=exclude_report_id)
    return qs.exists()


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
    item: LostFoundItem,
    *,
    user=None,
    claimed_by_name="",
    claimed_by_phone="",
    note="",
    claim_proof_type="",
    claim_proof_reference="",
) -> LostFoundItem:
    # Row-lock + re-read so the actively-matched guard is race-safe (a concurrent
    # confirm_match serialises against this lock). An item ACTIVELY matched by a
    # lost report may NOT be claimed out from under the atomic handover.
    item = LostFoundItem.objects.select_for_update().get(pk=item.pk)
    if _found_item_actively_matched(item):
        raise FoundItemActivelyMatched({"reason": "actively_matched"})
    if item.status not in (LostFoundStatus.FOUND, LostFoundStatus.STORED):
        raise InvalidOperationStatusTransition(
            {"from": item.status, "to": LostFoundStatus.CLAIMED}
        )
    name = (claimed_by_name or "").strip() or item.claimed_by_name
    phone = (claimed_by_phone or "").strip() or item.claimed_by_phone
    # WP7: enforce the handover requirements (stronger for sensitive categories)
    # and resolve the bounded, privacy-safe proof to store.
    proof_type, proof_reference = _resolve_claim_proof(
        item,
        claim_proof_type=claim_proof_type,
        claim_proof_reference=claim_proof_reference,
        name=name,
        phone=phone,
        has_guest=item.guest_id is not None,
    )
    previous = item.status
    item.status = LostFoundStatus.CLAIMED
    item.claimed_by_name = name
    item.claimed_by_phone = phone
    item.claim_proof_type = proof_type
    item.claim_proof_reference = proof_reference
    item.claimed_at = timezone.now()
    item.updated_by = _actor(user)
    item.save()
    # NOTE: ``note`` is the caller-supplied status note only — the proof
    # reference is NEVER written to the status log (privacy).
    _lf_log(item, previous, LostFoundStatus.CLAIMED, user, note)
    return item


@transaction.atomic
def return_lost_found_item(
    item: LostFoundItem,
    *,
    user=None,
    claimed_by_name="",
    claimed_by_phone="",
    note="",
    claim_proof_type="",
    claim_proof_reference="",
    recipient_has_guest: bool | None = None,
    _via_matched_handover: bool = False,
) -> LostFoundItem:
    # Row-lock + re-read so the actively-matched guard is race-safe. Standalone
    # returns of an item ACTIVELY matched by a lost report are refused; only the
    # atomic ``hand_over_matched_report`` path passes ``_via_matched_handover``
    # (a keyword-only, non-serializer, non-forgeable internal flag) to return the
    # very item its own matching report holds.
    item = LostFoundItem.objects.select_for_update().get(pk=item.pk)
    if not _via_matched_handover and _found_item_actively_matched(item):
        raise FoundItemActivelyMatched({"reason": "actively_matched"})
    if item.status not in ACTIVE_LF_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": item.status, "to": LostFoundStatus.RETURNED}
        )
    name = (claimed_by_name or "").strip() or item.claimed_by_name
    phone = (claimed_by_phone or "").strip() or item.claimed_by_phone
    # A returned item must record WHO received it AND a way to reach them: the
    # handover contract requires, for EVERY category, a recipient name + a phone
    # OR a linked known guest (``require_contact=True``); SENSITIVE categories
    # additionally require proof (resolved here, falling back to what the claim
    # already stored so it need not be re-entered). ``recipient_has_guest``
    # defaults to the found item's own guest link, but a caller (the atomic
    # matched-report handover) may override it so a report tied to a KNOWN guest
    # satisfies the guest condition even when the found item has no guest link.
    has_guest = (
        item.guest_id is not None
        if recipient_has_guest is None
        else recipient_has_guest
    )
    proof_type, proof_reference = _resolve_claim_proof(
        item,
        claim_proof_type=claim_proof_type,
        claim_proof_reference=claim_proof_reference,
        name=name,
        phone=phone,
        has_guest=has_guest,
        require_contact=True,
    )
    previous = item.status
    item.status = LostFoundStatus.RETURNED
    item.claimed_by_name = name
    item.claimed_by_phone = phone
    item.claim_proof_type = proof_type
    item.claim_proof_reference = proof_reference
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
    # Row-lock + re-read so the actively-matched guard is race-safe. An item
    # ACTIVELY matched by a lost report may NOT be disposed out from under the
    # atomic handover — that would dangle the report as ``matched`` to a gone
    # item. Release it first via the report's ``unmatch`` (documented reason).
    item = LostFoundItem.objects.select_for_update().get(pk=item.pk)
    if _found_item_actively_matched(item):
        raise FoundItemActivelyMatched({"reason": "actively_matched"})
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


# --- Lost report (LR — the "I lost X" cycle + safe manual matching) ----------
#
# A SEPARATE lifecycle from the FOUND item. A lost report is never auto-linked;
# the ONLY link is the explicit, row-locked ``confirm_match``. A match NEVER
# mutates the found item (its own found→…→returned lifecycle is untouched); only
# a handover returns it — atomically, both-or-neither — through the EXISTING WP7
# ``return_lost_found_item`` path so the sensitive-proof controls are reused.
#
# The status/note logs (``_lr_log``) NEVER carry the reporter phone or any proof
# value (privacy — same discipline as the found-item logs).


def _lr_log(report, previous, new, user, note=""):
    LostReportStatusLog.objects.create(
        hotel=report.hotel,
        report=report,
        previous_status=previous or "",
        new_status=new,
        note=(note or "")[:255],
        changed_by=_actor(user),
    )


def _found_item_is_matchable(item: LostFoundItem) -> bool:
    """Matchable = still holdable (owner rule): NOT returned / disposed / closed."""
    return item.status not in NON_MATCHABLE_FOUND_STATUSES


@transaction.atomic
def create_lost_report(
    hotel,
    *,
    user=None,
    category=LostFoundCategory.OTHER,
    description="",
    distinctive_marks="",
    last_seen_location="",
    lost_at=None,
    reporter_name="",
    reporter_phone="",
    guest=None,
    stay=None,
    reservation=None,
    internal_notes="",
) -> LostReport:
    """File a guest/customer LOST report (nothing is physically held).

    ``report_number`` is minted from the row-locked per-hotel ``lost_report``
    sequence. A reporter name is required (reuses the neutral 422
    :class:`ClaimantRequired`); all links are same-hotel checked.
    """
    _check_same_hotel(hotel, field="guest", obj=guest)
    _check_same_hotel(hotel, field="stay", obj=stay)
    _check_same_hotel(hotel, field="reservation", obj=reservation)
    if not (reporter_name or "").strip():
        # A lost report must name WHO reported it (the reporter) — reuse the
        # existing neutral 422 rather than minting a near-duplicate code.
        raise ClaimantRequired()
    actor = _actor(user)
    report = LostReport.objects.create(
        hotel=hotel,
        report_number=next_number(hotel, "lost_report"),
        category=category,
        description=description or "",
        distinctive_marks=distinctive_marks or "",
        last_seen_location=last_seen_location or "",
        lost_at=lost_at,
        reporter_name=reporter_name.strip(),
        reporter_phone=reporter_phone or "",
        guest=guest,
        stay=stay,
        reservation=reservation,
        reported_by_user=actor,
        status=LostReportStatus.OPEN,
        internal_notes=internal_notes or "",
        created_by=actor,
        updated_by=actor,
    )
    _lr_log(report, "", report.status, user)
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="lost_report.created",
        category="operation",
        severity="info",
        title=f"Lost report {report.report_number} filed",
        # Neutral message — no phone, no proof.
        message=f"{report.reporter_name} · {report.get_category_display()}",
        actor=user,
        related_object=report,
        related_url="/hotel/operations",
    )
    return report


@transaction.atomic
def update_lost_report(report: LostReport, *, user=None, refs=None, **meta) -> LostReport:
    """Edit report metadata/links while it is still OPEN or SEARCHING.

    A matched report must be unmatched first; terminal reports are frozen. Link
    edits are same-hotel checked."""
    if report.status not in ACTIVE_LR_STATUSES:
        raise OperationNotEditable({"status": report.status})
    refs = refs or {}
    for field in ("guest", "stay", "reservation"):
        if field in refs:
            _check_same_hotel(report.hotel, field=field, obj=refs[field])
            setattr(report, field, refs[field])
    for field in (
        "category",
        "description",
        "distinctive_marks",
        "last_seen_location",
        "lost_at",
        "reporter_name",
        "reporter_phone",
        "internal_notes",
    ):
        if field in meta:
            setattr(report, field, meta[field])
    report.updated_by = _actor(user)
    report.save()
    return report


@transaction.atomic
def change_lost_report_status(
    report: LostReport, *, new_status, user=None, note=""
) -> LostReport:
    """Generic move — only open→searching; every other move has its own action.

    Row-locked so the transition read-check is consistent under contention."""
    report = LostReport.objects.select_for_update().get(pk=report.pk)
    if new_status not in LR_STATUS_TRANSITIONS.get(report.status, set()):
        raise InvalidOperationStatusTransition(
            {"from": report.status, "to": new_status}
        )
    previous = report.status
    report.status = new_status
    report.updated_by = _actor(user)
    report.save()
    _lr_log(report, previous, new_status, user, note)
    return report


@transaction.atomic
def confirm_match(lost_report: LostReport, found_item: LostFoundItem, *, user=None) -> LostReport:
    """Link an OPEN/SEARCHING lost report to a MATCHABLE found item.

    Both rows are row-locked in a consistent order (the REPORT row first, then
    the found-item row) so two reports racing for the same item — or a match
    racing a concurrent return/dispose of the item — serialise without deadlock.

    Guarantees:
    * SAME hotel (else :class:`CrossTenantReference`).
    * the found item is MATCHABLE — NOT returned/disposed/closed (else
      :class:`FoundItemNotMatchable`).
    * the report is OPEN or SEARCHING (else :class:`InvalidOperationStatusTransition`).
    * the found item is not already actively matched by ANOTHER report — an
      application belt (:class:`FoundItemAlreadyMatched`) PLUS the DB partial-
      unique translated from the IntegrityError inside a savepoint.
    * the FOUND ITEM IS UNTOUCHED — no status change, no merge, no delete.
    """
    # Consistent lock order: report first, then the found item (prevents the
    # two-reports-one-item and match-vs-return races from deadlocking).
    report = LostReport.objects.select_for_update().get(pk=lost_report.pk)
    item = LostFoundItem.objects.select_for_update().get(pk=found_item.pk)
    if item.hotel_id != report.hotel_id:
        raise CrossTenantReference({"field": "found_item"})
    if report.status not in ACTIVE_LR_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": report.status, "to": LostReportStatus.MATCHED}
        )
    if not _found_item_is_matchable(item):
        raise FoundItemNotMatchable({"status": item.status})
    # Application belt: refuse an item another MATCHED report already holds.
    if (
        LostReport.objects.filter(
            hotel=report.hotel,
            matched_found_item=item,
            status=LostReportStatus.MATCHED,
        )
        .exclude(pk=report.pk)
        .exists()
    ):
        raise FoundItemAlreadyMatched({"item": item.id})
    previous = report.status
    report.matched_found_item = item
    report.status = LostReportStatus.MATCHED
    report.matched_by = _actor(user)
    report.matched_at = timezone.now()
    report.updated_by = _actor(user)
    # DB-backed backstop: the partial-unique ``uniq_matched_found_item_active_report``
    # is the last line of defence if a concurrent match slips past the row lock +
    # belt above. The save runs inside a savepoint so a violation rolls back only
    # this UPDATE (not the surrounding transaction) and surfaces as a clean 409.
    try:
        with transaction.atomic():
            report.save()
    except IntegrityError:
        raise FoundItemAlreadyMatched({"item": item.id})
    _lr_log(report, previous, report.status, user, f"matched:{item.item_number}")
    from apps.notifications.services import record_activity

    record_activity(
        report.hotel,
        event_type="lost_report.matched",
        category="operation",
        severity="info",
        title=f"Lost report {report.report_number} matched",
        message=f"→ found item {item.item_number}",
        actor=user,
        related_object=report,
        related_url="/hotel/operations",
    )
    return report


@transaction.atomic
def unmatch(lost_report: LostReport, *, reason, user=None) -> LostReport:
    """Break a MATCHED report's link, returning it to SEARCHING (mandatory
    reason). Allowed ONLY from ``matched``. The found item is UNTOUCHED — only
    the report's link/matched stamps are cleared."""
    if not (reason or "").strip():
        raise LostReportReasonRequired({"reason": "unmatch"})
    report = LostReport.objects.select_for_update().get(pk=lost_report.pk)
    if report.status != LostReportStatus.MATCHED:
        raise InvalidOperationStatusTransition(
            {"from": report.status, "to": LostReportStatus.SEARCHING}
        )
    previous = report.status
    report.matched_found_item = None
    report.matched_by = None
    report.matched_at = None
    report.status = LostReportStatus.SEARCHING
    report.updated_by = _actor(user)
    report.save()
    _lr_log(report, previous, report.status, user, reason.strip())
    return report


@transaction.atomic
def hand_over_matched_report(
    lost_report: LostReport,
    *,
    user=None,
    recipient_name="",
    recipient_phone="",
    note="",
    claim_proof_type="",
    claim_proof_reference="",
) -> LostReport:
    """Hand the matched found item over to the reporter — ATOMIC both-or-neither.

    The report + its matched found item are row-locked (report first, then the
    item). The EXISTING :func:`return_lost_found_item` applies the unified
    handover contract — for EVERY category a recipient name + a phone OR a linked
    known guest, and for SENSITIVE categories additionally a proof type +
    reference. ``recipient_phone`` is passed as the phone and the report's guest
    (or the item's) as the linked-guest signal, so a report tied to a KNOWN guest
    satisfies the "phone-or-guest" requirement even with no phone and no guest on
    the found item. It flips the found item to ``returned``; THEN the report
    flips to ``returned``. If EITHER step fails (missing recipient contact,
    missing proof for a sensitive item, or the item was concurrently
    returned/disposed) the WHOLE transaction rolls back — nothing changes."""
    report = LostReport.objects.select_for_update().get(pk=lost_report.pk)
    if report.status != LostReportStatus.MATCHED:
        raise InvalidOperationStatusTransition(
            {"from": report.status, "to": LostReportStatus.RETURNED}
        )
    if report.matched_found_item_id is None:
        raise InvalidOperationStatusTransition({"reason": "no_matched_item"})
    item = LostFoundItem.objects.select_for_update().get(
        pk=report.matched_found_item_id
    )
    if item.hotel_id != report.hotel_id:
        raise CrossTenantReference({"field": "found_item"})
    # Both-or-neither: return the found item through the EXISTING WP7 path. Its
    # own @transaction.atomic opens a NESTED savepoint; any failure (proof
    # controls / not-active item) rolls the savepoint back AND propagates so the
    # outer transaction here rolls back too — the report is never left returned
    # with an un-returned item, or vice-versa.
    returned_item = return_lost_found_item(
        item,
        user=user,
        claimed_by_name=recipient_name,
        claimed_by_phone=recipient_phone,
        note=note,
        claim_proof_type=claim_proof_type,
        claim_proof_reference=claim_proof_reference,
        # The handover contract requires a phone OR a linked known guest. An LR
        # report tied to a KNOWN guest (the reporter) satisfies the guest
        # condition even when the found item itself has no guest link, so thread
        # the report's OR the item's guest link as the effective "has guest".
        recipient_has_guest=(
            report.guest_id is not None or item.guest_id is not None
        ),
        # Legitimate atomic handover of the very item THIS report matches — the
        # actively-matched guard would otherwise (correctly) block a standalone
        # return, so bypass it here only via this non-forgeable internal flag.
        _via_matched_handover=True,
    )
    previous = report.status
    report.status = LostReportStatus.RETURNED
    report.returned_at = timezone.now()
    report.updated_by = _actor(user)
    report.save()
    # Make the report's audit trail self-sufficient: record the NON-SENSITIVE
    # recipient name (never phone/proof) alongside the caller note. The recipient
    # is resolved exactly as the found item did — a blank name falls back to the
    # item's stored claimant — so the report log stands on its own.
    recipient = (recipient_name or "").strip() or returned_item.claimed_by_name
    handover_note = (note or "").strip()
    log_note = f"→ {recipient}" + (f" · {handover_note}" if handover_note else "")
    _lr_log(report, previous, report.status, user, log_note)
    from apps.notifications.services import record_activity

    record_activity(
        report.hotel,
        event_type="lost_report.returned",
        category="operation",
        severity="success",
        title=f"Lost report {report.report_number} handed over",
        message=f"→ {report.reporter_name}",
        actor=user,
        related_object=report,
        related_url="/hotel/operations",
    )
    return report


@transaction.atomic
def close_unfound(lost_report: LostReport, *, reason, user=None) -> LostReport:
    """Close an OPEN/SEARCHING report as NOT FOUND (mandatory reason)."""
    if not (reason or "").strip():
        raise LostReportReasonRequired({"reason": "close_unfound"})
    report = LostReport.objects.select_for_update().get(pk=lost_report.pk)
    if report.status not in ACTIVE_LR_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": report.status, "to": LostReportStatus.CLOSED_UNFOUND}
        )
    previous = report.status
    report.status = LostReportStatus.CLOSED_UNFOUND
    report.unfound_reason = reason.strip()
    report.closed_at = timezone.now()
    report.updated_by = _actor(user)
    report.save()
    _lr_log(report, previous, report.status, user, reason.strip())
    from apps.notifications.services import record_activity

    record_activity(
        report.hotel,
        event_type="lost_report.closed_unfound",
        category="operation",
        severity="info",
        title=f"Lost report {report.report_number} closed (not found)",
        message=reason.strip(),
        actor=user,
        related_object=report,
        related_url="/hotel/operations",
    )
    return report


@transaction.atomic
def cancel_lost_report(lost_report: LostReport, *, reason, user=None) -> LostReport:
    """Cancel an OPEN/SEARCHING report (mandatory reason — reuses the existing
    neutral :class:`CancellationReasonRequired`)."""
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    report = LostReport.objects.select_for_update().get(pk=lost_report.pk)
    if report.status not in ACTIVE_LR_STATUSES:
        raise InvalidOperationStatusTransition(
            {"from": report.status, "to": LostReportStatus.CANCELLED}
        )
    previous = report.status
    report.status = LostReportStatus.CANCELLED
    report.cancellation_reason = reason.strip()
    report.cancelled_at = timezone.now()
    report.updated_by = _actor(user)
    report.save()
    _lr_log(report, previous, report.status, user, reason.strip())
    from apps.notifications.services import record_activity

    record_activity(
        report.hotel,
        event_type="lost_report.cancelled",
        category="operation",
        severity="warning",
        title=f"Lost report {report.report_number} cancelled",
        message=reason.strip(),
        actor=user,
        related_object=report,
        related_url="/hotel/operations",
    )
    return report
