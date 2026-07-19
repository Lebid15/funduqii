"""WP2 — DB-level guard: the partial-unique constraint
``uniq_active_housekeeping_task_per_room`` plus the read-only precheck command.

The constraint permits at most ONE ACTIVE cleaning task per ``(hotel, room)``;
ACTIVE = pending / assigned / in_progress / awaiting_inspection (mirrors
``apps.operations.services.ACTIVE_HK_STATUSES``). These tests prove the DB
rejects a direct second active insert (bypassing the service), that
completed / cancelled free the room for a fresh cycle, that the guard is
hotel-scoped and skips NULL-room history, that awaiting_inspection counts as
active, that the service surfaces a clean 409 both via the app-level check AND
via the IntegrityError backstop (and skips for automatic callers), and that the
read-only precheck reports offenders without changing anything.

NOTE: the authoritative constraint / concurrency evidence is PostgreSQL (later
gate). SQLite supports partial indexes, so the constraint behaviour is
demonstrable here, but true SELECT ... FOR UPDATE row-lock serialization is only
real on PostgreSQL.
"""
from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.common.exceptions import DuplicateActiveTask
from apps.operations.models import (
    HousekeepingStatus,
    HousekeepingTask,
    HousekeepingTaskType,
)
from apps.operations.services import create_housekeeping_task
from apps.operations.tests import make_hotel, make_room
from apps.rooms.models import RoomStatus

CONSTRAINT_NAME = "uniq_active_housekeeping_task_per_room"


def _task(hotel, room, *, number, status):
    """Insert a HousekeepingTask directly, BYPASSING the service, to exercise
    the raw DB constraint."""
    return HousekeepingTask.objects.create(
        hotel=hotel,
        task_number=number,
        room=room,
        status=status,
        task_type=HousekeepingTaskType.DAILY_CLEANING,
    )


class ActiveTaskConstraintTests(TestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)

    def test_second_active_insert_rejected_by_db(self):
        # Authoritative proof is PostgreSQL; the SQLite partial index shows it.
        _task(
            self.hotel, self.room, number="HK00001",
            status=HousekeepingStatus.PENDING,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _task(
                    self.hotel, self.room, number="HK00002",
                    status=HousekeepingStatus.ASSIGNED,
                )

    def test_second_active_allowed_after_completed(self):
        # A completed task does not hold the room — a fresh active task is fine.
        _task(
            self.hotel, self.room, number="HK00001",
            status=HousekeepingStatus.COMPLETED,
        )
        _task(
            self.hotel, self.room, number="HK00002",
            status=HousekeepingStatus.PENDING,
        )
        self.assertEqual(
            HousekeepingTask.objects.filter(room=self.room).count(), 2
        )

    def test_second_active_allowed_after_cancelled(self):
        _task(
            self.hotel, self.room, number="HK00001",
            status=HousekeepingStatus.CANCELLED,
        )
        _task(
            self.hotel, self.room, number="HK00002",
            status=HousekeepingStatus.IN_PROGRESS,
        )
        self.assertEqual(
            HousekeepingTask.objects.filter(room=self.room).count(), 2
        )

    def test_awaiting_inspection_counts_as_active(self):
        _task(
            self.hotel, self.room, number="HK00001",
            status=HousekeepingStatus.AWAITING_INSPECTION,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _task(
                    self.hotel, self.room, number="HK00002",
                    status=HousekeepingStatus.PENDING,
                )

    def test_constraint_is_hotel_scoped(self):
        # Same logical room number in two hotels: two DISTINCT rooms, each may
        # carry its own active task without colliding.
        other = make_hotel(slug="o2")
        oroom = make_room(other, number="101", status=RoomStatus.DIRTY)
        _task(
            self.hotel, self.room, number="HK00001",
            status=HousekeepingStatus.PENDING,
        )
        _task(
            other, oroom, number="HK00001",
            status=HousekeepingStatus.PENDING,
        )
        self.assertEqual(HousekeepingTask.objects.count(), 2)

    def test_null_room_tasks_do_not_collide(self):
        # Historical tasks whose room was later deleted (SET_NULL) are NOT
        # constrained — the partial condition requires room IS NOT NULL.
        _task(
            self.hotel, None, number="HK00001",
            status=HousekeepingStatus.PENDING,
        )
        _task(
            self.hotel, None, number="HK00002",
            status=HousekeepingStatus.PENDING,
        )
        self.assertEqual(
            HousekeepingTask.objects.filter(room__isnull=True).count(), 2
        )


class CreatePathDuplicateTests(TestCase):
    """The service surfaces DuplicateActiveTask (409) two ways: the app-level
    check and the DB-backed IntegrityError backstop."""

    def setUp(self):
        self.hotel = make_hotel()
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)

    def test_app_level_check_raises_409(self):
        create_housekeeping_task(self.hotel, room=self.room, priority="normal")
        with self.assertRaises(DuplicateActiveTask):
            create_housekeeping_task(
                self.hotel, room=self.room, priority="normal"
            )

    def test_integrity_error_backstop_raises_409(self):
        # Seed an active task, then neutralize ONLY the app-level exists() guard
        # so the INSERT reaches the DB and trips the partial-unique constraint —
        # proving the backstop turns a raced insert into a clean 409, not a 500.
        _task(
            self.hotel, self.room, number="HK09999",
            status=HousekeepingStatus.PENDING,
        )
        with mock.patch.object(HousekeepingTask.objects, "filter") as mfilter:
            mfilter.return_value.exists.return_value = False
            with self.assertRaises(DuplicateActiveTask):
                create_housekeeping_task(
                    self.hotel, room=self.room, priority="normal"
                )

    def test_integrity_error_backstop_skips_for_automatic_callers(self):
        # Automatic callers (check-out / room move) pass on_active="skip"; the
        # backstop must swallow the race and return None — never a 409/500.
        _task(
            self.hotel, self.room, number="HK09999",
            status=HousekeepingStatus.PENDING,
        )
        with mock.patch.object(HousekeepingTask.objects, "filter") as mfilter:
            mfilter.return_value.exists.return_value = False
            result = create_housekeeping_task(
                self.hotel, room=self.room, priority="normal", on_active="skip"
            )
        self.assertIsNone(result)


class PrecheckCommandTests(TestCase):
    """The read-only ``detect_duplicate_active_housekeeping`` command."""

    def setUp(self):
        self.hotel = make_hotel()
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)

    def test_reports_zero_on_clean_data(self):
        _task(
            self.hotel, self.room, number="HK00001",
            status=HousekeepingStatus.PENDING,
        )
        out = StringIO()
        call_command("detect_duplicate_active_housekeeping", stdout=out)
        self.assertIn("No rooms with more than one active", out.getvalue())

    def test_reports_offenders_when_duplicates_seeded(self):
        # The constraint blocks two active tasks per room, so the duplicates can
        # only be seeded after dropping the partial index for THIS transaction.
        # The TestCase rolls the transaction (and the DDL) back afterwards, so
        # the index is restored for every other test.
        with connection.cursor() as cur:
            cur.execute(f'DROP INDEX IF EXISTS "{CONSTRAINT_NAME}"')
        t1 = _task(
            self.hotel, self.room, number="HK00001",
            status=HousekeepingStatus.PENDING,
        )
        t2 = _task(
            self.hotel, self.room, number="HK00002",
            status=HousekeepingStatus.IN_PROGRESS,
        )
        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("detect_duplicate_active_housekeeping", stdout=out)
        self.assertEqual(ctx.exception.code, 1)
        report = out.getvalue()
        self.assertIn(f"room={self.room.id}", report)
        self.assertIn("active_tasks=2", report)
        self.assertIn(f"#{t1.id}", report)
        self.assertIn(f"#{t2.id}", report)
        self.assertIn("STOP", report)

    def test_null_room_duplicates_not_reported(self):
        # NULL-room history is unconstrained AND out of the precheck's scope.
        with connection.cursor() as cur:
            cur.execute(f'DROP INDEX IF EXISTS "{CONSTRAINT_NAME}"')
        _task(self.hotel, None, number="HK00001", status=HousekeepingStatus.PENDING)
        _task(self.hotel, None, number="HK00002", status=HousekeepingStatus.PENDING)
        out = StringIO()
        call_command("detect_duplicate_active_housekeeping", stdout=out)
        self.assertIn("No rooms with more than one active", out.getvalue())
