"""WP-CONC — REAL PostgreSQL concurrency proof for hotel operations.

These tests prove — on a REAL PostgreSQL database — that the WP1 room-status
row-locks (``SELECT ... FOR UPDATE`` inside the operations services) and the WP2
partial-unique constraint ``uniq_active_housekeeping_task_per_room`` (migration
operations/0003) actually SERIALIZE concurrent writers, so the system can never
reach an inconsistent operational state under contention.

They mirror the proven two-connection pattern in
``apps.finance.tests_concurrency``:

* ``TransactionTestCase`` — its ``setUp`` data is COMMITTED (no outer wrapping
  transaction), so the worker threads, each on its OWN database connection, can
  actually SEE the seeded hotel/room/task. Under a plain ``TestCase`` the
  fixtures would live in an uncommitted transaction invisible to the workers.
* ``threading.Barrier(2)`` — line the two workers up right at the contended
  operation so they hit the row lock / unique index simultaneously.
* each worker closes its OWN connection in ``finally``
  (``connections["default"].close()``) so the pool stays clean.
* a hard vendor guard — ``if connection.vendor != "postgresql": self.skipTest(...)``
  — because true multi-connection write concurrency + ``SELECT ... FOR UPDATE``
  row locking are only real on PostgreSQL (the production database). SQLite (the
  default dev/test backend) serialises writers with a process-wide lock and
  treats ``select_for_update`` as a no-op, so running there would be a FALSE
  green; it is SKIPPED instead.

Coverage:

* C1 — two concurrent ``create_housekeeping_task`` for the SAME room: exactly
  ONE wins, the other raises ``DuplicateActiveTask``; exactly one active task
  survives; neither thread deadlocks.
* C2 — the LOSING create's transaction stays usable: after catching the
  conflict it performs a subsequent read AND write on its own connection with
  no "current transaction is aborted" error (the savepoint scoping inside
  ``create_housekeeping_task`` is not left poisoning the outer transaction).
* C3 — a normal ``create_housekeeping_task`` (``on_active="raise"``) racing an
  automatic caller (``on_active="skip"``, the check-out / room-move style):
  never a duplicate active task, and the skip caller NEVER raises (it returns
  the created task if it won the lock, else ``None``).
* C4 — the room-status race: one worker completes a cleaning task and RELEASES
  the room to ``available`` while another concurrently opens a BLOCKING
  maintenance request on the SAME room. The room row-lock serialises them, so
  the final state is consistent — the room is NEVER ``available`` while an open
  blocking maintenance request exists.
"""
from __future__ import annotations

import threading

from django.db import connection, connections
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.common.exceptions import DuplicateActiveTask, RoomBlockedByMaintenance
from apps.operations.models import (
    HousekeepingStatus,
    HousekeepingTask,
    MaintenanceCategory,
    MaintenanceRequest,
    OperationPriority,
    RoomBlockStatus,
)
from apps.operations.services import (
    ACTIVE_HK_STATUSES,
    change_housekeeping_status,
    complete_housekeeping_task,
    create_housekeeping_task,
    create_maintenance_request,
    room_has_blocking_maintenance,
)
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

_PG_SKIP = (
    "row-lock/partial-unique concurrency requires PostgreSQL: real "
    "multi-connection write contention + SELECT ... FOR UPDATE row locking are "
    "only meaningful on PostgreSQL (the production database). SQLite serialises "
    "writers with a process-wide lock and treats select_for_update as a no-op; "
    "skipped here to avoid a false green."
)

#: Join timeout — a deadlocked / hung worker never finishes within this bound,
#: so the ``is_alive()`` assertion catches it instead of the suite hanging.
_JOIN_TIMEOUT = 30


class _OperationsConcurrencyBase(TransactionTestCase):
    """Commits the shared hotel/room/user so both worker connections see them."""

    def _seed_hotel_room_user(self, *, slug):
        self.hotel = Hotel.objects.create(
            name="Hotel", slug=slug, status=HotelStatus.ACTIVE
        )
        self.user = User.objects.create_user(
            email=f"{slug}@x.com", password="StrongPass!234", full_name="Ops"
        )
        HotelMembership.objects.create(
            user=self.user,
            hotel=self.hotel,
            membership_type=MembershipType.MANAGER,
            is_active=True,
        )
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3,
        )
        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        # DIRTY = a just-vacated, vacant, cleanable room (no in-house stay).
        self.room = Room.objects.create(
            hotel=self.hotel, floor=floor, room_type=self.rtype,
            number="101", status=RoomStatus.DIRTY,
        )

    def _active_task_count(self):
        return HousekeepingTask.objects.filter(
            hotel=self.hotel, room=self.room, status__in=ACTIVE_HK_STATUSES
        ).count()

    def _run(self, threads):
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=_JOIN_TIMEOUT)
        for t in threads:
            self.assertFalse(
                t.is_alive(), "a worker thread deadlocked or timed out"
            )

    def _assert_no_unexpected(self, results):
        for r in results:
            self.assertFalse(
                str(r).startswith("unexpected:"),
                f"an unexpected error escaped a worker: {r}",
            )


class HousekeepingCreateConcurrencyTests(_OperationsConcurrencyBase):
    """C1 / C2 / C3 — concurrent housekeeping-task creation on the SAME room."""

    def setUp(self):
        self._seed_hotel_room_user(slug="conc-hk")

    # -- workers ------------------------------------------------------------
    def _create_worker(self, barrier, results, index, *, on_active):
        """One worker: its OWN connection, ONE ``create_housekeeping_task`` for
        the shared room. Records a plain string outcome; a leaked unexpected
        error is captured (never silently swallowed)."""
        try:
            barrier.wait(timeout=15)
            try:
                task = create_housekeeping_task(
                    self.hotel,
                    user=self.user,
                    room=self.room,
                    priority=OperationPriority.NORMAL,
                    on_active=on_active,
                )
                results[index] = "created" if task is not None else "skipped_none"
            except DuplicateActiveTask:
                results[index] = "duplicate"
        except Exception as exc:  # noqa: BLE001 - a leaked error must be visible
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def _create_then_followup_worker(self, barrier, results, followups, index):
        """C2 worker: create; on ``DuplicateActiveTask`` prove the connection is
        NOT poisoned by immediately doing a READ and a WRITE on the SAME
        connection (a "current transaction is aborted" would raise here)."""
        try:
            barrier.wait(timeout=15)
            try:
                task = create_housekeeping_task(
                    self.hotel,
                    user=self.user,
                    room=self.room,
                    priority=OperationPriority.NORMAL,
                )
                results[index] = "created" if task is not None else "skipped_none"
            except DuplicateActiveTask:
                results[index] = "duplicate"
                # READ on the same connection (should see the winner's task).
                active_count = self._active_task_count()
                # WRITE on the same connection (a fresh, independent txn).
                req = create_maintenance_request(
                    self.hotel,
                    user=self.user,
                    room=self.room,
                    title="post-conflict probe",
                    category=MaintenanceCategory.OTHER,
                    priority=OperationPriority.NORMAL,
                    affects_room_availability=False,
                    room_block_status=RoomBlockStatus.NONE,
                )
                followups[index] = (
                    f"read_ok:{active_count};write_ok:{req.pk is not None}"
                )
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
            followups[index] = f"followup_failed:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    # -- C1 -----------------------------------------------------------------
    def test_c1_two_concurrent_creates_leave_one_active_task(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results = ["", ""]
        threads = [
            threading.Thread(
                target=self._create_worker,
                args=(barrier, results, i),
                kwargs={"on_active": "raise"},
            )
            for i in range(2)
        ]
        self._run(threads)

        self._assert_no_unexpected(results)
        # Exactly one winner and one duplicate-rejected loser.
        self.assertEqual(sorted(results), ["created", "duplicate"], results)
        # Exactly ONE active task survives for the room.
        self.assertEqual(self._active_task_count(), 1)

    # -- C2 -----------------------------------------------------------------
    def test_c2_losing_transaction_stays_usable(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results = ["", ""]
        followups = ["", ""]
        threads = [
            threading.Thread(
                target=self._create_then_followup_worker,
                args=(barrier, results, followups, i),
            )
            for i in range(2)
        ]
        self._run(threads)

        self._assert_no_unexpected(results)
        self.assertEqual(sorted(results), ["created", "duplicate"], results)

        # The loser caught DuplicateActiveTask and then successfully READ (saw
        # the one committed active task) AND WROTE (created a maintenance
        # request) on the very same connection — proof the transaction was not
        # left aborted.
        loser = results.index("duplicate")
        self.assertEqual(
            followups[loser], "read_ok:1;write_ok:True",
            f"loser's post-conflict read/write did not both succeed: {followups}",
        )
        # Exactly one active HK task, and exactly the one probe maintenance
        # request the loser wrote afterwards.
        self.assertEqual(self._active_task_count(), 1)
        self.assertEqual(
            MaintenanceRequest.objects.filter(
                hotel=self.hotel, room=self.room
            ).count(),
            1,
        )

    # -- C3 -----------------------------------------------------------------
    def test_c3_normal_create_versus_skip_autocaller(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        # index 0 = normal (on_active="raise"); index 1 = automatic (skip).
        results = ["", ""]
        threads = [
            threading.Thread(
                target=self._create_worker,
                args=(barrier, results, 0),
                kwargs={"on_active": "raise"},
            ),
            threading.Thread(
                target=self._create_worker,
                args=(barrier, results, 1),
                kwargs={"on_active": "skip"},
            ),
        ]
        self._run(threads)

        self._assert_no_unexpected(results)
        normal_outcome, skip_outcome = results

        # The automatic (skip) caller must NEVER raise: it either won the lock
        # and created the task, or lost and returned None — but never a 409.
        self.assertIn(
            skip_outcome, ("created", "skipped_none"),
            f"the skip auto-caller must never raise: {results}",
        )
        self.assertIn(normal_outcome, ("created", "duplicate"), results)
        # Exactly one active task — no duplicate under contention.
        self.assertEqual(self._active_task_count(), 1)
        # Only two consistent race outcomes are possible: either the normal
        # caller won (and the skip caller returned None), or the skip caller won
        # (and the normal caller got the duplicate 409).
        self.assertIn(
            (normal_outcome, skip_outcome),
            {("created", "skipped_none"), ("duplicate", "created")},
            results,
        )


class RoomStatusReleaseVsBlockConcurrencyTests(_OperationsConcurrencyBase):
    """C4 — a room RELEASE (cleaning completion) racing a BLOCKING maintenance
    request on the same room. The room row-lock serialises the two writers so
    the final state is consistent: never ``available`` with an open block."""

    def setUp(self):
        self._seed_hotel_room_user(slug="conc-room")
        # Seed a startable/completable cleaning task and START it so the vacant,
        # cleanable (DIRTY) room flips to CLEANING — the state from which a
        # completion-with-release actually transitions the room to available.
        self.task = create_housekeeping_task(
            self.hotel,
            user=self.user,
            room=self.room,
            priority=OperationPriority.NORMAL,
        )
        change_housekeeping_status(
            self.task,
            new_status=HousekeepingStatus.IN_PROGRESS,
            user=self.user,
        )
        self.room.refresh_from_db()

    # -- workers ------------------------------------------------------------
    def _complete_release_worker(self, barrier, results, index):
        """Complete the cleaning task AND release the room to available. If the
        blocking maintenance request won the room lock first, the releasability
        re-check raises ``RoomBlockedByMaintenance`` and the whole atomic block
        rolls back — an EXPECTED outcome, not an error."""
        try:
            barrier.wait(timeout=15)
            try:
                complete_housekeeping_task(
                    self.task,
                    user=self.user,
                    mark_room_available=True,
                )
                results[index] = "released"
            except RoomBlockedByMaintenance:
                results[index] = "blocked_by_maintenance"
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def _open_block_worker(self, barrier, results, index):
        """Open a blocking maintenance request on the SAME room (moves the room
        to ``maintenance`` via the row-locked ``_apply_room_block``)."""
        try:
            barrier.wait(timeout=15)
            create_maintenance_request(
                self.hotel,
                user=self.user,
                room=self.room,
                title="Emergency block",
                category=MaintenanceCategory.SAFETY,
                priority=OperationPriority.URGENT,
                affects_room_availability=True,
                room_block_status=RoomBlockStatus.MAINTENANCE,
            )
            results[index] = "blocked"
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def test_c4_release_never_wins_over_open_block(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results = ["", ""]
        threads = [
            threading.Thread(
                target=self._complete_release_worker, args=(barrier, results, 0)
            ),
            threading.Thread(
                target=self._open_block_worker, args=(barrier, results, 1)
            ),
        ]
        self._run(threads)

        self._assert_no_unexpected(results)
        # The release worker either released (it won the lock first, before the
        # block committed) or was refused because the block was already applied.
        self.assertIn(results[0], ("released", "blocked_by_maintenance"), results)
        # The block worker always succeeds in opening its request.
        self.assertEqual(results[1], "blocked", results)

        self.room.refresh_from_db()
        open_block_exists = room_has_blocking_maintenance(self.room)

        # THE INVARIANT: the room is NEVER available while an open blocking
        # maintenance request exists. The row-lock serialisation guarantees the
        # block is the last authoritative writer whenever it commits.
        if open_block_exists:
            self.assertNotEqual(
                self.room.status, RoomStatus.AVAILABLE,
                "room ended up AVAILABLE while an open blocking maintenance "
                "request exists — the row-lock failed to serialise the writers",
            )

        # Concretely, the block is always created and open, so the room must end
        # in a blocked status (maintenance/out-of-service), never available.
        self.assertTrue(
            open_block_exists,
            "the blocking maintenance request must exist and stay open",
        )
        self.assertIn(
            self.room.status,
            (RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE),
            f"room must be blocked, got {self.room.status}",
        )
        # Exactly one maintenance request (the block) — no phantom duplicates.
        self.assertEqual(
            MaintenanceRequest.objects.filter(
                hotel=self.hotel, room=self.room
            ).count(),
            1,
        )
