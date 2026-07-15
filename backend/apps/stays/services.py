"""Front-desk services (Phase 7 + final closure): the ONE controlled path for
check-in, check-out and in-house stay changes. Views never mutate stays
directly — they call these services.

Rules enforced here (backend is the source of truth):
- Check-in only from a **confirmed** reservation whose arrival date has been
  reached (hotel business date), into an **available** physical room that is
  not occupied and not held by another reservation, and never beyond the
  reservation line's booked quantity.
- Occupancy is derived from an active stay — no manual `room.status = occupied`.
- After check-in the STAY is the operational source of truth: extending,
  shortening and room moves happen HERE (the reservations section freezes
  dates/rooms once a stay is in-house). Every change re-checks availability
  through the central engine and keeps the reservation in sync so inventory
  stays unified.
- Check-out settles operationally only: an OPEN folio with a non-zero balance
  blocks it (settlement lives in Finance); zero-balance folios are closed via
  the central finance service. The room becomes **dirty** on check-out
  (documented decision), via the Phase 5 controlled status service.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    AlreadyCheckedIn,
    ArrivalDateInFuture,
    CrossTenantReference,
    EarlyDepartureReasonRequired,
    FolioAwaitingFinalCharges,
    FolioBalanceOutstanding,
    InsuranceNotSettled,
    InvalidCheckIn,
    InvalidCheckOut,
    InvalidStayChange,
    ReverseCheckInReasonRequired,
    ReservationLineFull,
    RoomAssignmentConflict,
    RoomNotReady,
    RoomOccupied,
)
from apps.reservations.availability import (
    NON_BOOKABLE_ROOM_STATUSES,
    AvailabilityService,
)
from apps.reservations.models import (
    Reservation,
    ReservationRoomLine,
    ReservationStatus,
)
from apps.rooms.models import Room, RoomStatus
from apps.rooms.services import change_room_status
from apps.shifts.services import get_business_date

from .models import Stay, StayGuest, StayGuestRole, StayStatus, StayStatusLog

# A room may only be checked into when it is manually `available`. dirty/cleaning
# (and the hard-blocked maintenance/out_of_service/archived) are refused —
# housekeeping must ready the room first (documented decision; an override could
# be added behind a permission later).
CHECK_IN_READY_STATUS = RoomStatus.AVAILABLE


def _log(stay, previous, new, *, note="", user=None):
    actor = user if getattr(user, "is_authenticated", False) else None
    StayStatusLog.objects.create(
        hotel=stay.hotel,
        stay=stay,
        previous_status=previous or "",
        new_status=new,
        note=note or "",
        changed_by=actor,
    )


def _record(stay, *, event_type, severity, title, message, user=None):
    # Phase 14 activity system (lazy import to keep app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        stay.hotel,
        event_type=event_type,
        category="stay",
        severity=severity,
        title=title,
        message=message,
        actor=user,
        related_object=stay,
        related_url="/hotel/front-desk",
    )


def _require_in_house(stay) -> Stay:
    """Re-read the stay under a row lock and require it to be in-house."""
    stay = Stay.objects.select_for_update().select_related(
        "room", "room__room_type", "primary_guest", "reservation", "hotel"
    ).get(pk=stay.pk)
    if stay.status != StayStatus.IN_HOUSE:
        raise InvalidStayChange(
            {"reason": "stay_not_in_house", "status": stay.status}
        )
    return stay


def _shrink_reservation_end(reservation, *, business_date):
    """Release inventory a stay no longer needs, keeping the reservation and
    its stays unified WITHOUT harming siblings.

    The reservation's end shrinks to the latest end still needed: the planned
    check-out of every stay that is still in-house, floored at the business
    date and at a one-night minimum. If any booked room of the reservation has
    NOT been admitted yet (a pending arrival), nothing shrinks — that booking
    still needs its original window.
    """
    if reservation is None:
        return
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    total_quantity = sum(
        line.quantity for line in reservation.lines.all()
    )
    admitted = reservation.stays.exclude(status=StayStatus.CANCELLED).count()
    if admitted < total_quantity:
        return
    candidates = [business_date] + [
        s.planned_check_out_date
        for s in reservation.stays.filter(status=StayStatus.IN_HOUSE)
    ]
    new_end = max(candidates + [reservation.check_in_date + timedelta(days=1)])
    if new_end < reservation.check_out_date:
        reservation.check_out_date = new_end
        reservation.save(update_fields=["check_out_date", "updated_at"])


def _grow_reservation_end(reservation, *, new_end):
    """Extend the reservation's end so it keeps covering an extended stay."""
    if reservation is None:
        return
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if new_end > reservation.check_out_date:
        reservation.check_out_date = new_end
        reservation.save(update_fields=["check_out_date", "updated_at"])


class CheckInService:
    """Admit a confirmed reservation into a specific room, creating a Stay."""

    @staticmethod
    @transaction.atomic
    def execute(
        hotel,
        *,
        reservation,
        reservation_line=None,
        room=None,
        primary_guest,
        companions=(),
        check_in_notes="",
        user=None,
    ) -> Stay:
        if reservation.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "reservation"})
        if reservation.status != ReservationStatus.CONFIRMED:
            raise InvalidCheckIn(
                {"reason": "reservation_not_confirmed", "status": reservation.status}
            )
        # Arrival-date guard (final closure): check-in may not happen before
        # the reservation's arrival date, measured by the HOTEL's business
        # date — never the server clock. Late arrivals stay admissible for as
        # long as the reservation is valid.
        business_date = get_business_date(hotel)
        if reservation.check_in_date > business_date:
            raise ArrivalDateInFuture(
                {
                    "check_in_date": str(reservation.check_in_date),
                    "business_date": str(business_date),
                }
            )

        if reservation_line is not None:
            if reservation_line.reservation_id != reservation.id:
                raise InvalidCheckIn({"reason": "line_not_in_reservation"})
            # Quantity cap (final closure): lock the line row so concurrent
            # admissions serialize, then refuse once the line's booked
            # quantity is reached (cancelled stays don't count).
            reservation_line = ReservationRoomLine.objects.select_for_update().get(
                pk=reservation_line.pk
            )
            admitted = (
                Stay.objects.filter(hotel=hotel, reservation_line=reservation_line)
                .exclude(status=StayStatus.CANCELLED)
                .count()
            )
            if admitted >= reservation_line.quantity:
                raise ReservationLineFull(
                    {
                        "reservation_line": reservation_line.id,
                        "quantity": reservation_line.quantity,
                        "admitted": admitted,
                    }
                )
            # A line's pinned room wins; a passed room must match it.
            if reservation_line.room_id:
                if room is not None and room.id != reservation_line.room_id:
                    raise InvalidCheckIn({"reason": "room_does_not_match_line"})
                room = reservation_line.room
        else:
            # No line passed: the same cap, against the whole reservation
            # (lock the reservation row to serialize concurrent admissions).
            locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
            total_quantity = sum(line.quantity for line in locked.lines.all())
            admitted = (
                Stay.objects.filter(hotel=hotel, reservation=reservation)
                .exclude(status=StayStatus.CANCELLED)
                .count()
            )
            if total_quantity and admitted >= total_quantity:
                raise ReservationLineFull(
                    {
                        "reservation": reservation.id,
                        "quantity": total_quantity,
                        "admitted": admitted,
                    }
                )

        if room is None:
            raise InvalidCheckIn({"reason": "room_required"})

        # Lock the room row for the duration of the check-in.
        room = Room.objects.select_for_update().get(pk=room.pk)
        if room.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "room"})
        if not room.is_active or room.status != CHECK_IN_READY_STATUS:
            raise RoomNotReady({"room": room.id, "status": room.status})
        if Stay.objects.filter(
            hotel=hotel, room=room, status=StayStatus.IN_HOUSE
        ).exists():
            raise RoomOccupied({"room": room.id})
        # Not the same line+room checked in twice.
        if reservation_line is not None and Stay.objects.filter(
            hotel=hotel,
            reservation_line=reservation_line,
            room=room,
            status=StayStatus.IN_HOUSE,
        ).exists():
            raise AlreadyCheckedIn({"line": reservation_line.id, "room": room.id})
        # The room must not be specifically held by a DIFFERENT reservation.
        if AvailabilityService.room_is_assigned_in_range(
            hotel,
            room,
            reservation.check_in_date,
            reservation.check_out_date,
            exclude_reservation_id=reservation.id,
        ):
            raise RoomAssignmentConflict({"room": room.id})

        if primary_guest.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "primary_guest"})
        for companion in companions:
            if companion.hotel_id != hotel.id:
                raise CrossTenantReference({"field": "companion"})
        # Guests final closure: a guest blocked in THIS hotel is never
        # admitted — as primary or companion (lazy import, no app cycle).
        from apps.guests.services import ensure_guest_not_blocked

        ensure_guest_not_blocked(primary_guest, *companions)

        actor = user if getattr(user, "is_authenticated", False) else None
        stay = Stay.objects.create(
            hotel=hotel,
            reservation=reservation,
            reservation_line=reservation_line,
            room=room,
            primary_guest=primary_guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=reservation.check_in_date,
            planned_check_out_date=reservation.check_out_date,
            actual_check_in_at=timezone.now(),
            checked_in_by=actor,
            check_in_notes=check_in_notes or "",
        )
        StayGuest.objects.create(
            hotel=hotel, stay=stay, guest=primary_guest, role=StayGuestRole.PRIMARY
        )
        seen = {primary_guest.id}
        for companion in companions:
            if companion.id in seen:
                continue
            seen.add(companion.id)
            StayGuest.objects.create(
                hotel=hotel, stay=stay, guest=companion, role=StayGuestRole.COMPANION
            )
        # Folio closure round: every stay opens with its ONE operational folio
        # (same transaction — a failed folio rolls the whole check-in back).
        # Lazy import: finance is a later phase.
        from apps.finance.services import ensure_stay_folio, post_stay_room_charge

        ensure_stay_folio(stay, user=user)
        # STAYS-ARRIVALS-DEPARTURES §24/§31 (owner D1): post the room/night charge
        # so the folio is the COMPLETE account (skipped for an unpriced room).
        # Same transaction — a failure rolls the whole check-in back.
        post_stay_room_charge(stay, user=user)
        _log(stay, "", StayStatus.IN_HOUSE, note="checked in", user=user)
        _record(
            stay,
            event_type="stay.checked_in",
            severity="success",
            title=f"Check-in: room {room.number}",
            message=f"{primary_guest.full_name} · {reservation.reservation_number}",
            user=user,
        )
        return stay


class CheckOutService:
    """Close an in-house stay.

    Operational settlement only: an OPEN folio with a non-zero balance blocks
    the check-out (no override here — settlement happens in Finance); folios
    that balance to zero are closed through the central finance service. A
    check-out before the planned date is an EARLY departure: it requires a
    reason and shrinks the reservation's end so the freed nights go back to
    inventory. Charges are never touched.
    """

    @staticmethod
    @transaction.atomic
    def execute(stay, *, check_out_notes="", checkout_reason="", user=None) -> Stay:
        # Row lock: concurrent check-outs of the same stay serialize; the
        # loser then fails the in-house test instead of double-logging.
        stay = Stay.objects.select_for_update().select_related(
            "room", "primary_guest", "reservation", "hotel"
        ).get(pk=stay.pk)
        if stay.status != StayStatus.IN_HOUSE:
            raise InvalidCheckOut({"status": stay.status})

        business_date = get_business_date(stay.hotel)
        early = business_date < stay.planned_check_out_date
        if early and not (checkout_reason or "").strip():
            raise EarlyDepartureReasonRequired(
                {
                    "planned_check_out_date": str(stay.planned_check_out_date),
                    "business_date": str(business_date),
                }
            )

        # Folio gate (final closure). Lazy import: finance is a later phase.
        from apps.finance.models import Folio, FolioStatus
        from apps.finance.services import close_folio, folio_balance

        open_folios = list(
            Folio.objects.select_for_update().filter(
                hotel=stay.hotel, stay=stay, status=FolioStatus.OPEN
            )
        )
        for folio in open_folios:
            # §32/§38 — a folio still awaiting final charges must not close and
            # blocks departure (checked BEFORE the balance: the balance is not yet
            # final while charges are pending).
            if folio.awaiting_final_charges:
                raise FolioAwaitingFinalCharges(
                    {
                        "folio": folio.id,
                        "folio_number": folio.folio_number,
                        "reason": folio.awaiting_final_charges_note,
                    }
                )
            balance = folio_balance(folio)["balance"]
            if balance != 0:
                raise FolioBalanceOutstanding(
                    {
                        "folio": folio.id,
                        "folio_number": folio.folio_number,
                        "balance": str(balance),
                    }
                )

        # §35/§38 — refundable insurance held for this stay must be fully refunded
        # or settled (held_amount == 0) before departure. This includes insurance
        # taken at booking against the reservation (stay not yet linked).
        from django.db.models import Q

        from apps.finance.models import RefundableInsurance

        held_filter = Q(stay=stay)
        if stay.reservation_id:
            held_filter |= Q(reservation_id=stay.reservation_id, stay__isnull=True)
        for ins in RefundableInsurance.objects.filter(hotel=stay.hotel).filter(held_filter):
            if ins.held_amount > 0:
                raise InsuranceNotSettled(
                    {"insurance": ins.id, "held": str(ins.held_amount)}
                )

        actor = user if getattr(user, "is_authenticated", False) else None
        previous = stay.status
        stay.status = StayStatus.CHECKED_OUT
        stay.actual_check_out_at = timezone.now()
        stay.checked_out_by = actor
        stay.check_out_notes = check_out_notes or ""
        stay.checkout_reason = checkout_reason or ""
        stay.save(
            update_fields=[
                "status",
                "actual_check_out_at",
                "checked_out_by",
                "check_out_notes",
                "checkout_reason",
                "updated_at",
            ]
        )
        # Balance is zero on every open folio — close them centrally.
        for folio in open_folios:
            close_folio(folio, user=user)
        # Documented decision: a vacated room becomes `dirty` for housekeeping.
        if stay.room.status == RoomStatus.AVAILABLE:
            change_room_status(stay.room, RoomStatus.DIRTY, note="", user=user)
        # Phase 10: auto-raise ONE check-out cleaning task (idempotent; same
        # transaction — it has no external dependencies that could fail).
        # Imported lazily to keep app loading order simple.
        from apps.operations.services import create_checkout_cleaning_task

        create_checkout_cleaning_task(stay, user=user)
        # Early departure releases the nights the guest no longer uses.
        if early:
            _shrink_reservation_end(stay.reservation, business_date=business_date)
        note = "checked out (early departure)" if early else "checked out"
        _log(stay, previous, StayStatus.CHECKED_OUT, note=note, user=user)
        _record(
            stay,
            event_type="stay.checked_out",
            severity="info",
            title=f"Check-out: room {stay.room.number}",
            message=(
                f"{stay.primary_guest.full_name} · early departure"
                if early
                else stay.primary_guest.full_name
            ),
            user=user,
        )
        return stay


class ReverseCheckInService:
    """Reverse a MISTAKEN check-in (§30) — an organised reversal, never a delete.

    Voids the check-in's room charges (same business date), reverts the stay's
    folio to a pre-arrival reservation folio (detaches the stay, so any deposit
    survives as a pre-arrival deposit and the room frees), and soft-cancels the
    stay with a mandatory reason + audit. Historical PAYMENTS are never deleted;
    only an IN-HOUSE stay can be reversed. The reservation returns to a bookable
    state so a correct check-in can follow.
    """

    @staticmethod
    @transaction.atomic
    def execute(stay, *, reason, user=None) -> Stay:
        if not (reason or "").strip():
            raise ReverseCheckInReasonRequired()
        reason = reason.strip()
        stay = (
            Stay.objects.select_for_update()
            .select_related("room", "reservation", "hotel")
            .get(pk=stay.pk)
        )
        if stay.status != StayStatus.IN_HOUSE:
            raise InvalidStayChange({"reason": "not_in_house", "status": stay.status})

        from apps.finance.models import (
            ChargeType,
            Folio,
            FolioStatus,
            PostingStatus,
        )
        from apps.finance.services import (
            ROOM_CHARGE_SOURCE,
            ROOM_EXTENSION_SOURCE,
            void_charge,
        )

        open_folios = list(
            Folio.objects.select_for_update().filter(
                hotel=stay.hotel, stay=stay, status=FolioStatus.OPEN
            )
        )
        for folio in open_folios:
            # Void the check-in's room charges (reverses the financial effect).
            # Payments/deposits are NEVER deleted — no silent loss of history.
            for charge in folio.charges.filter(
                type=ChargeType.ROOM,
                source__in=[ROOM_CHARGE_SOURCE, ROOM_EXTENSION_SOURCE],
                status=PostingStatus.POSTED,
            ):
                void_charge(charge, reason=f"check-in reversed · {reason}", user=user)
            # Detach the folio from the stay: it reverts to the reservation's ONE
            # pre-arrival folio (reservation set, stay NULL), so any deposit lives
            # on as a pre-arrival deposit and a future re-check-in reuses it (never
            # a second ledger). A folio with no reservation link stays attached to
            # the cancelled stay as read-only history.
            if folio.reservation_id is not None:
                folio.stay = None
                folio.save(update_fields=["stay", "updated_at"])

        previous = stay.status
        stay.status = StayStatus.CANCELLED
        stay.checkout_reason = reason
        stay.save(update_fields=["status", "checkout_reason", "updated_at"])
        # The room frees automatically (occupancy is derived from in-house stays).
        _log(
            stay,
            previous,
            StayStatus.CANCELLED,
            note=f"check-in reversed · {reason}",
            user=user,
        )
        _record(
            stay,
            event_type="stay.check_in_reversed",
            severity="warning",
            title=f"Check-in reversed: room {stay.room.number}",
            message=f"{stay.primary_guest.full_name} · {reason}",
            user=user,
        )
        return stay


class ExtendStayService:
    """Extend an in-house stay — from the STAY, the operational truth.

    Availability for the ADDED window is re-checked through the central
    engine (excluding the stay's own reservation so it never conflicts with
    itself); the reservation's end grows with the stay so inventory stays
    unified. The arrival date never changes; the ADDED nights are posted to the
    folio as a room charge (§25 / owner decision D1), skipped for an unpriced room.
    """

    @staticmethod
    @transaction.atomic
    def execute(stay, *, new_check_out_date, reason="", user=None) -> Stay:
        stay = _require_in_house(stay)
        old_end = stay.planned_check_out_date
        if new_check_out_date <= old_end:
            raise InvalidStayChange(
                {
                    "reason": "new_date_not_after_current",
                    "current_check_out": str(old_end),
                }
            )
        room = Room.objects.select_for_update().get(pk=stay.room_id)
        if not room.is_active or room.status in NON_BOOKABLE_ROOM_STATUSES:
            raise RoomNotReady({"room": room.id, "status": room.status})
        # Central engine: next reservations on this room, other stays, type
        # capacity, maintenance/out-of-service/archived — all in one check.
        AvailabilityService.ensure_can_book(
            stay.hotel,
            [
                {
                    "room_type_id": room.room_type_id,
                    "quantity": 1,
                    "room_id": room.id,
                }
            ],
            old_end,
            new_check_out_date,
            exclude_reservation_id=stay.reservation_id,
        )
        stay.planned_check_out_date = new_check_out_date
        stay.save(update_fields=["planned_check_out_date", "updated_at"])
        _grow_reservation_end(stay.reservation, new_end=new_check_out_date)
        # §25 (owner D1): the ADDED nights are a real folio charge so the account
        # (and the check-out balance gate) stays correct. Same transaction.
        from apps.finance.services import post_stay_extension_charge

        post_stay_extension_charge(
            stay, added_nights=(new_check_out_date - old_end).days, user=user
        )
        note = f"extended {old_end} -> {new_check_out_date}"
        if (reason or "").strip():
            note = f"{note} · {reason.strip()}"
        _log(stay, StayStatus.IN_HOUSE, StayStatus.IN_HOUSE, note=note, user=user)
        _record(
            stay,
            event_type="stay.extended",
            severity="info",
            title=f"Stay extended: room {room.number}",
            message=f"{stay.primary_guest.full_name} · {old_end} → {new_check_out_date}",
            user=user,
        )
        return stay


class ShortenStayService:
    """Shorten an in-house stay — from the STAY, the operational truth.

    The freed nights go back to inventory (the reservation's end shrinks with
    the stay). Charges are NEVER touched — any financial correction is a
    finance-side operation. Shortening never checks the guest out by itself.
    """

    @staticmethod
    @transaction.atomic
    def execute(stay, *, new_check_out_date, reason="", user=None) -> Stay:
        stay = _require_in_house(stay)
        old_end = stay.planned_check_out_date
        business_date = get_business_date(stay.hotel)
        if new_check_out_date >= old_end:
            raise InvalidStayChange(
                {
                    "reason": "new_date_not_before_current",
                    "current_check_out": str(old_end),
                }
            )
        # >= business date also guarantees >= the actual arrival date, since
        # the arrival-date guard makes future check-ins impossible.
        if new_check_out_date < business_date:
            raise InvalidStayChange(
                {
                    "reason": "before_business_date",
                    "business_date": str(business_date),
                }
            )
        if new_check_out_date <= stay.planned_check_in_date:
            raise InvalidStayChange(
                {
                    "reason": "before_check_in",
                    "check_in_date": str(stay.planned_check_in_date),
                }
            )
        stay.planned_check_out_date = new_check_out_date
        stay.save(update_fields=["planned_check_out_date", "updated_at"])
        _shrink_reservation_end(stay.reservation, business_date=business_date)
        note = f"shortened {old_end} -> {new_check_out_date}"
        if (reason or "").strip():
            note = f"{note} · {reason.strip()}"
        _log(stay, StayStatus.IN_HOUSE, StayStatus.IN_HOUSE, note=note, user=user)
        _record(
            stay,
            event_type="stay.shortened",
            severity="info",
            title=f"Stay shortened: room {stay.room.number}",
            message=f"{stay.primary_guest.full_name} · {old_end} → {new_check_out_date}",
            user=user,
        )
        return stay


class RoomMoveService:
    """Move an in-house stay to another room — with a mandatory reason.

    The new room must be ready exactly like a check-in room (available, not
    occupied, not held by another reservation for the remaining window, with
    enough capacity). The vacated room goes to housekeeping like a check-out
    (dirty + one cleaning task). History is preserved: the stay's status log
    records old room, new room, actor, time and reason.
    """

    @staticmethod
    @transaction.atomic
    def execute(stay, *, new_room, reason, user=None) -> Stay:
        if not (reason or "").strip():
            raise InvalidStayChange({"reason": "move_reason_required"})
        stay = _require_in_house(stay)
        if new_room.pk == stay.room_id:
            raise InvalidStayChange({"reason": "same_room"})
        # Lock both rooms in a stable id order to avoid deadlocks.
        locked = {
            r.pk: r
            for r in Room.objects.select_for_update()
            .filter(pk__in=sorted([stay.room_id, new_room.pk]))
            .order_by("pk")
            .select_related("room_type")
        }
        old_room = locked[stay.room_id]
        new_room = locked[new_room.pk]
        if new_room.hotel_id != stay.hotel_id:
            raise CrossTenantReference({"field": "room"})
        if not new_room.is_active or new_room.status != CHECK_IN_READY_STATUS:
            raise RoomNotReady({"room": new_room.id, "status": new_room.status})
        if Stay.objects.filter(
            hotel=stay.hotel, room=new_room, status=StayStatus.IN_HOUSE
        ).exists():
            raise RoomOccupied({"room": new_room.id})
        guest_count = stay.guests.count() or 1
        if guest_count > new_room.room_type.max_capacity:
            raise InvalidStayChange(
                {
                    "reason": "capacity_exceeded",
                    "guests": guest_count,
                    "max_capacity": new_room.room_type.max_capacity,
                }
            )
        business_date = get_business_date(stay.hotel)
        window_end = max(
            stay.planned_check_out_date, business_date + timedelta(days=1)
        )
        # Central engine: the new room must be free (no pinned reservation, no
        # maintenance/out-of-service, type capacity) until the stay's end.
        AvailabilityService.ensure_can_book(
            stay.hotel,
            [
                {
                    "room_type_id": new_room.room_type_id,
                    "quantity": 1,
                    "room_id": new_room.id,
                }
            ],
            business_date,
            window_end,
            exclude_reservation_id=stay.reservation_id,
        )
        stay.room = new_room
        stay.save(update_fields=["room", "updated_at"])
        # Keep availability unified: the reservation line follows the guest
        # (a pinned line is repinned; a 1-room unpinned line gets pinned so
        # the new room is protected for the remaining window).
        line = stay.reservation_line
        if line is not None:
            line = ReservationRoomLine.objects.select_for_update().get(pk=line.pk)
            if line.room_id == old_room.id or (
                line.room_id is None and line.quantity == 1
            ):
                line.room = new_room
                line.save(update_fields=["room", "updated_at"])
        # The vacated room goes to housekeeping exactly like a check-out.
        if old_room.status == RoomStatus.AVAILABLE:
            change_room_status(old_room, RoomStatus.DIRTY, note="", user=user)
        from apps.operations.models import HousekeepingTaskType, OperationPriority
        from apps.operations.services import create_housekeeping_task

        # stay=None so the real check-out's idempotent task (keyed by stay)
        # is not suppressed later; on_active="skip" so an already-active task
        # on the vacated room never breaks the move.
        create_housekeeping_task(
            stay.hotel,
            user=user,
            room=old_room,
            stay=None,
            task_type=HousekeepingTaskType.CHECKOUT_CLEANING,
            priority=OperationPriority.NORMAL,
            notes=f"Room move: guest moved to room {new_room.number}",
            on_active="skip",
        )
        note = f"room moved {old_room.number} -> {new_room.number} · {reason.strip()}"
        _log(stay, StayStatus.IN_HOUSE, StayStatus.IN_HOUSE, note=note, user=user)
        _record(
            stay,
            event_type="stay.room_moved",
            severity="warning",
            title=f"Room move: {old_room.number} → {new_room.number}",
            message=f"{stay.primary_guest.full_name} · {reason.strip()}",
            user=user,
        )
        return stay


# --- RESERVATIONS-FORM-REWORK: occupant → StayGuest promotion -----------------
# Used by the immediate-check-in orchestration to carry a reservation's named
# adult companions into the stay. Runs inside the caller's transaction.


def _compose_occupant_name(occupant) -> str:
    """A display ``full_name`` for a companion from its structured parts."""
    parts = [
        (occupant.first_name or "").strip(),
        (occupant.father_name or "").strip(),
        (occupant.last_name or "").strip(),
    ]
    name = " ".join(part for part in parts if part).strip()
    return name or (occupant.first_name or "").strip() or "Companion"


def _guest_from_occupant(hotel, occupant, *, user=None):
    """Get-or-create a hotel-scoped ``Guest`` for an occupant with no guest link.

    Reuses an existing guest by NORMALIZED national ID — the same key the partial
    per-hotel national-id unique constraint uses (see ``_ensure_primary_guest``) —
    so a differently-formatted national ID reuses the existing guest instead of
    creating a duplicate that would then trip the constraint and roll the whole
    check-in back; the promotion stays idempotent. Otherwise a lightweight Guest
    is created from the occupant's structured snapshot. The generic
    ``document_type``/``document_number`` are deliberately NOT copied — that would
    risk tripping the per-hotel document uniqueness constraint and roll back.
    """
    from apps.guests.models import Guest
    from apps.guests.normalize import normalize_id

    national_id = (occupant.national_id or "").strip()
    national_id_normalized = normalize_id(national_id)
    if national_id_normalized:
        existing = Guest.objects.filter(
            hotel=hotel, national_id_normalized=national_id_normalized
        ).first()
        if existing is not None:
            return existing
    actor = user if getattr(user, "is_authenticated", False) else None
    return Guest.objects.create(
        hotel=hotel,
        full_name=_compose_occupant_name(occupant),
        first_name=(occupant.first_name or ""),
        last_name=(occupant.last_name or ""),
        father_name=(occupant.father_name or ""),
        mother_name=(occupant.mother_name or ""),
        national_id=national_id,
        nationality=(occupant.nationality or "")[:80],
        date_of_birth=occupant.date_of_birth,
        created_by=actor,
        updated_by=actor,
    )


def promote_reservation_occupants(reservation, stay, *, user=None) -> list:
    """Create one companion ``StayGuest`` per adult occupant of ``reservation``.

    - Uses each occupant's linked guest when present; otherwise creates a
      hotel-scoped Guest from its structured fields (see ``_guest_from_occupant``).
    - Idempotent/safe: skips any guest already attached to the stay — including
      the PRIMARY that ``CheckInService`` already created (never duplicated) — and
      honors the ``unique_guest_per_stay`` constraint.
    - Cross-tenant safe: an occupant guest from another hotel is skipped.

    Returns the ``StayGuest`` rows created (possibly empty). Runs in the caller's
    transaction so any failure rolls the whole compose back.
    """
    if reservation is None:
        return []
    existing_guest_ids = set(
        StayGuest.objects.filter(stay=stay).values_list("guest_id", flat=True)
    )
    created = []
    for occupant in reservation.occupants.all():
        guest = occupant.guest or _guest_from_occupant(
            stay.hotel, occupant, user=user
        )
        if guest is None or guest.hotel_id != stay.hotel_id:
            continue
        if guest.id in existing_guest_ids:
            continue
        stay_guest = StayGuest.objects.create(
            hotel=stay.hotel,
            stay=stay,
            guest=guest,
            role=StayGuestRole.COMPANION,
        )
        existing_guest_ids.add(guest.id)
        created.append(stay_guest)
    return created


def stays_overview(hotel) -> dict:
    """Counts for the six operational cards (§6/§50) in a FIXED set of queries —
    never per-row work — based on the hotel's current business date.

    1 arriving today · 2 awaiting check-in (due/overdue, no stay) · 3 checked-in
    today · 4 current residents · 5 departing today · 6 needs attention (overdue
    arrivals + overstays + folios awaiting final charges).
    """
    from django.db.models import Q

    from apps.reservations.models import Reservation, ReservationStatus

    from .models import Stay, StayStatus

    bd = get_business_date(hotel)
    confirmed_no_stay = Reservation.objects.filter(
        hotel=hotel, status=ReservationStatus.CONFIRMED, stays__isnull=True,
    )
    arriving_today = confirmed_no_stay.filter(check_in_date=bd).count()
    awaiting_check_in = confirmed_no_stay.filter(check_in_date__lte=bd).count()
    overdue_arrivals = confirmed_no_stay.filter(check_in_date__lt=bd).count()

    in_house = Stay.objects.filter(hotel=hotel, status=StayStatus.IN_HOUSE)
    current_residents = in_house.count()
    departing_today = in_house.filter(planned_check_out_date=bd).count()
    checked_in_today = Stay.objects.filter(
        hotel=hotel, actual_check_in_at__date=bd
    ).count()

    stays_attention = (
        in_house.filter(
            Q(planned_check_out_date__lt=bd)
            | Q(folios__status="open", folios__awaiting_final_charges=True)
        )
        .distinct()
        .count()
    )
    return {
        "business_date": str(bd),
        "arriving_today": arriving_today,
        "awaiting_check_in": awaiting_check_in,
        "checked_in_today": checked_in_today,
        "current_residents": current_residents,
        "departing_today": departing_today,
        "needs_attention": overdue_arrivals + stays_attention,
    }
