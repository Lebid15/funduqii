"""GUEST-FOLIO-EXTRA-SERVICES-CLOSURE — the check-out race (#10, PostgreSQL-only).

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
