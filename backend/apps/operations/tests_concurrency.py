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
* C5 — two reports confirming a match to the SAME found item concurrently:
  exactly ONE wins, the other raises ``FoundItemAlreadyMatched`` (backed by the
  partial-unique ``uniq_matched_found_item_active_report``); at most one active
  match survives.
* C6 — a ``confirm_match`` racing a concurrent standalone dispose of the found
  item: the item row-lock serialises them so the two can NEVER both commit —
  either the dispose wins (item disposed, match refused ``FoundItemNotMatchable``)
  or the match wins (report matched, dispose refused ``FoundItemActivelyMatched``
  by the reverse guard). A report is NEVER left dangling as matched to a disposed
  item.
* C7 — a handover racing a concurrent unmatch on the SAME matched report: the
  report row-lock serialises them, so the report ends EITHER returned OR
  searching (never both, never a half-applied state).
"""
from __future__ import annotations

import threading

from django.db import connection, connections
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.common.exceptions import (
    DuplicateActiveTask,
    FoundItemActivelyMatched,
    FoundItemAlreadyMatched,
    FoundItemNotMatchable,
    InvalidOperationStatusTransition,
    RoomBlockedByMaintenance,
)
from apps.operations.models import (
    HousekeepingStatus,
    HousekeepingTask,
    LostFoundCategory,
    LostFoundItem,
    LostFoundStatus,
    LostReport,
    LostReportStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    OperationPriority,
    RoomBlockStatus,
)
from apps.operations.services import (
    ACTIVE_HK_STATUSES,
    change_housekeeping_status,
    complete_housekeeping_task,
    confirm_match,
    create_housekeeping_task,
    create_lost_found_item,
    create_lost_report,
    create_maintenance_request,
    dispose_lost_found_item,
    hand_over_matched_report,
    room_has_blocking_maintenance,
    unmatch,
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


class LostReportMatchConcurrencyTests(_OperationsConcurrencyBase):
    """C5 / C6 — concurrent SAFE-MATCH contention on a single found item."""

    def setUp(self):
        self._seed_hotel_room_user(slug="conc-lr-match")
        # One found item both reports will race to claim, and two OPEN reports.
        self.item = create_lost_found_item(
            self.hotel, user=self.user, title="Black wallet",
            category=LostFoundCategory.OTHER, status=LostFoundStatus.STORED,
        )
        self.report_a = create_lost_report(
            self.hotel, user=self.user, reporter_name="Reporter A"
        )
        self.report_b = create_lost_report(
            self.hotel, user=self.user, reporter_name="Reporter B"
        )

    def _match_worker(self, barrier, results, index, report):
        try:
            barrier.wait(timeout=15)
            try:
                confirm_match(report, self.item, user=self.user)
                results[index] = "matched"
            except FoundItemAlreadyMatched:
                results[index] = "already_matched"
            except FoundItemNotMatchable:
                results[index] = "not_matchable"
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def _dispose_worker(self, barrier, results, index):
        try:
            barrier.wait(timeout=15)
            try:
                dispose_lost_found_item(self.item, reason="damaged", user=self.user)
                results[index] = "disposed"
            except FoundItemActivelyMatched:
                # The match won the item lock first → the item is now actively
                # matched and the reverse guard refuses this standalone dispose.
                results[index] = "actively_matched"
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    # -- C5 -----------------------------------------------------------------
    def test_c5_two_reports_one_item_only_one_wins(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results = ["", ""]
        threads = [
            threading.Thread(
                target=self._match_worker,
                args=(barrier, results, 0, self.report_a),
            ),
            threading.Thread(
                target=self._match_worker,
                args=(barrier, results, 1, self.report_b),
            ),
        ]
        self._run(threads)

        self._assert_no_unexpected(results)
        # Exactly one winner; the loser is refused by the partial-unique belt.
        self.assertEqual(sorted(results), ["already_matched", "matched"], results)
        # At most ONE report is actively matched to the item.
        self.assertEqual(
            LostReport.objects.filter(
                hotel=self.hotel,
                matched_found_item=self.item,
                status=LostReportStatus.MATCHED,
            ).count(),
            1,
        )
        # The found item is untouched (still STORED).
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, LostFoundStatus.STORED)

    # -- C6 -----------------------------------------------------------------
    def test_c6_match_versus_concurrent_dispose(self):
        """The item row-lock SERIALISES a match against a concurrent standalone
        dispose so the two can NEVER both commit — no deadlock, no torn state, no
        dangling match. Whichever writer wins the item lock, the outcome is one of
        exactly two consistent shapes:

        * dispose won the lock  → it disposed a still-unmatched item; the match's
          ``SELECT ... FOR UPDATE`` then reads a DISPOSED item and refuses cleanly
          (``FoundItemNotMatchable``); the report is left OPEN with no link.
        * match won the lock     → the report is matched to the (still-STORED)
          item; the concurrent dispose's re-read under the lock sees the ACTIVE
          match and is refused by the reverse guard (``FoundItemActivelyMatched``);
          the item is left STORED — never disposed while a report holds it.
        """
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        # index 0 = match; index 1 = dispose.
        results = ["", ""]
        threads = [
            threading.Thread(
                target=self._match_worker,
                args=(barrier, results, 0, self.report_a),
            ),
            threading.Thread(
                target=self._dispose_worker, args=(barrier, results, 1)
            ),
        ]
        self._run(threads)

        self._assert_no_unexpected(results)
        # Exactly one of two consistent race outcomes — never both mutations.
        self.assertIn(
            (results[0], results[1]),
            {("matched", "actively_matched"), ("not_matchable", "disposed")},
            results,
        )

        self.report_a.refresh_from_db()
        self.item.refresh_from_db()
        if results[0] == "matched":
            # Match won → dispose refused, item stays STORED, report matched.
            self.assertEqual(self.item.status, LostFoundStatus.STORED)
            self.assertEqual(self.report_a.status, LostReportStatus.MATCHED)
            self.assertEqual(self.report_a.matched_found_item_id, self.item.id)
        else:
            # Dispose won → match refused, item disposed, report untouched.
            self.assertEqual(self.item.status, LostFoundStatus.DISPOSED)
            self.assertEqual(self.report_a.status, LostReportStatus.OPEN)
            self.assertIsNone(self.report_a.matched_found_item_id)

        # THE INVARIANT: a report is NEVER left dangling as matched to a DISPOSED
        # item — an actively-matched item is either still holdable, or there is no
        # active match at all.
        dangling = (
            self.item.status == LostFoundStatus.DISPOSED
            and LostReport.objects.filter(
                hotel=self.hotel,
                matched_found_item=self.item,
                status=LostReportStatus.MATCHED,
            ).exists()
        )
        self.assertFalse(dangling, "a report is matched to a DISPOSED item")


class LostReportHandoverConcurrencyTests(_OperationsConcurrencyBase):
    """C7 — a handover racing a concurrent unmatch on the same matched report."""

    def setUp(self):
        self._seed_hotel_room_user(slug="conc-lr-handover")
        self.item = create_lost_found_item(
            self.hotel, user=self.user, title="Black wallet",
            category=LostFoundCategory.OTHER, status=LostFoundStatus.STORED,
        )
        self.report = create_lost_report(
            self.hotel, user=self.user, reporter_name="Reporter"
        )
        confirm_match(self.report, self.item, user=self.user)

    def _handover_worker(self, barrier, results, index):
        try:
            barrier.wait(timeout=15)
            try:
                hand_over_matched_report(
                    self.report,
                    user=self.user,
                    recipient_name="Owner",
                    recipient_phone="0555",
                )
                results[index] = "returned"
            except InvalidOperationStatusTransition:
                # The unmatch won the report lock first → no longer matched.
                results[index] = "not_matched"
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def _unmatch_worker(self, barrier, results, index):
        try:
            barrier.wait(timeout=15)
            try:
                unmatch(self.report, reason="wrong item", user=self.user)
                results[index] = "unmatched"
            except InvalidOperationStatusTransition:
                # The handover won the report lock first → already returned.
                results[index] = "not_matched"
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def test_c7_handover_versus_concurrent_unmatch(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results = ["", ""]
        threads = [
            threading.Thread(
                target=self._handover_worker, args=(barrier, results, 0)
            ),
            threading.Thread(
                target=self._unmatch_worker, args=(barrier, results, 1)
            ),
        ]
        self._run(threads)

        self._assert_no_unexpected(results)
        # Exactly ONE of the two mutations applied — the report row-lock serialises
        # them, so the other sees a non-matched report and is refused.
        self.report.refresh_from_db()
        self.item.refresh_from_db()
        if results[0] == "returned":
            # Handover won: report returned, item returned, unmatch refused.
            self.assertEqual(results[1], "not_matched", results)
            self.assertEqual(self.report.status, LostReportStatus.RETURNED)
            self.assertEqual(self.item.status, LostFoundStatus.RETURNED)
        else:
            # Unmatch won: report searching + link cleared, handover refused; the
            # item is never returned by a rolled-back handover.
            self.assertEqual(results[1], "unmatched", results)
            self.assertEqual(results[0], "not_matched", results)
            self.assertEqual(self.report.status, LostReportStatus.SEARCHING)
            self.assertIsNone(self.report.matched_found_item_id)
            self.assertEqual(self.item.status, LostFoundStatus.STORED)
