"""RESTAURANT-CAFETERIA-OPERATIONAL-CLOSURE — the real money races (D5).

Three two-connection proofs (PostgreSQL only — SQLite serialises writers with a
process-wide lock and has different threading semantics, so it is SKIPPED there
rather than reporting a false green):

1. :class:`SettleSameKeyRaceTests` — two CONCURRENT direct settlements sharing one
   ``settlement_key`` on the SAME order. Both pass the fast path, serialize on the
   order row, and the loser replays the winner's settlement under the lock — the
   ONLY way to actually execute the post-lock re-check. Exactly ONE Payment.
2. :class:`SettleKeyReuseAcrossOrdersRaceTests` — the same ``settlement_key`` reused
   across TWO DIFFERENT orders. The workers lock different rows, both reach the
   ``order.save``, and the partial unique constraint fires for the loser — the
   savepoint catches the ``IntegrityError`` and translates it to a clean
   ``IdempotencyKeyConflict`` (409) with NO orphan folio / charge / payment.
3. :class:`ReturnSameKeyRaceTests` — two CONCURRENT returns sharing one
   ``idempotency_key`` on the SAME order. Exactly ONE ServiceOrderReturn and ONE
   credit charge; the loser replays, moving no second money.
"""
from __future__ import annotations

import threading
from datetime import timedelta
from decimal import Decimal

from django.db import connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.finance.constants import ChargeSource
from apps.finance.models import Folio, FolioCharge, Payment, PostingStatus
from apps.guests.models import Guest
from apps.rooms.models import Floor, Room, RoomType
from apps.services.models import OrderStatus, OrderType, Outlet, ServiceOrder
from apps.services.services import (
    build_return_fingerprint,
    build_settlement_fingerprint,
    change_status,
    create_order,
    post_order_to_folio,
    return_order,
    settle_order_direct,
)
from apps.stays.models import Stay, StayStatus
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

_PG_SKIP = (
    "The real two-connection money race is only meaningful on PostgreSQL (row "
    "locking + savepoint rollback). SQLite serialises writers with a process-wide "
    "lock and has different threading semantics; skipped to avoid a false green."
)


class _RaceSetup(TransactionTestCase):
    """TransactionTestCase COMMITS setUp so the two worker connections both see the
    committed hotel / stay / catalog / order rows."""

    def _make_catalog_hotel(self, slug):
        from apps.services.models import ServiceCategory, ServiceItem

        hotel = Hotel.objects.create(name="Hotel", slug=slug, status=HotelStatus.ACTIVE)
        user = User.objects.create_user(
            email=f"{slug}@x.com", password="StrongPass!234", full_name="Race"
        )
        HotelMembership.objects.create(
            user=user, hotel=hotel,
            membership_type=MembershipType.MANAGER, is_active=True,
        )
        category = ServiceCategory.objects.create(
            hotel=hotel, outlet=Outlet.RESTAURANT, name="Menu"
        )
        item = ServiceItem.objects.create(
            hotel=hotel, category=category, name="Burger",
            unit_price=Decimal("40.00"), tax_rate=Decimal("10.00"),
        )
        return hotel, user, item

    def _make_stay(self, hotel, number="101"):
        floor = Floor.objects.create(hotel=hotel, name="G", number="0")
        rt = RoomType.objects.create(
            hotel=hotel, name="Std", code=f"S{number}", base_capacity=2, max_capacity=2
        )
        room = Room.objects.create(hotel=hotel, floor=floor, room_type=rt, number=number)
        guest = Guest.objects.create(hotel=hotel, full_name="Guest One")
        return Stay.objects.create(
            hotel=hotel, room=room, primary_guest=guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=timezone.localdate(),
            planned_check_out_date=timezone.localdate() + timedelta(days=2),
            actual_check_in_at=timezone.now(),
        )

    def _delivered_order(self, hotel, user, item, *, stay=None):
        order = create_order(
            hotel, user=user, order_type=OrderType.ROOM if stay else OrderType.TABLE,
            outlet=Outlet.RESTAURANT, stay=stay,
            table=None if stay else self._table(hotel),
            items_data=[{"service_item": item, "quantity": Decimal("2")}],
        )
        change_status(order, new_status=OrderStatus.DELIVERED, user=user)
        return ServiceOrder.objects.get(pk=order.pk)

    def _table(self, hotel):
        from apps.services.models import RestaurantTable

        n = RestaurantTable.objects.count() + 1
        return RestaurantTable.objects.create(
            hotel=hotel, outlet=Outlet.RESTAURANT, number=f"T{n}"
        )


class SettleSameKeyRaceTests(_RaceSetup):
    def setUp(self):
        self.hotel, self.user, self.item = self._make_catalog_hotel("svc-settle-race")
        self.order = self._delivered_order(self.hotel, self.user, self.item)

    def _worker(self, barrier, results, index):
        try:
            fp = build_settlement_fingerprint(order_id=self.order.id, method="cash")
            barrier.wait(timeout=15)
            order = settle_order_direct(
                self.order, method="cash", user=self.user,
                settlement_key="settle-race", settlement_fingerprint=fp,
            )
            results[index] = ("ok", order.pk)
        except Exception as exc:  # noqa: BLE001 - a leaked error must be visible
            results[index] = (type(exc).__name__, str(exc))
        finally:
            connections["default"].close()

    def test_two_concurrent_settles_same_key_pay_once(self):
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
            self.assertFalse(t.is_alive(), f"a worker deadlocked: {results}")
        # Identical requests are a legal replay — both succeed.
        for outcome in results:
            self.assertEqual(outcome[0], "ok", f"unexpected failure: {results}")
        # THE INVARIANT: exactly one payment, one transient folio — never two.
        self.assertEqual(
            Payment.objects.filter(folio__service_orders=self.order).count(), 1,
            f"idempotency lost — a second payment moved: {results}",
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.settlement, "direct")


class SettleKeyReuseAcrossOrdersRaceTests(_RaceSetup):
    """The ``IntegrityError -> IdempotencyKeyConflict`` savepoint — the ONLY test
    that executes it. Two DIFFERENT orders reuse one key; the loser must leave
    NOTHING behind (no orphan folio / charge / payment)."""

    def setUp(self):
        self.hotel, self.user, self.item = self._make_catalog_hotel("svc-keyreuse-race")
        self.orders = [
            self._delivered_order(self.hotel, self.user, self.item),
            self._delivered_order(self.hotel, self.user, self.item),
        ]

    def _worker(self, barrier, results, index):
        order = self.orders[index]
        try:
            fp = build_settlement_fingerprint(order_id=order.id, method="cash")
            barrier.wait(timeout=15)
            settle_order_direct(
                order, method="cash", user=self.user,
                settlement_key="reused-key", settlement_fingerprint=fp,
            )
            results[index] = ("ok", order.pk)
        except Exception as exc:  # noqa: BLE001
            results[index] = (type(exc).__name__, str(exc))
        finally:
            connections["default"].close()

    def test_key_reused_across_orders_one_winner_no_orphan(self):
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
            self.assertFalse(t.is_alive(), f"a worker deadlocked: {results}")
        kinds = sorted(o[0] for o in results)
        self.assertEqual(
            kinds, ["IdempotencyKeyConflict", "ok"],
            f"expected one winner + one clean conflict, got: {results}",
        )
        # THE POINT: exactly one payment across BOTH orders — the loser rolled its
        # whole transient cycle back (no orphan folio / charge / payment).
        self.assertEqual(
            Payment.objects.filter(hotel=self.hotel).count(), 1,
            f"the loser left an orphan payment behind: {results}",
        )
        settled = [o for o in self.orders if ServiceOrder.objects.get(pk=o.pk).settlement == "direct"]
        self.assertEqual(len(settled), 1, f"exactly one order settled: {results}")


class ReturnSameKeyRaceTests(_RaceSetup):
    def setUp(self):
        self.hotel, self.user, self.item = self._make_catalog_hotel("svc-return-race")
        self.stay = self._make_stay(self.hotel)
        self.order = self._delivered_order(self.hotel, self.user, self.item, stay=self.stay)
        self.order = post_order_to_folio(self.order, user=self.user)
        self.line = self.order.items.first()

    def _worker(self, barrier, results, index):
        try:
            fp = build_return_fingerprint(
                order_id=self.order.id, kind="return",
                items=[{"original_item": self.line.id, "quantity": "1"}],
                reason="race",
            )
            barrier.wait(timeout=15)
            ret = return_order(
                self.order, kind="return",
                items=[{
                    "original_item": self.line, "quantity": Decimal("1"),
                    "replacement_item": None, "replacement_quantity": None,
                }],
                reason="race", user=self.user,
                idempotency_key="return-race", request_fingerprint=fp,
            )
            results[index] = ("ok", ret.pk)
        except Exception as exc:  # noqa: BLE001
            results[index] = (type(exc).__name__, str(exc))
        finally:
            connections["default"].close()

    def test_two_concurrent_returns_same_key_refund_once(self):
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
            self.assertFalse(t.is_alive(), f"a worker deadlocked: {results}")
        for outcome in results:
            self.assertEqual(outcome[0], "ok", f"unexpected failure: {results}")
        from apps.services.models import ServiceOrderReturn

        self.assertEqual(
            ServiceOrderReturn.objects.filter(order=self.order).count(), 1,
            f"idempotency lost — a second return recorded: {results}",
        )
        # Exactly ONE credit charge moved (source order_return), POSTED.
        credits = FolioCharge.objects.filter(
            hotel=self.hotel, source="order_return", status=PostingStatus.POSTED
        )
        self.assertEqual(
            credits.count(), 1,
            f"a duplicate or orphan refund charge survived the race: {results}",
        )
        # Both workers were handed the SAME return.
        self.assertEqual(results[0][1], results[1][1], results)
