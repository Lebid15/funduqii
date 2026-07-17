"""H1 — folio ROOM-charge revenue integrity.

Two guarantees under test:
  (1) A manual ROOM folio charge can no longer be created through ANY path
      (the charge serializer rejects it with a clear 400; ``add_charge`` — the
      single creator of every ``FolioCharge`` — refuses a ROOM charge that has
      no ``room_night`` as a defense-in-depth chokepoint).
  (2) An UNLINKED ROOM charge (``room_night IS NULL`` — only possible as
      pre-existing legacy data now) can NEVER silently disable automated
      nightly billing: ``ensure_due_room_charges`` still posts the due nights
      and surfaces the anomaly with a non-silent warning activity event.
"""
from __future__ import annotations

import threading
from datetime import timedelta
from decimal import Decimal

from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.common.exceptions import InvalidFinanceOperation
from apps.finance import services as fin
from apps.finance.models import (
    ChargeType,
    FolioCharge,
    NumberKind,
    PostingStatus,
)
from apps.guests.models import Guest
from apps.notifications.models import ActivityEvent
from apps.rooms.models import Floor, Room, RoomType
from apps.stays.models import Stay, StayRatePeriod
from apps.tenancy.models import (
    Hotel,
    HotelMembership,
    HotelStatus,
    MembershipType,
)

from .tests import ALL_FINANCE, HDR, add_member, make_hotel

_PG_SKIP = (
    "Real two-connection billing concurrency is only meaningful on PostgreSQL "
    "(partial unique index + row locking). SQLite serialises writers."
)


def _build_inhouse_stay(hotel, user, *, slug):
    """An in-house stay (2 nights) with a covering rate period + a folio."""
    rtype = RoomType.objects.create(
        hotel=hotel, name="Standard", code=f"STD-{slug}",
        base_capacity=2, max_capacity=3, base_rate="100.00",
    )
    floor = Floor.objects.create(hotel=hotel, name="G", number=f"0{slug}")
    room = Room.objects.create(
        hotel=hotel, floor=floor, room_type=rtype, number=f"1{slug}"
    )
    guest = Guest.objects.create(hotel=hotel, full_name="Guest One")
    stay = Stay.objects.create(
        hotel=hotel, room=room, primary_guest=guest, status="in_house",
        planned_check_in_date=timezone.localdate(),
        planned_check_out_date=timezone.localdate() + timedelta(days=2),
        actual_check_in_at=timezone.now(),
    )
    StayRatePeriod.objects.create(
        hotel=hotel, stay=stay,
        start_date=stay.planned_check_in_date,
        end_date=stay.planned_check_out_date,
        nightly_rate="100.00", currency="USD", source="booking",
    )
    folio = fin.ensure_stay_folio(stay, user=user)
    return stay, folio


def _seed_legacy_unlinked_room_charge(hotel, folio, user):
    """Simulate a pre-existing legacy ROOM charge with room_night IS NULL.
    Created directly (bypassing ``add_charge``, which now forbids it) exactly
    as such a row would exist in an older database. Wrapped in an atomic block so
    ``next_number``'s row lock is valid under TransactionTestCase too."""
    with transaction.atomic():
        return FolioCharge.objects.create(
            hotel=hotel, folio=folio,
            charge_number=fin.next_number(hotel, NumberKind.CHARGE),
            type=ChargeType.ROOM, description="legacy aggregate room charge",
            quantity=Decimal("1"), unit_amount=Decimal("300.00"),
            amount=Decimal("300.00"), tax_rate=Decimal("0"),
            tax_amount=Decimal("0"), total_amount=Decimal("300.00"),
            charge_date=timezone.localdate(), source="legacy",
            room_night=None, status=PostingStatus.POSTED, created_by=user,
        )


class ManualRoomChargeBlockedTests(APITestCase):
    """Acceptance 1/2/3/9 — the manual charge API rejects ROOM (clear 400),
    cannot be bypassed by the payload, and still accepts every other type;
    the rejection is a validation rule, not an RBAC gap."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.client.force_authenticate(self.manager)
        self.fid = self.client.post(
            reverse("finance:folio-list"), {"customer_name": "A"},
            format="json", **HDR(self.hotel),
        ).data["id"]

    def _charge(self, **body):
        body.setdefault("description", "X")
        body.setdefault("quantity", "1")
        body.setdefault("unit_amount", "100.00")
        return self.client.post(
            reverse("finance:folio-charge-create", args=[self.fid]),
            body, format="json", **HDR(self.hotel),
        )

    def test_manual_room_charge_rejected_with_clear_error(self):
        res = self._charge(type="room")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("room_charges_are_system_generated", str(res.data))
        # And nothing was posted.
        self.assertFalse(
            FolioCharge.objects.filter(
                folio_id=self.fid, type=ChargeType.ROOM
            ).exists()
        )

    def test_room_rejected_even_for_fully_permitted_manager(self):
        # The manager holds every finance permission — the 400 proves this is a
        # validation rule, not a permissions failure (which would be 403).
        res = self._charge(type="room")
        self.assertEqual(res.status_code, 400)
        self.assertNotEqual(res.status_code, 403)

    def test_allowed_manual_types_still_work(self):
        for t in ("service", "tax", "other"):
            res = self._charge(type=t, unit_amount="50.00")
            self.assertEqual(res.status_code, 201, f"{t}: {res.data}")
        # discount allows a negative amount (unchanged behaviour).
        res = self._charge(type="discount", unit_amount="-10.00")
        self.assertEqual(res.status_code, 201, res.data)


class AddChargeRoomChokepointTests(TestCase):
    """Acceptance 2/4 — the single creator ``add_charge`` refuses a ROOM charge
    with no room_night (covers every internal caller), yet the systematic path
    (which supplies room_night) works."""

    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(
            self.hotel, "svc@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.stay, self.folio = _build_inhouse_stay(
            self.hotel, self.user, slug="1"
        )

    def test_add_charge_room_without_room_night_raises(self):
        with self.assertRaises(InvalidFinanceOperation) as ctx:
            fin.add_charge(
                self.folio, charge_type=ChargeType.ROOM,
                description="stray room", quantity=1, unit_amount="100.00",
                user=self.user,
            )
        self.assertEqual(
            ctx.exception.detail.get("reason"), "manual_room_charge_forbidden"
        )

    def test_add_charge_room_with_room_night_ok(self):
        night = self.stay.planned_check_in_date
        charge = fin.add_charge(
            self.folio, charge_type=ChargeType.ROOM,
            description=f"night {night.isoformat()}", quantity=1,
            unit_amount="100.00", source=fin.ROOM_NIGHT_SOURCE,
            room_night=night, user=self.user,
        )
        self.assertEqual(charge.type, ChargeType.ROOM)
        self.assertEqual(charge.room_night, night)


class UnlinkedRoomChargeDoesNotDisableBillingTests(TestCase):
    """Acceptance 5/6/7/8 — an unlinked (legacy) ROOM charge never disables
    automated nightly billing; per-night idempotency holds; the folio balance
    reflects the real room nights; the anomaly is surfaced (non-silent)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(
            self.hotel, "own@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.stay, self.folio = _build_inhouse_stay(
            self.hotel, self.user, slug="2"
        )
        self.as_of = self.stay.planned_check_out_date  # both nights due

    def test_systematic_billing_posts_each_night(self):
        posted = fin.ensure_due_room_charges(
            self.stay, as_of=self.as_of, user=self.user
        )
        self.assertEqual(posted, 2)
        nights = FolioCharge.objects.filter(
            folio=self.folio, type=ChargeType.ROOM,
            status=PostingStatus.POSTED, room_night__isnull=False,
        )
        self.assertEqual(nights.count(), 2)
        self.assertEqual(nights.values("room_night").distinct().count(), 2)

    def test_unlinked_charge_does_not_suppress_billing(self):
        _seed_legacy_unlinked_room_charge(self.hotel, self.folio, self.user)
        posted = fin.ensure_due_room_charges(
            self.stay, as_of=self.as_of, user=self.user
        )
        # The legacy row did NOT disable billing: both nights still posted.
        self.assertEqual(posted, 2)
        self.assertEqual(
            FolioCharge.objects.filter(
                folio=self.folio, type=ChargeType.ROOM,
                status=PostingStatus.POSTED, room_night__isnull=False,
            ).count(),
            2,
        )
        # And the anomaly is surfaced non-silently.
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="charge.room_unlinked_detected"
            ).exists()
        )

    def test_ensure_is_idempotent(self):
        first = fin.ensure_due_room_charges(
            self.stay, as_of=self.as_of, user=self.user
        )
        second = fin.ensure_due_room_charges(
            self.stay, as_of=self.as_of, user=self.user
        )
        self.assertEqual(first, 2)
        self.assertEqual(second, 0)  # nothing new the second time
        # No duplicate for any room_night.
        nights = FolioCharge.objects.filter(
            folio=self.folio, type=ChargeType.ROOM,
            status=PostingStatus.POSTED, room_night__isnull=False,
        )
        self.assertEqual(nights.count(), 2)
        self.assertEqual(nights.values("room_night").distinct().count(), 2)

    def test_folio_balance_reflects_room_nights(self):
        _seed_legacy_unlinked_room_charge(self.hotel, self.folio, self.user)
        fin.ensure_due_room_charges(self.stay, as_of=self.as_of, user=self.user)
        bal = fin.folio_balance(self.folio)
        # 2 nights * 100 + the legacy 300 all count as posted charges — the
        # point is the nights ARE billed (balance is not left short by the
        # unlinked row disabling per-night posting).
        self.assertEqual(bal["total_charges"], Decimal("500.00"))


class UnlinkedRoomChargeConcurrencyTests(TransactionTestCase):
    """Acceptance 10 — with a legacy unlinked ROOM charge present, two
    CONCURRENT ``ensure_due_room_charges`` calls still converge to exactly the
    real nights (never a double, never disabled). PostgreSQL only."""

    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Hotel", slug="h1-conc", status=HotelStatus.ACTIVE
        )
        self.user = User.objects.create_user(
            email="h1c@x.com", password="StrongPass!234", full_name="H1C"
        )
        HotelMembership.objects.create(
            user=self.user, hotel=self.hotel,
            membership_type=MembershipType.MANAGER, is_active=True,
        )
        self.stay, self.folio = _build_inhouse_stay(
            self.hotel, self.user, slug="9"
        )
        _seed_legacy_unlinked_room_charge(self.hotel, self.folio, self.user)
        self.as_of = self.stay.planned_check_out_date

    def _worker(self, barrier, results, index):
        try:
            barrier.wait(timeout=15)
            results[index] = fin.ensure_due_room_charges(
                self.stay, as_of=self.as_of, user=self.user
            )
        except Exception as exc:  # noqa: BLE001
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def test_billing_converges_with_unlinked_charge_present(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)
        barrier = threading.Barrier(2)
        results = [None, None]
        threads = [
            threading.Thread(target=self._worker, args=(barrier, results, i))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        for t in threads:
            self.assertFalse(t.is_alive(), "a worker deadlocked or timed out")
        for r in results:
            self.assertFalse(
                str(r).startswith("unexpected:"),
                f"an unexpected error escaped a worker: {r}",
            )
        numeric = [r for r in results if isinstance(r, int)]
        self.assertEqual(sum(numeric), 2, results)  # exactly two nights total
        nights = FolioCharge.objects.filter(
            folio=self.folio, type=ChargeType.ROOM,
            status=PostingStatus.POSTED, room_night__isnull=False,
        )
        self.assertEqual(nights.count(), 2)
        self.assertEqual(nights.values("room_night").distinct().count(), 2)
