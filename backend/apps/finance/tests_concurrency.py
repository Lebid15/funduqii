"""STAYS PR #43 — ITEM 6 (PostgreSQL verification).

A REAL two-connection concurrency proof for the partial unique index
``uniq_posted_room_night_per_folio`` on ``FolioCharge (folio, room_night)
WHERE status='posted' AND room_night IS NOT NULL`` (migration finance/0009).

Two worker threads, each on its OWN database connection and inside its OWN
transaction, attempt to post the SAME room night on the SAME folio. The
partial unique index is the concurrency backstop: exactly one INSERT wins,
the loser gets an ``IntegrityError`` that its SAVEPOINT rolls back cleanly
(``finance.services.add_charge`` is ``@transaction.atomic`` -> a savepoint
when nested), leaving the loser's OUTER transaction usable — the exact
behaviour ``ensure_due_room_charges``' FIX-3 handler relies on — and no
unhandled 500-class error escapes.

This is MEANINGFUL only on PostgreSQL (the production database): the partial
unique index + savepoint rollback are the artefacts under test, and true
multi-connection write concurrency needs PostgreSQL's row locking. SQLite
(the default test backend) serialises writers with a process-wide lock and
has different threading semantics, so the PostgreSQL-specific work is SKIPPED
there (``self.skipTest``) rather than producing a false green.
"""
from __future__ import annotations

import threading
from datetime import timedelta

from django.db import IntegrityError, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.finance import services as fin
from apps.finance.models import ChargeType, FolioCharge, PostingStatus
from apps.guests.models import Guest
from apps.rooms.models import Floor, Room, RoomType
from apps.stays.models import Stay
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

_PG_SKIP = (
    "Real two-connection room-night concurrency is only meaningful on "
    "PostgreSQL (partial unique index + savepoint rollback + row locking). "
    "SQLite serialises writers with a process-wide lock and has different "
    "threading semantics; skipped to avoid a false green on SQLite."
)


class RoomNightConcurrencyTests(TransactionTestCase):
    """TransactionTestCase COMMITS setUp data (there is no outer wrapping
    transaction), so the two worker threads — each on its own connection —
    can actually SEE the committed hotel/stay/folio. Under a plain
    ``TestCase`` the fixtures would live in an uncommitted transaction
    invisible to the workers, so a real concurrency test requires this base
    class."""

    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Hotel", slug="conc-hotel", status=HotelStatus.ACTIVE
        )
        self.user = User.objects.create_user(
            email="conc@x.com", password="StrongPass!234", full_name="Conc"
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
            planned_check_in_date=timezone.localdate(),
            planned_check_out_date=timezone.localdate() + timedelta(days=2),
            # A per-stay rate SNAPSHOT so ``_stay_room_rate`` resolves a rate
            # without needing a reservation line (used by the ensure() test).
            nightly_rate="100.00",
            actual_check_in_at=timezone.now(),
        )
        # The folio is created and COMMITTED in setUp so both worker
        # connections share the exact same folio row.
        self.folio = fin.ensure_stay_folio(self.stay, user=self.user)
        self.night = self.stay.planned_check_in_date

    # -- worker: one direct add_charge of the shared night ------------------
    def _post_same_night(self, barrier, results, index):
        """One worker: its OWN connection, its OWN outer transaction, ONE
        ``add_charge`` for the shared night.

        Mirrors the production caller: the outer ``transaction.atomic()`` is
        "the request"; ``add_charge`` is ``@transaction.atomic`` -> a
        SAVEPOINT nested inside it. A unique collision therefore rolls back
        ONLY the savepoint, and the outer transaction stays usable — which we
        PROVE by issuing a read afterwards (on PostgreSQL a poisoned
        transaction would raise "current transaction is aborted" here) and by
        letting the outer block COMMIT cleanly. Records a plain string outcome
        and never lets an unexpected exception vanish."""
        try:
            barrier.wait(timeout=15)  # line both workers up right at the INSERT
            with transaction.atomic():
                try:
                    fin.add_charge(
                        self.folio,
                        charge_type=ChargeType.ROOM,
                        description=f"night {self.night.isoformat()}",
                        quantity=1,
                        unit_amount="100.00",
                        source=fin.ROOM_NIGHT_SOURCE,
                        room_night=self.night,
                        user=self.user,
                    )
                    outcome = "ok"
                except IntegrityError:
                    # The partial unique index rejected the duplicate. Prove the
                    # savepoint rollback left THIS outer transaction alive with a
                    # read; a broken (aborted) transaction would raise instead.
                    recovered = FolioCharge.objects.filter(
                        folio=self.folio, type=ChargeType.ROOM,
                        room_night=self.night, status=PostingStatus.POSTED,
                    ).exists()
                    outcome = "integrity_recovered" if recovered else "integrity_orphan"
            results[index] = outcome
        except Exception as exc:  # noqa: BLE001 - a leaked error must be visible
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            # Each worker owns its connection; close it so the pool is clean.
            connections["default"].close()

    def test_one_folio_charge_per_night_under_true_concurrency(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results = ["", ""]
        threads = [
            threading.Thread(
                target=self._post_same_night, args=(barrier, results, i)
            )
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Neither worker deadlocked / timed out.
        for t in threads:
            self.assertFalse(t.is_alive(), "a worker thread deadlocked or timed out")

        # No unhandled 500-class error escaped either worker.
        for r in results:
            self.assertFalse(
                str(r).startswith("unexpected:"),
                f"an unexpected (non-IntegrityError) error escaped a worker: {r}",
            )

        # Exactly one winner and exactly one integrity-rejected-but-recovered
        # loser: the loser saw the IntegrityError, rolled back its savepoint,
        # and its outer transaction survived (proved by the post-catch read).
        self.assertEqual(sorted(results), ["integrity_recovered", "ok"], results)

        # Exactly ONE posted charge exists for this (folio, room_night).
        posted = FolioCharge.objects.filter(
            folio=self.folio, type=ChargeType.ROOM, room_night=self.night,
            status=PostingStatus.POSTED,
        )
        self.assertEqual(posted.count(), 1, "the partial unique index must leave one charge")

        # The main pool connection is NOT poisoned by the loser's aborted work:
        # a follow-up write still succeeds.
        svc = fin.add_charge(
            self.folio, charge_type=ChargeType.SERVICE, description="after-race",
            quantity=1, unit_amount="10.00", user=self.user,
        )
        self.assertEqual(svc.status, PostingStatus.POSTED)

    # -- worker: the production entry point, ensure_due_room_charges ---------
    def _ensure_worker(self, barrier, results, index, as_of):
        """One worker calling the REAL production service. It locks the stay
        row (``ensure_stay_folio`` -> select_for_update), so the two workers
        serialise on the STAY (the first serialisation layer); the partial
        unique index is the second, backstop layer for paths that bypass the
        lock. Whichever loses the stay lock re-reads the now-posted nights and
        posts zero — convergence without a raised error."""
        try:
            barrier.wait(timeout=15)
            results[index] = fin.ensure_due_room_charges(
                self.stay, as_of=as_of, user=self.user
            )
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def test_ensure_due_room_charges_converges_under_concurrency(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        as_of = self.stay.planned_check_out_date  # both nights (D1, D1+1) due
        barrier = threading.Barrier(2)
        results = [None, None]
        threads = [
            threading.Thread(
                target=self._ensure_worker, args=(barrier, results, i, as_of)
            )
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for t in threads:
            self.assertFalse(t.is_alive(), "a worker thread deadlocked or timed out")
        for r in results:
            self.assertFalse(
                str(r).startswith("unexpected:"),
                f"an unexpected error escaped the production entry point: {r}",
            )

        # Across both workers exactly TWO nights were newly posted in total
        # (one worker posts both, the loser posts none — never a double).
        numeric = [r for r in results if isinstance(r, int)]
        self.assertEqual(len(numeric), 2)
        self.assertEqual(sum(numeric), 2, results)

        # And the folio holds exactly two DISTINCT posted room nights.
        nights = FolioCharge.objects.filter(
            folio=self.folio, type=ChargeType.ROOM, status=PostingStatus.POSTED,
            room_night__isnull=False,
        )
        self.assertEqual(nights.count(), 2)
        self.assertEqual(nights.values("room_night").distinct().count(), 2)
