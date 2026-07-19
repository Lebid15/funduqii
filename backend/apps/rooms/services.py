"""Services for rooms (Phase 5).

Room status changes go through one controlled path so every change is validated
(note required for certain statuses) and recorded in ``RoomStatusLog`` — the
lightweight per-room status history (not a general audit log).
"""
from __future__ import annotations

import enum

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.exceptions import (
    BulkRequestTooLarge,
    CrossTenantReference,
    DuplicateRoomNumber,
    ResourceInUse,
    RoomNotReleasable,
    StatusNoteRequired,
)

from .models import (
    NOTE_REQUIRED_STATUSES,
    Floor,
    Room,
    RoomStatus,
    RoomStatusLog,
    RoomType,
)

#: Hard cap on rooms created in a single bulk request (all-or-nothing batch).
MAX_BULK_ROOMS = 100

#: Room statuses that a release cycle must never silently override to
#: ``available``. ``archived`` is never releasable by ANY cycle; a
#: ``maintenance`` / ``out_of_service`` block is cleared ONLY by the authorized
#: maintenance-close cycle.
HARD_BLOCKED_ROOM_STATUSES = (
    RoomStatus.MAINTENANCE,
    RoomStatus.OUT_OF_SERVICE,
    RoomStatus.ARCHIVED,
)


class RoomReleaseCycle(enum.Enum):
    """Internal, NON-FORGEABLE marker naming which authorized operational cycle
    is releasing a room to ``available``.

    It is a Python ``Enum`` member — never a serializer field, never read from
    ``request.data``, and impossible to construct from a JSON body. A client can
    at most send a string; :func:`change_room_status` only trusts an actual
    ``RoomReleaseCycle`` instance, so the direct ``POST /rooms/{id}/status`` path
    (and every external caller) can never set ``available``.

    * ``HOUSEKEEPING_RELEASE`` — cleaning completion / inspection approval. Never
      overrides a hard block (maintenance/out-of-service/archived).
    * ``MAINTENANCE_CLOSE`` — closing a maintenance request that chose to release
      the room. The ONLY cycle allowed to clear a maintenance/out-of-service
      block (archived stays non-releasable even here).
    """

    HOUSEKEEPING_RELEASE = "housekeeping_release"
    MAINTENANCE_CLOSE = "maintenance_close"


def _release_refusal_reason(current_status: str) -> str:
    """Neutral, non-leaking ``details.reason`` for a direct/external release
    refusal — derived ONLY from what the rooms app can see (never operational
    internals like open requests or active tasks)."""
    if current_status in HARD_BLOCKED_ROOM_STATUSES:
        return "maintenance_block"
    if current_status == RoomStatus.DIRTY:
        return "room_dirty"
    return "operational_block"


@transaction.atomic
def change_room_status(
    room: Room,
    new_status: str,
    *,
    note: str,
    user,
    notify: bool = True,
    cycle_source: "RoomReleaseCycle | None" = None,
) -> Room:
    """Move a room to ``new_status``, validating and logging the change.

    ``notify`` defaults to ``True`` (existing single-room callers unchanged).
    When ``False`` the RoomStatusLog is still written, the status is still set
    and the note requirement is still validated — only the notification
    fan-out is muted (used by bulk create for maintenance/out_of_service rows).

    ``cycle_source`` is the WP1 fail-closed release guard. A room may transition
    INTO ``available`` ONLY when an authorized internal :class:`RoomReleaseCycle`
    member is supplied. It is keyword-only, defaults to ``None`` and is NEVER
    exposed by any serializer or read from request data — so the direct
    ``POST /rooms/{id}/status`` path and every external caller (which never pass
    it) can never release a room. Even a valid cycle cannot clear a hard block
    except the maintenance-close cycle for a maintenance/out-of-service room.
    Non-``available`` transitions are unaffected."""
    if new_status in NOTE_REQUIRED_STATUSES and not (note or "").strip():
        raise StatusNoteRequired({"status": new_status})

    previous = room.status
    if previous == new_status and (note or "") == room.status_note:
        return room

    # WP1 central release guard: only an authorized internal cycle may move a
    # room from a non-available state INTO ``available`` (a no-op available →
    # available is not a "becoming available" and is left alone).
    if new_status == RoomStatus.AVAILABLE and previous != RoomStatus.AVAILABLE:
        if not isinstance(cycle_source, RoomReleaseCycle):
            # Direct / external / any client path — refuse. The reason is mapped
            # from only what rooms can see, without leaking ops internals.
            raise RoomNotReleasable({"reason": _release_refusal_reason(previous)})
        # Archived is never releasable; a maintenance/out-of-service block is
        # cleared ONLY by the maintenance-close cycle.
        if previous == RoomStatus.ARCHIVED or (
            previous in (RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE)
            and cycle_source is not RoomReleaseCycle.MAINTENANCE_CLOSE
        ):
            raise RoomNotReleasable({"reason": "maintenance_block"})

    actor = user if getattr(user, "is_authenticated", False) else None
    RoomStatusLog.objects.create(
        hotel=room.hotel,
        room=room,
        previous_status=previous,
        new_status=new_status,
        note=note or "",
        changed_by=actor,
    )
    room.status = new_status
    room.status_note = note or ""
    room.status_changed_at = timezone.now()
    room.status_changed_by = actor
    room.save(
        update_fields=[
            "status",
            "status_note",
            "status_changed_at",
            "status_changed_by",
            "updated_at",
        ]
    )
    # Housekeeping final closure: every real status move shows up in the
    # activity feed (lazy import keeps app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        room.hotel,
        event_type="room.status_changed",
        category="room",
        severity="info",
        title=f"Room {room.number}: {previous} → {new_status}",
        message=note or "",
        actor=actor,
        related_object=room,
        related_url="/hotel/rooms",
        # Noise control (notifications closure): only blocking moves
        # (maintenance / out-of-service) notify; routine housekeeping moves
        # (available/dirty/cleaning/ready) stay activity-only. ``notify=False``
        # (bulk create) mutes the fan-out entirely while still logging.
        notify=notify and (new_status in NOTE_REQUIRED_STATUSES),
    )
    return room


def ensure_deletable_floor(floor) -> None:
    if floor.rooms.exists():
        raise ResourceInUse({"reason": "floor_has_rooms"})


def ensure_deletable_room_type(room_type) -> None:
    if room_type.rooms.exists():
        raise ResourceInUse({"reason": "room_type_has_rooms"})
    # A room type is also referenced by reservation lines (PROTECT); those must
    # block deletion too or the raw ProtectedError would escalate to a 500.
    if room_type.reservation_lines.exists():
        raise ResourceInUse({"reason": "room_type_has_reservations"})


def ensure_deletable_room(room) -> None:
    """Rooms are referenced by stays and reservation lines (both PROTECT).
    Deleting a room that has either is refused with a 409 instead of letting a
    raw ProtectedError escalate to a 500."""
    if room.stays.exists():
        raise ResourceInUse({"reason": "room_has_stays"})
    if room.reservation_lines.exists():
        raise ResourceInUse({"reason": "room_has_reservations"})


# --- Central room create (shared by single + bulk) --------------------------


def _is_room_number_conflict(exc: IntegrityError) -> bool:
    """True ONLY when ``exc`` is the ``unique_room_number_per_hotel`` violation.

    Narrow, backend-agnostic detection so ONLY a duplicate room number is
    relabelled ``DuplicateRoomNumber`` — any OTHER integrity error (e.g. a
    foreign-key violation) is left to propagate unchanged. Postgres names the
    constraint in the message; SQLite (dev) reports the offending columns
    instead, so both forms are matched."""
    parts = [str(exc)]
    if exc.__cause__ is not None:
        parts.append(str(exc.__cause__))
    blob = " ".join(parts).lower()
    if "unique_room_number_per_hotel" in blob:
        return True
    return "unique constraint failed" in blob and "rooms.number" in blob


def _create_one_room(
    hotel,
    *,
    number: str,
    display_name: str,
    floor_id: int,
    room_type_id: int,
    is_active: bool,
    initial_status: str,
    status_note: str,
    user,
    notify: bool,
) -> Room:
    """Create ONE room and apply its initial operational status.

    The single ``create_room`` path and every bulk row funnel through here so
    both write the Room and — when ``initial_status`` is not ``available`` — a
    ``RoomStatusLog`` via the SAME controlled ``change_room_status`` path.

    MUST run inside a ``transaction.atomic`` opened by the caller (so the quota
    check and the whole batch stay all-or-nothing). A concurrent duplicate
    number (unique_room_number_per_hotel) surfaces as a clean 400
    ``DuplicateRoomNumber`` instead of a raw ``IntegrityError`` 500; the
    exception propagates so the surrounding atomic block rolls back."""
    try:
        room = Room.objects.create(
            hotel=hotel,
            floor_id=floor_id,
            room_type_id=room_type_id,
            number=number,
            display_name=display_name or "",
            is_active=is_active,
        )
    except IntegrityError as exc:
        # Only a duplicate room number is a clean 400; re-raise anything else
        # (the atomic block still rolls back either way).
        if _is_room_number_conflict(exc):
            raise DuplicateRoomNumber(
                {"source": "existing", "numbers": [number]}
            ) from exc
        raise
    if initial_status and initial_status != RoomStatus.AVAILABLE:
        change_room_status(
            room, initial_status, note=status_note or "", user=user, notify=notify
        )
    return room


def create_room(
    hotel,
    *,
    number: str,
    display_name: str = "",
    floor,
    room_type,
    is_active: bool = True,
    initial_status: str = RoomStatus.AVAILABLE,
    status_note: str = "",
    user,
    notify: bool = True,
) -> Room:
    """Create a SINGLE room through the same central path as bulk create.

    Opens ONE ``transaction.atomic`` so the plan quota check, the room creation
    and the initial-status move (``RoomStatusLog``) are atomic together.
    ``floor``/``room_type`` are the validated model instances from
    ``RoomWriteSerializer`` (tenancy, duplicate-number and note validation ran
    there). A single create is NOT batch noise, so its initial-status move
    notifies normally (``notify`` defaults to ``True``) — unlike bulk, which
    mutes the fan-out."""
    from apps.subscriptions.entitlements import check_room_quota

    floor_id = getattr(floor, "id", floor)
    room_type_id = getattr(room_type, "id", room_type)
    with transaction.atomic():
        check_room_quota(hotel, count=1)
        return _create_one_room(
            hotel,
            number=str(number).strip(),
            display_name=display_name,
            floor_id=floor_id,
            room_type_id=room_type_id,
            is_active=is_active,
            initial_status=initial_status,
            status_note=status_note,
            user=user,
            notify=notify,
        )


# --- Bulk room create -------------------------------------------------------


def bulk_create_rooms(hotel, rows: list[dict], user) -> list[Room]:
    """Create N rooms for ``hotel`` as ONE all-or-nothing batch.

    ``rows`` are the already structurally-validated dicts from
    ``RoomBulkCreateSerializer`` (number/floor/room_type/... per row). ALL
    business validation runs BEFORE any write; the quota check, the room
    creations and the per-row initial-status moves all happen inside a single
    ``transaction.atomic`` — any failure rolls the whole batch back so zero
    rooms are created.

    Rooms whose ``initial_status`` is maintenance/out_of_service still write a
    RoomStatusLog but MUTE the notification fan-out (``notify=False``)."""
    from apps.subscriptions.entitlements import check_room_quota

    # Defensive size bounds (the serializer is the primary gate).
    if len(rows) > MAX_BULK_ROOMS:
        raise BulkRequestTooLarge({"limit": MAX_BULK_ROOMS, "requested": len(rows)})
    if len(rows) < 1:
        raise ValidationError({"rooms": "Provide at least one room."})

    numbers = [str(r["number"]).strip() for r in rows]

    # (2) Every number must be non-empty after trimming.
    empty_indices = [i for i, n in enumerate(numbers) if not n]
    if empty_indices:
        raise ValidationError(
            {
                "rooms": "Each room requires a non-empty number.",
                "indices": empty_indices,
            }
        )

    # (3) No duplicate numbers WITHIN the request.
    seen: set[str] = set()
    duplicate_numbers: list[str] = []
    for n in numbers:
        if n in seen and n not in duplicate_numbers:
            duplicate_numbers.append(n)
        seen.add(n)
    if duplicate_numbers:
        raise DuplicateRoomNumber(
            {"source": "request", "numbers": duplicate_numbers}
        )

    # (4) No collision with numbers already used in this hotel.
    existing = set(
        Room.objects.filter(hotel=hotel, number__in=numbers).values_list(
            "number", flat=True
        )
    )
    if existing:
        raise DuplicateRoomNumber(
            {"source": "existing", "numbers": sorted(existing)}
        )

    # (5) floor + room_type must EXIST and belong to this hotel (else
    # cross-tenant). One batch query each; ids not in the hotel's sets fail.
    floor_ids = set(
        Floor.objects.filter(hotel=hotel).values_list("id", flat=True)
    )
    type_ids = set(
        RoomType.objects.filter(hotel=hotel).values_list("id", flat=True)
    )
    for i, r in enumerate(rows):
        if r["floor"] not in floor_ids:
            raise CrossTenantReference({"field": "floor", "index": i})
        if r["room_type"] not in type_ids:
            raise CrossTenantReference({"field": "room_type", "index": i})

    # (6) initial_status must be a valid non-archived status; note-required
    # statuses need a non-empty note.
    for i, r in enumerate(rows):
        st = r.get("initial_status", RoomStatus.AVAILABLE)
        if st == RoomStatus.ARCHIVED:
            raise ValidationError(
                {"rooms": "Rooms cannot be created as archived.", "index": i}
            )
        if st in NOTE_REQUIRED_STATUSES and not (r.get("status_note") or "").strip():
            raise StatusNoteRequired({"status": st, "index": i})

    # One transaction: full-count quota -> create each row + apply its initial
    # status through the SHARED central helper (bulk mutes the notification
    # fan-out with notify=False while still writing the RoomStatusLog).
    with transaction.atomic():
        check_room_quota(hotel, count=len(rows))
        created: list[Room] = []
        for r, number in zip(rows, numbers):
            created.append(
                _create_one_room(
                    hotel,
                    number=number,
                    display_name=r.get("display_name", "") or "",
                    floor_id=r["floor"],
                    room_type_id=r["room_type"],
                    is_active=r.get("is_active", True),
                    initial_status=r.get("initial_status", RoomStatus.AVAILABLE),
                    status_note=r.get("status_note", "") or "",
                    user=user,
                    notify=False,
                )
            )
    return created


# --- Operational board (owner task) -----------------------------------------
# READ-ONLY aggregation for /hotel/rooms: every room with a COMPUTED display
# status, its current in-house stay and next upcoming reservation, plus hotel
# and per-floor summaries. `occupied` / `reserved` stay derived — they are
# never stored on the room (Phase 5 rule).

# Display priority (owner spec): the manual states win, then occupancy, then
# upcoming reservations, else available.
_ATTENTION_STATUSES = ("dirty", "cleaning", "maintenance", "out_of_service")


def _display_status(room, occupied_ids, reserved_ids) -> str:
    if room.status != "available":
        return room.status
    if room.id in occupied_ids:
        return "occupied"
    if room.id in reserved_ids:
        return "reserved"
    return "available"


def _hotel_currency(hotel) -> str:
    """The hotel's default currency (from HotelSettings) or USD.

    Mirrors ``finance.services._hotel_currency`` locally (no cross-app import).
    ``hotel.settings`` is the OneToOne HotelSettings row (may be absent). At most
    one extra query; no N+1 (called once per board build).
    """
    settings_obj = getattr(hotel, "settings", None)
    if settings_obj and getattr(settings_obj, "default_currency", ""):
        return settings_obj.default_currency
    return "USD"


def operational_board(hotel) -> dict:
    """Build the full rooms operational-board DTO for one hotel (pure read)."""
    from apps.reservations.models import BLOCKING_STATUSES, ReservationRoomLine
    from apps.shifts.services import get_business_date
    from apps.stays.models import Stay, StayStatus

    today = get_business_date(hotel)

    rooms = list(
        Room.objects.filter(hotel=hotel).select_related("floor", "room_type")
    )

    # Current in-house stay per room (a room holds at most one).
    stays = Stay.objects.filter(
        hotel=hotel, status=StayStatus.IN_HOUSE
    ).select_related("primary_guest", "reservation")
    stay_by_room: dict[int, Stay] = {s.room_id: s for s in stays}

    # Upcoming/active blocking reservations per room, earliest first.
    lines = (
        ReservationRoomLine.objects.filter(
            hotel=hotel,
            room__isnull=False,
            reservation__status__in=BLOCKING_STATUSES,
            reservation__check_out_date__gte=today,
        )
        .select_related("reservation")
        .order_by("reservation__check_in_date", "reservation_id")
    )
    lines_by_room: dict[int, list] = {}
    for line in lines:
        lines_by_room.setdefault(line.room_id, []).append(line)

    occupied_ids = set(stay_by_room)
    # A room is RESERVED only when a blocking reservation COVERS the business
    # date: check_in <= business_date < check_out. This mirrors the availability
    # engine's half-open interval [check_in, check_out) — a purely FUTURE
    # booking (check_in > business_date) does not reserve the room today, and the
    # checkout day itself frees it. `lines_by_room` still holds every upcoming
    # line, so `next_reservation` keeps surfacing future bookings unchanged.
    reserved_ids = {
        room_id
        for room_id, room_lines in lines_by_room.items()
        if any(
            ln.reservation.check_in_date <= today < ln.reservation.check_out_date
            for ln in room_lines
        )
    }

    def _next_reservation(room_id: int):
        stay = stay_by_room.get(room_id)
        for line in lines_by_room.get(room_id, []):
            res = line.reservation
            # Skip the reservation the current stay came from — it is not
            # an UPCOMING booking for this room.
            if stay is not None and stay.reservation_id == res.id:
                continue
            return {
                "id": res.id,
                "reservation_number": res.reservation_number,
                "guest_name": res.primary_guest_name,
                "status": res.status,
                "check_in_date": str(res.check_in_date),
                "check_out_date": str(res.check_out_date),
            }
        return None

    room_rows = []
    for room in rooms:
        stay = stay_by_room.get(room.id)
        # Two INDEPENDENT axes: `operational_status` is the stored manual state
        # (housekeeping/ops); `occupancy_status` is derived purely from real
        # stays/reservations. A room can be occupied AND dirty at once — neither
        # axis hides the other (that is the collapse bug this fixes).
        if room.id in occupied_ids:
            occupancy_status = "occupied"
        elif room.id in reserved_ids:
            occupancy_status = "reserved"
        else:
            occupancy_status = "free"
        floor_is_active = room.floor.is_active
        room_type_is_active = room.room_type.is_active
        # Bookable RIGHT NOW: every gate open on both axes (no extra queries —
        # floor/room_type are select_related, sets are already built).
        available_now = (
            room.is_active
            and floor_is_active
            and room_type_is_active
            and room.status == "available"
            and occupancy_status == "free"
        )
        room_rows.append(
            {
                "id": room.id,
                "number": room.number,
                "display_name": room.display_name,
                "floor": room.floor_id,
                "floor_name": room.floor.name,
                "floor_is_active": floor_is_active,
                "room_type": room.room_type_id,
                "room_type_name": room.room_type.name,
                "room_type_code": room.room_type.code,
                "room_type_is_active": room_type_is_active,
                # §6.1: the board row now shows the room's EFFECTIVE features
                # (type defaults − exclusions + additions). The payload key
                # stays `amenities` so the frontend board contract is
                # unchanged; empty overrides mirror the type exactly.
                "amenities": room.effective_features,
                "base_capacity": room.room_type.base_capacity,
                "max_capacity": room.room_type.max_capacity,
                "base_rate": (
                    str(room.room_type.base_rate)
                    if room.room_type.base_rate is not None
                    else None
                ),
                "is_active": room.is_active,
                "operational_status": room.status,
                "occupancy_status": occupancy_status,
                "available_now": available_now,
                "display_status": _display_status(room, occupied_ids, reserved_ids),
                "status_note": room.status_note,
                "status_changed_at": (
                    room.status_changed_at.isoformat()
                    if room.status_changed_at
                    else None
                ),
                "current_stay": (
                    {
                        "id": stay.id,
                        "guest_name": stay.primary_guest.full_name,
                        "planned_check_out_date": str(stay.planned_check_out_date),
                        "reservation_id": stay.reservation_id,
                        "reservation_number": (
                            stay.reservation.reservation_number
                            if stay.reservation
                            else None
                        ),
                    }
                    if stay
                    else None
                ),
                "next_reservation": _next_reservation(room.id),
            }
        )

    def _empty_counts() -> dict:
        return {
            "total": 0,
            "available": 0,
            # Explicit alias of `available` on the occupancy/bookable axis; kept
            # alongside `available` for frontend compatibility.
            "available_now": 0,
            "occupied": 0,
            "reserved": 0,
            "dirty": 0,
            "cleaning": 0,
            "maintenance": 0,
            "out_of_service": 0,
            "attention": 0,
        }

    # Summaries count NON-archived rooms only (archived rooms still appear in
    # `rooms` so the board's "show archived" toggle works). Counting is on TWO
    # INDEPENDENT axes: occupancy (occupied/reserved/available_now) and
    # operational (dirty/cleaning/maintenance/out_of_service). The two overlap
    # deliberately — an occupied+dirty room is counted in BOTH occupied and
    # dirty, so occupancy is never masked by the manual state.
    summary = _empty_counts()
    floor_counts: dict[int, dict] = {}
    for row in room_rows:
        if row["operational_status"] == "archived":
            continue
        bucket = floor_counts.setdefault(row["floor"], _empty_counts())
        for counts in (summary, bucket):
            counts["total"] += 1
            # Occupancy axis (mutually exclusive occupied/reserved/free).
            if row["occupancy_status"] == "occupied":
                counts["occupied"] += 1
            elif row["occupancy_status"] == "reserved":
                counts["reserved"] += 1
            # Bookable-now axis (both keys carry the same value).
            if row["available_now"]:
                counts["available"] += 1
                counts["available_now"] += 1
            # Operational axis (independent; may overlap with occupancy).
            op = row["operational_status"]
            if op in _ATTENTION_STATUSES:
                counts[op] += 1
                counts["attention"] += 1

    floors = []
    for floor in Floor.objects.filter(hotel=hotel).order_by("sort_order", "id"):
        counts = floor_counts.get(floor.id, _empty_counts())
        total = counts["total"]
        floors.append(
            {
                "id": floor.id,
                "name": floor.name,
                "number": floor.number,
                "is_active": floor.is_active,
                **counts,
                "availability_rate": (
                    round(counts["available"] * 100 / total) if total else 0
                ),
            }
        )

    return {
        "currency": _hotel_currency(hotel),
        "summary": summary,
        "floors": floors,
        "rooms": room_rows,
    }
