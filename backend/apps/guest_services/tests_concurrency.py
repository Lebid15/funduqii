"""GUEST-FOLIO-EXTRA-SERVICES-CLOSURE — the real races (#10/#5, PostgreSQL-only).

Two two-connection proofs live here:

1. :class:`AddServiceVsCheckoutRaceTests` — add-service vs check-out.
2. :class:`SameKeyIdempotencyRaceTests` — two CONCURRENT adds sharing one
   idempotency key (A6), the only way to actually execute the post-lock replay
   path; sequentially the fast path always wins first and that code never runs.

Both are meaningless on SQLite (no real multi-connection row locking) and skip
there rather than report a false green.

--- the check-out race (#10) -------------------------------------------------

A REAL two-connection proof that adding a guest service and checking the stay out
are ATOMIC with respect to each other. Both operations lock the STAY row FIRST
(``select_for_update(of=("self",))``) in the SAME order, so they serialize on that
row and can never deadlock. The invariant proved: exactly ONE of two outcomes
occurs, never a lost/orphan charge and never a charge stranded on a closed folio.

* ADD wins the stay lock: the service charge is posted BEFORE check-out runs, so
  the folio balance is non-zero and check-out is BLOCKED
  (``FolioBalanceOutstanding``) — the charge is visible on the still-open folio.
* CHECK-OUT wins the stay lock: the zero-balance folio closes and the stay leaves
  in-house, so the later add refuses with ``StayNotInHouse`` and creates NOTHING.

Meaningful only on PostgreSQL (real multi-connection row locking); SQLite
serialises writers with a process-wide lock and has different threading semantics,
so it is SKIPPED there to avoid a false green.
"""
from __future__ import annotations

import threading
from datetime import timedelta

from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.finance.constants import ChargeSource
from apps.finance.models import Folio, FolioCharge, FolioStatus, PostingStatus
from apps.finance.services import ensure_stay_folio
from apps.guest_services.models import GuestExtraService, GuestServicePosting, PricingMode
from apps.guest_services.services import (
    add_guest_service_to_stay,
    build_request_fingerprint,
)
from apps.guests.models import Guest
from apps.rooms.models import Floor, Room, RoomType
from apps.stays.models import Stay, StayRatePeriod, StayStatus
from apps.stays.services import CheckOutService
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

_PG_SKIP = (
    "The real two-connection add-service vs check-out race is only meaningful on "
    "PostgreSQL (row locking + savepoint rollback). SQLite serialises writers with "
    "a process-wide lock and has different threading semantics; skipped to avoid a "
    "false green on SQLite."
)

_PG_SKIP_IDEMPOTENCY = (
    "The same-key idempotency race needs two REAL concurrent connections blocking "
    "on one stay row (PostgreSQL). SQLite serialises writers process-wide, so the "
    "two adds would simply run in sequence and the fast path would always win — "
    "exactly the false green this test exists to eliminate."
)


class AddServiceVsCheckoutRaceTests(TransactionTestCase):
    """TransactionTestCase COMMITS setUp so the two worker connections both see the
    committed hotel/stay/folio/catalog rows."""

    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Hotel", slug="gs-race", status=HotelStatus.ACTIVE
        )
        self.user = User.objects.create_user(
            email="gsrace@x.com", password="StrongPass!234", full_name="Race"
        )
        HotelMembership.objects.create(
            user=self.user, hotel=self.hotel,
            membership_type=MembershipType.MANAGER, is_active=True,
        )
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3, base_rate="100.00",
        )
        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        self.room = Room.objects.create(
            hotel=self.hotel, floor=floor, room_type=self.rtype, number="101"
        )
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Guest One")
        self.stay = Stay.objects.create(
            hotel=self.hotel, room=self.room, primary_guest=self.guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=timezone.localdate(),
            planned_check_out_date=timezone.localdate() + timedelta(days=2),
            actual_check_in_at=timezone.now(),
        )
        # A rate period covering the stay (no nights are due on the check-in day,
        # so no room charges are posted and the folio balance starts at zero).
        StayRatePeriod.objects.create(
            hotel=self.hotel, stay=self.stay,
            start_date=self.stay.planned_check_in_date,
            end_date=self.stay.planned_check_out_date,
            nightly_rate="100.00", currency="USD", source="booking",
        )
        self.folio = ensure_stay_folio(self.stay, user=self.user)
        self.service = GuestExtraService.objects.create(
            hotel=self.hotel, name="Laundry", category="laundry",
            unit_price="50.00", currency="USD", tax_rate="0.00",
            pricing_mode=PricingMode.FIXED,
        )

    def _add_worker(self, barrier, results, index):
        try:
            barrier.wait(timeout=15)
            fp = build_request_fingerprint(
                self.service, stay_id=self.stay.id, quantity=1
            )
            add_guest_service_to_stay(
                self.hotel, stay=self.stay, service=self.service, quantity=1,
                user=self.user, idempotency_key="race-add", request_fingerprint=fp,
            )
            results[index] = "added"
        except Exception as exc:  # noqa: BLE001 - a leaked error must be visible
            results[index] = f"{type(exc).__name__}"
        finally:
            connections["default"].close()

    def _checkout_worker(self, barrier, results, index):
        try:
            barrier.wait(timeout=15)
            CheckOutService.execute(
                self.stay, checkout_reason="race test", user=self.user
            )
            results[index] = "checked_out"
        except Exception as exc:  # noqa: BLE001
            results[index] = f"{type(exc).__name__}"
        finally:
            connections["default"].close()

    def test_add_and_checkout_are_atomic(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results = ["", ""]
        threads = [
            threading.Thread(target=self._add_worker, args=(barrier, results, 0)),
            threading.Thread(target=self._checkout_worker, args=(barrier, results, 1)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for t in threads:
            self.assertFalse(t.is_alive(), "a worker deadlocked or timed out")

        self.stay.refresh_from_db()
        postings = GuestServicePosting.objects.filter(stay=self.stay).count()
        svc_charges = FolioCharge.objects.filter(
            folio=self.folio, source=ChargeSource.GUEST_EXTRA_SERVICE,
            status=PostingStatus.POSTED,
        ).count()
        folio = Folio.objects.get(pk=self.folio.pk)

        add_outcome, checkout_outcome = results[0], results[1]

        if self.stay.status == StayStatus.CHECKED_OUT:
            # CHECK-OUT won: the add must have refused with no side effect, and the
            # folio closed at a zero balance (no stranded/lost charge).
            self.assertEqual(checkout_outcome, "checked_out", results)
            self.assertEqual(add_outcome, "StayNotInHouse", results)
            self.assertEqual(postings, 0)
            self.assertEqual(svc_charges, 0)
            self.assertEqual(folio.status, FolioStatus.CLOSED)
        else:
            # ADD won: the charge is on the still-open folio and check-out was
            # BLOCKED by the outstanding balance (the charge is never lost).
            self.assertEqual(self.stay.status, StayStatus.IN_HOUSE, results)
            self.assertEqual(add_outcome, "added", results)
            self.assertEqual(checkout_outcome, "FolioBalanceOutstanding", results)
            self.assertEqual(postings, 1)
            self.assertEqual(svc_charges, 1)
            self.assertEqual(folio.status, FolioStatus.OPEN)

        # NEVER both-succeed-with-lost-charge.
        self.assertFalse(
            self.stay.status == StayStatus.CHECKED_OUT and postings == 1,
            "both add and check-out succeeded — a lost/stranded charge",
        )


class SameKeyIdempotencyRaceTests(TransactionTestCase):
    """A6 — TWO CONCURRENT adds with the SAME idempotency_key and SAME fingerprint.

    SCOPE — read this before trusting it: this test covers the POST-LOCK REPLAY
    RE-CHECK, and ONLY that. It does NOT execute the
    ``IntegrityError -> IdempotencyKeyConflict`` savepoint; both workers here
    share one stay, so they serialize on that stay's row and the loser returns
    from the re-check before it can ever reach the INSERT. Deleting the savepoint
    entirely would leave this test green. That branch is covered separately by
    ``CrossStayKeyReuseRaceTests`` below, where the workers touch DIFFERENT stays
    and therefore never serialize.

    Why this test had to exist: run sequentially, the fast-path lookup at the top
    of the service always finds the first posting and returns before the re-check
    can execute, so "idempotency is safe under concurrency" was asserted by
    nothing at all.

    Here both workers pass the fast path (neither has committed yet), then
    serialize on the STAY row. The loser resumes AFTER the winner commits and —
    under PostgreSQL's default READ COMMITTED isolation, which this project does
    not override — its post-lock re-check sees the winner's committed posting and
    returns it. INVARIANT: exactly ONE FolioCharge and exactly ONE
    GuestServicePosting, both workers handed the SAME posting, no deadlock, and
    no exception escapes at all (identical fingerprints are a legal replay, never
    a conflict).
    """

    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Hotel", slug="gs-idem-race", status=HotelStatus.ACTIVE
        )
        self.user = User.objects.create_user(
            email="gsidem@x.com", password="StrongPass!234", full_name="Idem"
        )
        HotelMembership.objects.create(
            user=self.user, hotel=self.hotel,
            membership_type=MembershipType.MANAGER, is_active=True,
        )
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3, base_rate="100.00",
        )
        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        self.room = Room.objects.create(
            hotel=self.hotel, floor=floor, room_type=self.rtype, number="101"
        )
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Guest One")
        self.stay = Stay.objects.create(
            hotel=self.hotel, room=self.room, primary_guest=self.guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=timezone.localdate(),
            planned_check_out_date=timezone.localdate() + timedelta(days=2),
            actual_check_in_at=timezone.now(),
        )
        StayRatePeriod.objects.create(
            hotel=self.hotel, stay=self.stay,
            start_date=self.stay.planned_check_in_date,
            end_date=self.stay.planned_check_out_date,
            nightly_rate="100.00", currency="USD", source="booking",
        )
        self.folio = ensure_stay_folio(self.stay, user=self.user)
        self.service = GuestExtraService.objects.create(
            hotel=self.hotel, name="Laundry", category="laundry",
            unit_price="50.00", currency="USD", tax_rate="0.00",
            pricing_mode=PricingMode.FIXED,
        )

    def _add_worker(self, barrier, results, index):
        """Calls the REAL production service on this thread's own connection."""
        try:
            fp = build_request_fingerprint(
                self.service, stay_id=self.stay.id, quantity=1
            )
            # Release both threads at the same instant so they genuinely contend.
            barrier.wait(timeout=15)
            posting = add_guest_service_to_stay(
                self.hotel, stay=self.stay, service=self.service, quantity=1,
                user=self.user, idempotency_key="same-key-race",
                request_fingerprint=fp,
            )
            results[index] = ("ok", posting.pk)
        except Exception as exc:  # noqa: BLE001 - a leaked error must be visible
            results[index] = (type(exc).__name__, str(exc))
        finally:
            connections["default"].close()

    def test_two_concurrent_adds_same_key_create_exactly_one_charge(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP_IDEMPOTENCY)

        barrier = threading.Barrier(2)
        results = [None, None]
        threads = [
            threading.Thread(target=self._add_worker, args=(barrier, results, 0)),
            threading.Thread(target=self._add_worker, args=(barrier, results, 1)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # No deadlock / no hang.
        for t in threads:
            self.assertFalse(t.is_alive(), f"a worker deadlocked or timed out: {results}")

        # No unexpected exception type escaped — with identical fingerprints this
        # is a legal replay, so BOTH calls must succeed.
        for outcome in results:
            self.assertIsNotNone(outcome, f"a worker produced no result: {results}")
            self.assertEqual(outcome[0], "ok", f"unexpected failure: {results}")

        # THE INVARIANT: one charge, one posting — never two, never zero.
        postings = GuestServicePosting.objects.filter(
            hotel=self.hotel, idempotency_key="same-key-race"
        )
        self.assertEqual(postings.count(), 1, f"idempotency lost: {results}")
        self.assertEqual(
            GuestServicePosting.objects.filter(stay=self.stay).count(), 1, results
        )
        svc_charges = FolioCharge.objects.filter(
            folio=self.folio, source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        self.assertEqual(
            svc_charges.count(), 1,
            f"a duplicate or orphan charge survived the race: {results}",
        )
        # Both workers were handed the SAME posting (the loser replayed, it did
        # not create a second one), and that charge is the posting's own charge.
        posting = postings.get()
        self.assertEqual(results[0][1], posting.pk, results)
        self.assertEqual(results[1][1], posting.pk, results)
        self.assertEqual(svc_charges.get().pk, posting.folio_charge_id)
        # The charge is POSTED on the still-open folio (no rolled-back remnant).
        self.assertEqual(svc_charges.get().status, PostingStatus.POSTED)
        self.assertEqual(
            Folio.objects.get(pk=self.folio.pk).status, FolioStatus.OPEN
        )


class CrossStayKeyReuseRaceTests(TransactionTestCase):
    """The ``IntegrityError -> IdempotencyKeyConflict`` savepoint — the ONLY test
    that actually executes it.

    ``SameKeyIdempotencyRaceTests`` above cannot: its workers share a stay, so
    they serialize on that row and the loser returns from the post-lock re-check
    before reaching the INSERT. An independent review established that deleting
    the savepoint would leave that test green — the branch had ZERO coverage
    while a docstring claimed otherwise.

    Here the same key is reused across TWO DIFFERENT stays. The workers lock
    different stay rows, so they never serialize: BOTH clear the re-check (neither
    has committed) and BOTH reach the posting INSERT. The partial unique
    constraint on ``(hotel, idempotency_key)`` then fires for the loser, the
    savepoint catches the ``IntegrityError`` and translates it into a clean
    ``IdempotencyKeyConflict`` (HTTP 409).

    THE INVARIANT THAT MATTERS: the loser must leave NOTHING behind. It had
    already created its own ``FolioCharge`` before the posting INSERT failed, so
    if the savepoint did not roll that back, a guest would be charged for a
    service that has no posting and no audit trail — money moved with no record.
    """

    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Hotel", slug="gs-xstay-race", status=HotelStatus.ACTIVE
        )
        self.user = User.objects.create_user(
            email="gsxstay@x.com", password="StrongPass!234", full_name="XStay"
        )
        HotelMembership.objects.create(
            user=self.user, hotel=self.hotel,
            membership_type=MembershipType.MANAGER, is_active=True,
        )
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3, base_rate="100.00",
        )
        self.floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        self.service = GuestExtraService.objects.create(
            hotel=self.hotel, name="Laundry", category="laundry",
            unit_price="50.00", currency="USD", tax_rate="0.00",
            pricing_mode=PricingMode.FIXED,
        )
        self.stays = [self._make_stay(101), self._make_stay(102)]
        self.folios = [ensure_stay_folio(s, user=self.user) for s in self.stays]

    def _make_stay(self, number):
        room = Room.objects.create(
            hotel=self.hotel, floor=self.floor, room_type=self.rtype,
            number=str(number),
        )
        guest = Guest.objects.create(hotel=self.hotel, full_name=f"Guest {number}")
        stay = Stay.objects.create(
            hotel=self.hotel, room=room, primary_guest=guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=timezone.localdate(),
            planned_check_out_date=timezone.localdate() + timedelta(days=2),
            actual_check_in_at=timezone.now(),
        )
        StayRatePeriod.objects.create(
            hotel=self.hotel, stay=stay,
            start_date=stay.planned_check_in_date,
            end_date=stay.planned_check_out_date,
            nightly_rate="100.00", currency="USD", source="booking",
        )
        return stay

    def _add_worker(self, barrier, results, index):
        stay = self.stays[index]
        try:
            fp = build_request_fingerprint(
                self.service, stay_id=stay.id, quantity=1
            )
            barrier.wait(timeout=15)
            posting = add_guest_service_to_stay(
                self.hotel, stay=stay, service=self.service, quantity=1,
                user=self.user, idempotency_key="reused-across-stays",
                request_fingerprint=fp,
            )
            results[index] = ("ok", posting.pk)
        except Exception as exc:  # noqa: BLE001 - a leaked error must be visible
            results[index] = (type(exc).__name__, str(exc))
        finally:
            connections["default"].close()

    def test_key_reused_across_stays_yields_one_posting_and_no_orphan_charge(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP_IDEMPOTENCY)

        barrier = threading.Barrier(2)
        results = [None, None]
        threads = [
            threading.Thread(target=self._add_worker, args=(barrier, results, 0)),
            threading.Thread(target=self._add_worker, args=(barrier, results, 1)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for t in threads:
            self.assertFalse(t.is_alive(), f"a worker deadlocked: {results}")
        for outcome in results:
            self.assertIsNotNone(outcome, f"a worker produced no result: {results}")

        # Exactly one winner and one clean 409 — never two winners, and never a
        # raw IntegrityError leaking out of the service.
        kinds = sorted(o[0] for o in results)
        self.assertEqual(
            kinds, ["IdempotencyKeyConflict", "ok"],
            f"expected one winner + one clean conflict, got: {results}",
        )

        # One posting for the key, across BOTH stays.
        postings = GuestServicePosting.objects.filter(
            hotel=self.hotel, idempotency_key="reused-across-stays"
        )
        self.assertEqual(postings.count(), 1, f"idempotency lost: {results}")

        # THE POINT: the loser rolled its own charge back. Exactly ONE service
        # charge exists across BOTH folios — no orphan on the losing stay.
        charges = FolioCharge.objects.filter(
            folio__in=self.folios, source=ChargeSource.GUEST_EXTRA_SERVICE
        )
        self.assertEqual(
            charges.count(), 1,
            f"the loser left an orphan charge behind — a guest was charged with "
            f"no posting and no audit trail: {results}",
        )
        self.assertEqual(charges.get().pk, postings.get().folio_charge_id)
