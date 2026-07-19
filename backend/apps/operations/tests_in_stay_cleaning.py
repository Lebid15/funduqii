"""WP4 — in-stay vs check-out cleaning, service outcome, come-back-later.

Distinguishes CHECK-OUT cleaning (vacant room) from IN-STAY cleaning (occupied
room — occupancy DERIVED from an in-house ``Stay``, the single source of truth).

Pinned behaviour:
* Completing an IN-STAY cleaning records a ``service_outcome`` but NEVER changes
  the room status and NEVER writes a ``RoomStatusLog`` — an occupied room's
  state cannot be corrupted, even when ``mark_room_available=True`` is asked.
* The four terminal outcomes are exactly cleaned / guest_refused /
  do_not_disturb / no_access. ``come_back_later`` is NOT one of them.
* ``come_back_later`` is a SEPARATE, non-terminal event: the task stays active,
  an event is logged, and it can be actioned again and completed later.
* CHECK-OUT (vacant) cleaning keeps its existing release / dirty behaviour.
* The completion branch is driven by OCCUPANCY (in-house Stay), not task_type.
* come-back-later needs ``housekeeping.status_update``; creating a task for an
  occupied room needs ``housekeeping.create`` (no new role / permission).
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.common.exceptions import InvalidOperationStatusTransition
from apps.hotels.models import HotelSettings
from apps.operations.models import (
    HousekeepingServiceOutcome,
    HousekeepingStatus,
    HousekeepingTaskType,
    OperationPriority,
)
from apps.operations.services import (
    ACTIVE_HK_STATUSES,
    approve_inspection,
    cancel_housekeeping_task,
    change_housekeeping_status,
    come_back_later_housekeeping_task,
    complete_housekeeping_task,
    create_housekeeping_task,
    reject_inspection,
)
from apps.operations.tests import add_member, make_hotel, make_room, make_stay
from apps.rooms.models import RoomStatus, RoomStatusLog

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

OUTCOMES = [
    HousekeepingServiceOutcome.CLEANED,
    HousekeepingServiceOutcome.GUEST_REFUSED,
    HousekeepingServiceOutcome.DO_NOT_DISTURB,
    HousekeepingServiceOutcome.NO_ACCESS,
]


def _room_log_count(room):
    return RoomStatusLog.objects.filter(room=room).count()


# --------------------------------------------------------------------------- #
# IN-STAY (occupied) completion — status untouched, no RoomStatusLog            #
# --------------------------------------------------------------------------- #


class InStayCompletionServiceTests(TestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.mgr = add_member(
            self.hotel,
            "mgr@x.com",
            perms=["housekeeping.view", "housekeeping.create", "housekeeping.status_update"],
        )

    def _occupied_task(
        self,
        *,
        number,
        room_status=RoomStatus.DIRTY,
        task_type=HousekeepingTaskType.DAILY_CLEANING,
    ):
        room = make_room(self.hotel, number=number, status=room_status)
        make_stay(self.hotel, room)  # in-house stay -> occupied (derived)
        task = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=room,
            task_type=task_type,
            priority=OperationPriority.NORMAL,
        )
        return room, task

    def test_in_stay_completion_each_outcome_no_status_change_no_log(self):
        # Every one of the four outcomes: task completes, outcome stored, room
        # status UNCHANGED and NO RoomStatusLog written by the completion — even
        # though mark_room_available=True is requested (an occupied room is
        # never released).
        for i, outcome in enumerate(OUTCOMES):
            room, task = self._occupied_task(number=f"20{i}", room_status=RoomStatus.DIRTY)
            before_status = room.status
            before_logs = _room_log_count(room)
            complete_housekeeping_task(
                task,
                user=self.mgr,
                mark_room_available=True,
                service_outcome=outcome,
            )
            task.refresh_from_db()
            room.refresh_from_db()
            self.assertEqual(task.status, HousekeepingStatus.COMPLETED)
            self.assertEqual(task.service_outcome, outcome)
            self.assertEqual(room.status, before_status)  # untouched by completion
            self.assertEqual(_room_log_count(room), before_logs)  # no new log

    def test_in_stay_start_and_complete_never_touch_room_status(self):
        # An occupied room legitimately keeps its status (here `available` —
        # occupancy is derived from the in-house Stay, which prevents double
        # booking). STARTING the cleaning does NOT flip it to `cleaning`, and
        # COMPLETING does NOT change it either. The whole cleaning lifecycle
        # writes ZERO RoomStatusLog rows for an occupied room.
        room, task = self._occupied_task(number="210", room_status=RoomStatus.AVAILABLE)
        logs0 = _room_log_count(room)
        change_housekeeping_status(
            task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
        )
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # start left it alone
        self.assertEqual(_room_log_count(room), logs0)  # no log from start
        complete_housekeeping_task(
            task,
            user=self.mgr,
            mark_room_available=True,  # even when release is requested
            service_outcome=HousekeepingServiceOutcome.CLEANED,
        )
        task.refresh_from_db()
        room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.COMPLETED)
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # completion left it alone
        self.assertEqual(_room_log_count(room), logs0)  # zero logs across lifecycle

    def test_occupancy_branch_uses_stay_not_task_type(self):
        # (a) A CHECKOUT_CLEANING task on a room that STILL has an in-house stay
        #     is treated as IN-STAY (room untouched) — task_type does not matter.
        room, task = self._occupied_task(
            number="220",
            room_status=RoomStatus.DIRTY,
            task_type=HousekeepingTaskType.CHECKOUT_CLEANING,
        )
        before_logs = _room_log_count(room)
        complete_housekeeping_task(
            task,
            user=self.mgr,
            mark_room_available=True,
            service_outcome=HousekeepingServiceOutcome.CLEANED,
        )
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.DIRTY)  # occupancy wins
        self.assertEqual(_room_log_count(room), before_logs)

        # (b) A DAILY_CLEANING task on a VACANT room follows the vacant path and
        #     releases through the guard cycle — again driven by occupancy.
        vroom = make_room(self.hotel, number="221", status=RoomStatus.DIRTY)
        vtask = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=vroom,
            task_type=HousekeepingTaskType.DAILY_CLEANING,
            priority=OperationPriority.NORMAL,
        )
        change_housekeeping_status(
            vtask, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
        )
        vroom.refresh_from_db()
        self.assertEqual(vroom.status, RoomStatus.CLEANING)
        complete_housekeeping_task(
            vtask,
            user=self.mgr,
            mark_room_available=True,
            service_outcome=HousekeepingServiceOutcome.CLEANED,
        )
        vroom.refresh_from_db()
        self.assertEqual(vroom.status, RoomStatus.AVAILABLE)  # released (vacant)


# --------------------------------------------------------------------------- #
# CHECK-OUT (vacant) cleaning keeps its existing behaviour (regression)         #
# --------------------------------------------------------------------------- #


class CheckoutVacantRegressionTests(TestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.mgr = add_member(
            self.hotel,
            "mgr@x.com",
            perms=["housekeeping.create", "housekeeping.status_update"],
        )

    def _vacant_started_checkout(self, number):
        room = make_room(self.hotel, number=number, status=RoomStatus.DIRTY)
        task = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=room,
            task_type=HousekeepingTaskType.CHECKOUT_CLEANING,
            priority=OperationPriority.NORMAL,
        )
        change_housekeeping_status(
            task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
        )
        room.refresh_from_db()
        return room, task

    def test_checkout_complete_without_release_goes_dirty(self):
        room, task = self._vacant_started_checkout("301")
        self.assertEqual(room.status, RoomStatus.CLEANING)
        complete_housekeeping_task(task, user=self.mgr, mark_room_available=False)
        room.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.DIRTY)  # unchanged behaviour
        # service_outcome defaults to `cleaned` for a check-out completion.
        self.assertEqual(task.service_outcome, HousekeepingServiceOutcome.CLEANED)

    def test_checkout_complete_release_via_guard_goes_available(self):
        room, task = self._vacant_started_checkout("302")
        complete_housekeeping_task(task, user=self.mgr, mark_room_available=True)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # released via guard


# --------------------------------------------------------------------------- #
# Inspection-enabled hotel — approve / reject NEVER corrupt an occupied room     #
# (this is the PRIMARY in-stay completion path on inspection hotels)            #
# --------------------------------------------------------------------------- #


class InStayInspectionTests(TestCase):
    def setUp(self):
        self.hotel = make_hotel()
        HotelSettings.objects.update_or_create(
            hotel=self.hotel, defaults={"housekeeping_inspection_required": True}
        )
        self.mgr = add_member(
            self.hotel,
            "mgr@x.com",
            perms=[
                "housekeeping.create",
                "housekeeping.status_update",
                "housekeeping.inspect",
            ],
        )

    def _occupied_started(self, number, room_status=RoomStatus.AVAILABLE):
        room = make_room(self.hotel, number=number, status=room_status)
        make_stay(self.hotel, room)  # in-house -> occupied
        task = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=room,
            task_type=HousekeepingTaskType.DAILY_CLEANING,
            priority=OperationPriority.NORMAL,
        )
        change_housekeeping_status(
            task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
        )
        room.refresh_from_db()
        return room, task

    def _vacant_started(self, number):
        room = make_room(self.hotel, number=number, status=RoomStatus.DIRTY)
        task = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=room,
            task_type=HousekeepingTaskType.CHECKOUT_CLEANING,
            priority=OperationPriority.NORMAL,
        )
        change_housekeeping_status(
            task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
        )
        room.refresh_from_db()
        return room, task

    def test_occupied_complete_parks_then_approve_no_status_change(self):
        room, task = self._occupied_started("601")
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # start left it alone
        before_logs = _room_log_count(room)
        # Completion parks for inspection; room untouched; outcome preserved.
        complete_housekeeping_task(
            task,
            user=self.mgr,
            mark_room_available=True,
            service_outcome=HousekeepingServiceOutcome.GUEST_REFUSED,
        )
        task.refresh_from_db()
        room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.AWAITING_INSPECTION)
        self.assertEqual(task.service_outcome, HousekeepingServiceOutcome.GUEST_REFUSED)
        self.assertEqual(room.status, RoomStatus.AVAILABLE)
        self.assertEqual(_room_log_count(room), before_logs)
        # Approve -> task completed, room UNCHANGED, NOT released, no log.
        approve_inspection(task, user=self.mgr)
        task.refresh_from_db()
        room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.COMPLETED)
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # never released
        self.assertEqual(_room_log_count(room), before_logs)  # no RoomStatusLog

    def test_occupied_reject_no_status_change(self):
        room, task = self._occupied_started("602")
        complete_housekeeping_task(
            task, user=self.mgr, service_outcome=HousekeepingServiceOutcome.CLEANED
        )
        task.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.AWAITING_INSPECTION)
        before_logs = _room_log_count(room)
        reject_inspection(task, reason="missed the bathroom", user=self.mgr)
        task.refresh_from_db()
        room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.IN_PROGRESS)
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # NOT dirtied
        self.assertEqual(_room_log_count(room), before_logs)  # no log

    def test_vacant_approve_releases_via_guard(self):
        # The occupancy gate must ONLY affect occupied rooms — a VACANT room
        # under the same inspection-on hotel still releases on approval.
        room, task = self._vacant_started("603")
        self.assertEqual(room.status, RoomStatus.CLEANING)  # vacant -> cleaning
        complete_housekeeping_task(task, user=self.mgr, mark_room_available=True)
        task.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.AWAITING_INSPECTION)
        approve_inspection(task, user=self.mgr)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # released

    def test_vacant_reject_dirties(self):
        room, task = self._vacant_started("604")
        complete_housekeeping_task(task, user=self.mgr)
        task.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.AWAITING_INSPECTION)
        reject_inspection(task, reason="redo", user=self.mgr)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.DIRTY)  # vacant behaviour kept


# --------------------------------------------------------------------------- #
# Cancel — never corrupts an occupied room; vacant behaviour preserved          #
# --------------------------------------------------------------------------- #


class CancelOccupancyTests(TestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.mgr = add_member(
            self.hotel,
            "mgr@x.com",
            perms=[
                "housekeeping.create",
                "housekeeping.status_update",
                "housekeeping.cancel",
            ],
        )

    def test_cancel_occupied_room_status_unchanged(self):
        room = make_room(self.hotel, number="701", status=RoomStatus.AVAILABLE)
        make_stay(self.hotel, room)  # occupied
        task = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=room,
            task_type=HousekeepingTaskType.DAILY_CLEANING,
            priority=OperationPriority.NORMAL,
        )
        change_housekeeping_status(
            task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
        )
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # start left it alone
        before_logs = _room_log_count(room)
        cancel_housekeeping_task(task, reason="guest declined", user=self.mgr)
        task.refresh_from_db()
        room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.CANCELLED)
        self.assertEqual(room.status, RoomStatus.AVAILABLE)  # unchanged
        self.assertEqual(_room_log_count(room), before_logs)  # no log

    def test_cancel_vacant_cleaning_room_goes_dirty(self):
        room = make_room(self.hotel, number="702", status=RoomStatus.DIRTY)
        task = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=room,
            task_type=HousekeepingTaskType.CHECKOUT_CLEANING,
            priority=OperationPriority.NORMAL,
        )
        change_housekeeping_status(
            task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
        )
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.CLEANING)
        cancel_housekeeping_task(task, reason="not needed", user=self.mgr)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.DIRTY)  # vacant behaviour kept


# --------------------------------------------------------------------------- #
# come_back_later — non-terminal, logged, repeatable                            #
# --------------------------------------------------------------------------- #


class ComeBackLaterServiceTests(TestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.mgr = add_member(
            self.hotel,
            "mgr@x.com",
            perms=["housekeeping.create", "housekeeping.status_update"],
        )

    def _task(self, number, *, start=True):
        room = make_room(self.hotel, number=number, status=RoomStatus.AVAILABLE)
        make_stay(self.hotel, room)  # occupied — the in-stay context
        task = create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=room,
            task_type=HousekeepingTaskType.DAILY_CLEANING,
            priority=OperationPriority.NORMAL,
        )
        if start:
            change_housekeeping_status(
                task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.mgr
            )
            task.refresh_from_db()
        return task

    def test_come_back_later_keeps_task_active_logs_and_repeatable(self):
        task = self._task("401", start=True)
        before_status = task.status  # in_progress
        before_logs = task.status_logs.count()
        come_back_later_housekeeping_task(task, user=self.mgr, note="guest asleep")
        task.refresh_from_db()
        self.assertEqual(task.status, before_status)  # UNCHANGED — not completed
        self.assertIn(task.status, ACTIVE_HK_STATUSES)  # still active
        self.assertEqual(task.status_logs.count(), before_logs + 1)  # event logged
        self.assertEqual(task.service_outcome, "")  # not a completion / outcome
        # Can be actioned AGAIN (revisited later).
        come_back_later_housekeeping_task(task, user=self.mgr, note="still asleep")
        task.refresh_from_db()
        self.assertEqual(task.status, before_status)
        self.assertEqual(task.status_logs.count(), before_logs + 2)
        # And can STILL be completed afterwards.
        complete_housekeeping_task(
            task, user=self.mgr, service_outcome=HousekeepingServiceOutcome.CLEANED
        )
        task.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.COMPLETED)
        self.assertEqual(task.service_outcome, HousekeepingServiceOutcome.CLEANED)

    def test_come_back_later_on_pending_task_ok(self):
        task = self._task("402", start=False)  # pending
        self.assertEqual(task.status, HousekeepingStatus.PENDING)
        come_back_later_housekeeping_task(task, user=self.mgr)
        task.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.PENDING)  # still active

    def test_come_back_later_rejected_on_completed_task(self):
        task = self._task("403", start=True)
        complete_housekeeping_task(
            task, user=self.mgr, service_outcome=HousekeepingServiceOutcome.CLEANED
        )
        task.refresh_from_db()
        with self.assertRaises(InvalidOperationStatusTransition):
            come_back_later_housekeeping_task(task, user=self.mgr)


# --------------------------------------------------------------------------- #
# API surface: outcome validation + permissions                                 #
# --------------------------------------------------------------------------- #


class HousekeepingWp4ApiTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.mgr = add_member(
            self.hotel,
            "mgr@x.com",
            perms=["housekeeping.view", "housekeeping.create", "housekeeping.status_update"],
        )
        self.room = make_room(self.hotel, number="501", status=RoomStatus.AVAILABLE)

    def _make_task(self):
        return create_housekeeping_task(
            self.hotel,
            user=self.mgr,
            room=self.room,
            task_type=HousekeepingTaskType.DAILY_CLEANING,
            priority=OperationPriority.NORMAL,
        )

    def test_come_back_later_endpoint_requires_status_update_permission(self):
        task = self._make_task()
        viewer = add_member(
            self.hotel, "viewer@x.com", perms=["housekeeping.view", "housekeeping.create"]
        )
        self.client.force_authenticate(viewer)
        res = self.client.post(
            reverse("operations:housekeeping-come-back-later", args=[task.id]),
            {"note": "later"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 403)  # no status_update -> denied
        # With status_update -> 200 and the task stays active (unchanged).
        self.client.force_authenticate(self.mgr)
        res = self.client.post(
            reverse("operations:housekeeping-come-back-later", args=[task.id]),
            {"note": "later"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], HousekeepingStatus.PENDING)
        self.assertEqual(res.data["service_outcome"], "")

    def test_come_back_later_is_not_a_valid_service_outcome(self):
        task = self._make_task()
        self.client.force_authenticate(self.mgr)
        res = self.client.post(
            reverse("operations:housekeeping-complete", args=[task.id]),
            {"service_outcome": "come_back_later"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 400)  # rejected by the serializer choices
        task.refresh_from_db()
        self.assertNotEqual(task.status, HousekeepingStatus.COMPLETED)

    def test_complete_endpoint_stores_service_outcome_for_occupied_room(self):
        task = self._make_task()
        make_stay(self.hotel, self.room)  # occupied at completion time
        self.client.force_authenticate(self.mgr)
        res = self.client.post(
            reverse("operations:housekeeping-complete", args=[task.id]),
            {"service_outcome": "guest_refused"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], HousekeepingStatus.COMPLETED)
        self.assertEqual(res.data["service_outcome"], "guest_refused")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)  # untouched

    def test_creating_task_for_occupied_room_requires_housekeeping_create(self):
        make_stay(self.hotel, self.room)  # occupied room
        viewer = add_member(self.hotel, "v2@x.com", perms=["housekeeping.view"])
        self.client.force_authenticate(viewer)
        res = self.client.post(
            reverse("operations:housekeeping-list"),
            {"room": self.room.id, "task_type": "daily_cleaning"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 403)  # no create permission
        # Existing housekeeping.create unlocks it — no new role / permission.
        self.client.force_authenticate(self.mgr)
        res = self.client.post(
            reverse("operations:housekeeping-list"),
            {"room": self.room.id, "task_type": "daily_cleaning"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)
