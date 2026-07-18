"""WP1 — central, fail-closed room-release guard.

A room may become ``available`` ONLY as the result of a correct operational
release cycle. These tests pin the guard on EVERY path:

* the direct ``POST /rooms/{id}/status`` endpoint (and every external caller)
  can NEVER set ``available`` — refused 409 ``room_not_releasable`` in every
  state, and the room stays unchanged;
* ``cycle_source`` is non-forgeable — not a serializer field, ignored if a
  client sends it in the body;
* the legitimate operations paths (cleaning completion, inspection approval,
  maintenance close → available) STILL release the room;
* the operations-level releasability check refuses a dirty room / a room with
  an active cleaning task with a neutral ``details.reason``;
* two sequential releases behave (the row-lock code path runs).
"""
from __future__ import annotations

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.common.exceptions import RoomBlockedByMaintenance, RoomNotReleasable
from apps.hotels.models import HotelSettings
from apps.operations.models import (
    HousekeepingStatus,
    MaintenanceCategory,
    OperationPriority,
    RoomBlockStatus,
)
from apps.operations.services import (
    approve_inspection,
    change_housekeeping_status,
    close_maintenance_request,
    complete_housekeeping_task,
    create_housekeeping_task,
    create_maintenance_request,
    resolve_maintenance_request,
)
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.rooms.serializers import RoomStatusUpdateSerializer
from apps.rooms.services import RoomReleaseCycle, change_room_status
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType
from apps.accounts.models import User

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731


def _manager(hotel, email="m@x.com"):
    user = User.objects.create_user(
        email=email, password="StrongPass!234", full_name="Manager"
    )
    HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=MembershipType.MANAGER, is_active=True
    )
    return user


def _room(hotel, number="101", status=RoomStatus.AVAILABLE):
    floor = Floor.objects.create(hotel=hotel, name="G", number="0")
    rt = RoomType.objects.create(
        hotel=hotel, name="Std", code=f"S{number}", base_capacity=2, max_capacity=2
    )
    return Room.objects.create(
        hotel=hotel, floor=floor, room_type=rt, number=number, status=status
    )


class _Base(APITestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Hotel", slug="h", status=HotelStatus.ACTIVE
        )
        self.manager = _manager(self.hotel)
        self.client.force_authenticate(self.manager)

    # -- helpers -----------------------------------------------------------
    def _set_status(self, room, status, note=""):
        body = {"status": status}
        if note:
            body["note"] = note
        return self.client.post(
            reverse("rooms:room-status", args=[room.id]),
            body,
            format="json",
            **HDR(self.hotel),
        )

    def _make_task(self, room, *, start=False):
        task = create_housekeeping_task(
            self.hotel,
            user=self.manager,
            room=room,
            priority=OperationPriority.NORMAL,
        )
        if start:
            change_housekeeping_status(
                task, new_status=HousekeepingStatus.IN_PROGRESS, user=self.manager
            )
            room.refresh_from_db()
        return task

    def _blocking_maintenance(self, room, block=RoomBlockStatus.MAINTENANCE):
        req = create_maintenance_request(
            self.hotel,
            user=self.manager,
            room=room,
            title="Broken AC",
            category=MaintenanceCategory.PLUMBING,
            priority=OperationPriority.NORMAL,
            affects_room_availability=True,
            room_block_status=block,
        )
        room.refresh_from_db()
        return req


# --------------------------------------------------------------------------- #
# Direct POST /rooms/{id}/status → available is refused in EVERY state          #
# --------------------------------------------------------------------------- #


class DirectPathReleaseGuardTests(_Base):
    def _assert_refused(self, room, *, expected_reason, unchanged_status):
        res = self._set_status(room, "available")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "room_not_releasable")
        self.assertEqual(res.data["details"]["reason"], expected_reason)
        room.refresh_from_db()
        self.assertEqual(room.status, unchanged_status)

    def test_available_on_dirty_refused(self):
        room = _room(self.hotel, status=RoomStatus.DIRTY)
        self._assert_refused(
            room, expected_reason="room_dirty", unchanged_status=RoomStatus.DIRTY
        )

    def test_available_on_open_blocking_maintenance_refused(self):
        room = _room(self.hotel)
        self._blocking_maintenance(room)  # room -> maintenance, request open
        self._assert_refused(
            room,
            expected_reason="maintenance_block",
            unchanged_status=RoomStatus.MAINTENANCE,
        )

    def test_available_on_active_cleaning_task_refused(self):
        room = _room(self.hotel, status=RoomStatus.DIRTY)
        self._make_task(room, start=True)  # room -> cleaning, task active
        self.assertEqual(room.status, RoomStatus.CLEANING)
        self._assert_refused(
            room,
            expected_reason="operational_block",
            unchanged_status=RoomStatus.CLEANING,
        )

    def test_available_on_maintenance_refused(self):
        room = _room(self.hotel)
        change_room_status(room, RoomStatus.MAINTENANCE, note="pump", user=self.manager)
        self._assert_refused(
            room,
            expected_reason="maintenance_block",
            unchanged_status=RoomStatus.MAINTENANCE,
        )

    def test_available_on_out_of_service_refused(self):
        room = _room(self.hotel)
        change_room_status(
            room, RoomStatus.OUT_OF_SERVICE, note="flood", user=self.manager
        )
        self._assert_refused(
            room,
            expected_reason="maintenance_block",
            unchanged_status=RoomStatus.OUT_OF_SERVICE,
        )

    def test_available_on_archived_refused(self):
        room = _room(self.hotel)
        change_room_status(room, RoomStatus.ARCHIVED, note="", user=self.manager)
        self._assert_refused(
            room,
            expected_reason="maintenance_block",
            unchanged_status=RoomStatus.ARCHIVED,
        )

    def test_s2_open_maintenance_plus_manually_dirty_refused(self):
        # S2: an open blocking maintenance request AND a manually-dirtied room.
        # The direct path still refuses (the room is not available), and the
        # room stays exactly as it was.
        room = _room(self.hotel)
        self._blocking_maintenance(room)  # -> maintenance
        change_room_status(room, RoomStatus.DIRTY, note="", user=self.manager)
        self._assert_refused(
            room, expected_reason="room_dirty", unchanged_status=RoomStatus.DIRTY
        )

    def test_noop_available_on_already_available_ok(self):
        # available -> available is NOT "becoming available"; left untouched.
        room = _room(self.hotel, status=RoomStatus.AVAILABLE)
        res = self._set_status(room, "available")
        self.assertEqual(res.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)

    def test_non_available_direct_transitions_still_work(self):
        # The guard governs ONLY `available`; every other move still works.
        room = _room(self.hotel, status=RoomStatus.AVAILABLE)
        self.assertEqual(self._set_status(room, "dirty").status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.DIRTY)
        ok = self._set_status(room, "maintenance", note="AC")
        self.assertEqual(ok.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.MAINTENANCE)


# --------------------------------------------------------------------------- #
# cycle_source is non-forgeable                                                  #
# --------------------------------------------------------------------------- #


class CycleSourceNonForgeableTests(_Base):
    def test_cycle_source_is_not_a_serializer_field(self):
        fields = RoomStatusUpdateSerializer().fields
        self.assertNotIn("cycle_source", fields)
        self.assertEqual(set(fields), {"status", "note"})

    def test_client_supplied_cycle_source_is_ignored(self):
        # A client putting `cycle_source` in the body (string form of the enum)
        # changes nothing — it is not a field and is never passed through.
        room = _room(self.hotel, status=RoomStatus.DIRTY)
        res = self.client.post(
            reverse("rooms:room-status", args=[room.id]),
            {"status": "available", "cycle_source": "housekeeping_release"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "room_not_releasable")
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.DIRTY)


# --------------------------------------------------------------------------- #
# Legitimate operations release paths STILL succeed                             #
# --------------------------------------------------------------------------- #


class LegitimateReleasePathsTests(_Base):
    def test_complete_mark_available_releases_cleanable_room(self):
        room = _room(self.hotel, status=RoomStatus.DIRTY)
        task = self._make_task(room, start=True)  # -> cleaning
        complete_housekeeping_task(task, user=self.manager, mark_room_available=True)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)

    def test_approve_inspection_releases_room(self):
        HotelSettings.objects.update_or_create(
            hotel=self.hotel, defaults={"housekeeping_inspection_required": True}
        )
        room = _room(self.hotel, status=RoomStatus.DIRTY)
        task = self._make_task(room, start=True)  # -> cleaning
        # Completion parks for inspection (room stays cleaning, not released).
        complete_housekeeping_task(task, user=self.manager, mark_room_available=True)
        task.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.AWAITING_INSPECTION)
        room.refresh_from_db()
        self.assertNotEqual(room.status, RoomStatus.AVAILABLE)
        # Approval completes the task AND releases the room.
        approve_inspection(task, user=self.manager)
        task.refresh_from_db()
        room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingStatus.COMPLETED)
        self.assertEqual(room.status, RoomStatus.AVAILABLE)

    def test_maintenance_close_available_releases_after_block_clears(self):
        room = _room(self.hotel)
        req = self._blocking_maintenance(room)  # -> maintenance
        resolve_maintenance_request(req, user=self.manager)
        close_maintenance_request(
            req, user=self.manager, room_next_status="available"
        )
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)


# --------------------------------------------------------------------------- #
# Operations-level releasability refusals (neutral details.reason)              #
# --------------------------------------------------------------------------- #


class ReleasabilityReasonTests(_Base):
    def test_complete_cannot_release_uncleaned_dirty_room(self):
        # A task completed WITHOUT ever being started leaves the room dirty;
        # the release is refused (room_dirty) rather than skipping the cleaning.
        room = _room(self.hotel, status=RoomStatus.DIRTY)
        task = self._make_task(room, start=False)  # room stays dirty
        with self.assertRaises(RoomNotReleasable) as ctx:
            complete_housekeeping_task(
                task, user=self.manager, mark_room_available=True
            )
        self.assertEqual(str(ctx.exception.detail["reason"]), "room_dirty")
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.DIRTY)

    def test_maintenance_close_blocked_by_active_housekeeping(self):
        room = _room(self.hotel)
        req = self._blocking_maintenance(room)  # -> maintenance
        self._make_task(room, start=False)  # active cleaning task on the room
        resolve_maintenance_request(req, user=self.manager)
        with self.assertRaises(RoomNotReleasable) as ctx:
            close_maintenance_request(
                req, user=self.manager, room_next_status="available"
            )
        self.assertEqual(str(ctx.exception.detail["reason"]), "active_housekeeping")
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.MAINTENANCE)

    def test_maintenance_close_blocked_by_other_open_request_keeps_maintenance_code(self):
        # Backward-compat: the maintenance-specific 409 is preserved when
        # ANOTHER open request still blocks the room.
        room = _room(self.hotel)
        self._blocking_maintenance(room, block=RoomBlockStatus.OUT_OF_SERVICE)
        req = self._blocking_maintenance(room)  # second blocking request
        resolve_maintenance_request(req, user=self.manager)
        with self.assertRaises(RoomBlockedByMaintenance):
            close_maintenance_request(
                req, user=self.manager, room_next_status="available"
            )


# --------------------------------------------------------------------------- #
# Serial row-lock behaviour                                                      #
# --------------------------------------------------------------------------- #


class SerialReleaseRowLockTests(_Base):
    def test_two_sequential_cleaning_releases_behave(self):
        room = _room(self.hotel, status=RoomStatus.DIRTY)
        # Cycle 1: dirty -> cleaning -> available.
        t1 = self._make_task(room, start=True)
        complete_housekeeping_task(t1, user=self.manager, mark_room_available=True)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)
        # Cycle 2 on the now-available room: available -> cleaning -> available.
        t2 = self._make_task(room, start=True)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.CLEANING)
        complete_housekeeping_task(t2, user=self.manager, mark_room_available=True)
        room.refresh_from_db()
        self.assertEqual(room.status, RoomStatus.AVAILABLE)
