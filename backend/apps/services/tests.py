"""Tests for service orders (Phase 9): access/permissions, catalog, orders,
status workflow, posting to folio, numbering, overview, and regression.

Covers tenant isolation, the suspended-hotel read-only rule, Decimal-only
totals with per-line snapshots, and the once-only financial exit to Phase 8.
"""
from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.models import Folio, FolioCharge, FolioStatus, PostingStatus
from apps.finance.services import create_folio, folio_balance
from apps.guests.models import Guest
from apps.rbac.services import grant_permission
from apps.rooms.models import Floor, Room, RoomType
from apps.services.models import (
    OrderStatus,
    ServiceCategory,
    ServiceItem,
    ServiceOrder,
)
from apps.stays.models import Stay
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

ALL_SERVICES = [
    "services.view", "services.create", "services.update", "services.delete",
    "services.tables_manage",
    "service_orders.view", "service_orders.create", "service_orders.update",
    "service_orders.cancel", "service_orders.status_update",
    "service_orders.post_to_folio", "service_orders.settle_direct",
]


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=()):
    user = User.objects.create_user(
        email=email, password="StrongPass!234", full_name="Member"
    )
    m = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True
    )
    for code in perms:
        grant_permission(m, code)
    return user


def make_category(hotel, name="Restaurant", **kw):
    return ServiceCategory.objects.create(hotel=hotel, name=name, **kw)


def make_item(hotel, category, name="Burger", price="40.00", tax="10.00", **kw):
    return ServiceItem.objects.create(
        hotel=hotel,
        category=category,
        name=name,
        unit_price=Decimal(price),
        tax_rate=Decimal(tax),
        **kw,
    )


def make_stay(hotel, *, room_number="101"):
    floor = Floor.objects.create(hotel=hotel, name="G", number="0")
    rt = RoomType.objects.create(
        hotel=hotel, name="Std", code=f"S{room_number}", base_capacity=2, max_capacity=2
    )
    room = Room.objects.create(hotel=hotel, floor=floor, room_type=rt, number=room_number)
    guest = Guest.objects.create(hotel=hotel, full_name="Guest One", email="g@x.com")
    stay = Stay.objects.create(
        hotel=hotel,
        room=room,
        primary_guest=guest,
        planned_check_in_date=timezone.localdate(),
        planned_check_out_date=timezone.localdate() + timezone.timedelta(days=2),
        actual_check_in_at=timezone.now(),
    )
    return stay


class ServicesMixin:
    _table_seq = {"n": 0}

    def make_catalog(self):
        self.category = make_category(self.hotel)                 # restaurant
        self.item = make_item(self.hotel, self.category)          # 40.00 +10%
        self.item2 = make_item(self.hotel, self.category, name="Tea", price="10.00", tax="0.00")

    def make_table(self, hotel=None, outlet="restaurant", **kw):
        from apps.services.models import RestaurantTable

        ServicesMixin._table_seq["n"] += 1
        return RestaurantTable.objects.create(
            hotel=hotel or self.hotel,
            outlet=outlet,
            number=f"T{ServicesMixin._table_seq['n']:03d}",
            **kw,
        )

    def create_order(self, hotel=None, **body):
        """Order-create helper. Legacy call sites keep working: a body with a
        stay becomes a ROOM order; anything else becomes a TABLE order on a
        fresh table (one open order per table)."""
        hotel = hotel or self.hotel
        body.setdefault("items", [{"service_item": self.item.id, "quantity": "2"}])
        if "order_type" not in body:
            body["order_type"] = "room" if body.get("stay") else "table"
        if body["order_type"] == "table":
            body.setdefault("table", self.make_table(hotel).id)
        body.setdefault("outlet", "restaurant")
        return self.client.post(
            reverse("services:order-list"), body, format="json", **HDR(hotel)
        )

    def set_status(self, oid, new_status, hotel=None):
        return self.client.post(
            reverse("services:order-status", args=[oid]),
            {"status": new_status},
            format="json",
            **HDR(hotel or self.hotel),
        )

    def deliver(self, oid):
        return self.set_status(oid, "delivered")

    def post_order(self, oid, hotel=None):
        return self.client.post(
            reverse("services:order-post-to-folio", args=[oid]),
            {},
            format="json",
            **HDR(hotel or self.hotel),
        )


# --------------------------------------------------------------------------- #
# Access / permissions                                                          #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase, ServicesMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.make_catalog()

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(reverse("services:item-list"), **HDR(self.hotel)).status_code,
            401,
        )

    def test_no_membership_denied(self):
        lonely = User.objects.create_user(
            email="l@x.com", password="StrongPass!234", full_name="L"
        )
        self.client.force_authenticate(lonely)
        self.assertEqual(
            self.client.get(reverse("services:item-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_other_hotel_denied(self):
        other = make_hotel(slug="o")
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("services:item-list"), **HDR(other)).status_code, 403
        )

    def test_platform_owner_without_membership_denied(self):
        owner = User.objects.create_platform_owner(
            email="o@x.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(reverse("services:order-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_manager_can_manage(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("services:overview"), **HDR(self.hotel)).status_code,
            200,
        )
        self.assertEqual(self.create_order().status_code, 201)

    def test_staff_view_permission(self):
        staff = add_member(self.hotel, "s@x.com", perms=["services.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("services:item-list"), **HDR(self.hotel)).status_code,
            200,
        )

    def test_staff_without_permission_denied(self):
        staff = add_member(self.hotel, "s2@x.com")
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("services:item-list"), **HDR(self.hotel)).status_code,
            403,
        )
        self.assertEqual(self.create_order().status_code, 403)

    def test_staff_create_order_permission(self):
        staff = add_member(
            self.hotel, "s3@x.com", perms=["service_orders.create", "service_orders.view"]
        )
        self.client.force_authenticate(staff)
        self.assertEqual(self.create_order().status_code, 201)

    def test_staff_status_and_post_permissions(self):
        creator = add_member(self.hotel, "c@x.com", perms=["service_orders.create"])
        self.client.force_authenticate(creator)
        oid = self.create_order().data["id"]
        # No status_update permission:
        self.assertEqual(self.deliver(oid).status_code, 403)
        mover = add_member(self.hotel, "mv@x.com", perms=["service_orders.status_update"])
        self.client.force_authenticate(mover)
        self.assertEqual(self.deliver(oid).status_code, 200)
        # No post permission:
        self.assertEqual(self.post_order(oid).status_code, 403)

    def test_suspended_hotel_read_only(self):
        self.client.force_authenticate(self.manager)
        oid = self.create_order().data["id"]
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        # Reads still fine.
        self.assertEqual(
            self.client.get(reverse("services:order-list"), **HDR(self.hotel)).status_code,
            200,
        )
        # Every write is blocked with hotel_suspended.
        for res in (
            self.create_order(),
            self.set_status(oid, "preparing"),
            self.client.post(
                reverse("services:order-cancel", args=[oid]),
                {"reason": "x"}, format="json", **HDR(self.hotel),
            ),
            self.post_order(oid),
            self.client.post(
                reverse("services:category-list"), {"name": "X"},
                format="json", **HDR(self.hotel),
            ),
        ):
            self.assertEqual(res.status_code, 403)
            self.assertEqual(res.data["code"], "hotel_suspended")


# --------------------------------------------------------------------------- #
# Catalog                                                                       #
# --------------------------------------------------------------------------- #


class CatalogTests(APITestCase, ServicesMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_create_and_update_category(self):
        res = self.client.post(
            reverse("services:category-list"),
            {"name": "Café", "code": "CAFE"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)
        cid = res.data["id"]
        res = self.client.patch(
            reverse("services:category-detail", args=[cid]),
            {"name": "Cafeteria"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.data["name"], "Cafeteria")

    def test_lists_scoped_by_hotel(self):
        make_category(self.hotel, name="Mine")
        other = make_hotel(slug="o")
        make_category(other, name="Theirs")
        res = self.client.get(reverse("services:category-list"), **HDR(self.hotel))
        names = [c["name"] for c in res.data["results"]]
        self.assertIn("Mine", names)
        self.assertNotIn("Theirs", names)

    def test_create_item_and_price_validation(self):
        cat = make_category(self.hotel)
        res = self.client.post(
            reverse("services:item-list"),
            {"category": cat.id, "name": "Juice", "unit_price": "12.50",
             "tax_rate": "5.00"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)
        # Legacy item_type is deprecated: sending it is refused outright.
        legacy = self.client.post(
            reverse("services:item-list"),
            {"category": cat.id, "name": "Old", "unit_price": "1.00",
             "item_type": "cafe"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(legacy.status_code, 400)
        bad = self.client.post(
            reverse("services:item-list"),
            {"category": cat.id, "name": "Bad", "unit_price": "-1"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(bad.status_code, 400)

    def test_item_category_must_be_same_hotel(self):
        other = make_hotel(slug="o")
        foreign_cat = make_category(other)
        res = self.client.post(
            reverse("services:item-list"),
            {"category": foreign_cat.id, "name": "X", "unit_price": "1.00"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "cross_tenant_reference")

    def test_inactive_or_unavailable_item_cannot_be_ordered(self):
        self.make_catalog()
        self.item.is_available = False
        self.item.save()
        res = self.create_order()
        self.assertEqual(res.status_code, 422)
        self.item.is_available = True
        self.item.is_active = False
        self.item.save()
        res = self.create_order()
        self.assertEqual(res.status_code, 422)

    def test_cannot_delete_category_with_items(self):
        self.make_catalog()
        res = self.client.delete(
            reverse("services:category-detail", args=[self.category.id]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "resource_in_use")

    def test_cannot_delete_item_used_in_order(self):
        self.make_catalog()
        self.create_order()
        res = self.client.delete(
            reverse("services:item-detail", args=[self.item.id]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "resource_in_use")
        # Unused item deletes fine.
        res = self.client.delete(
            reverse("services:item-detail", args=[self.item2.id]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 204)

    def test_item_filters(self):
        self.make_catalog()
        res = self.client.get(
            reverse("services:item-list"), {"search": "Tea"}, **HDR(self.hotel)
        )
        self.assertEqual(res.data["count"], 1)
        res = self.client.get(
            reverse("services:item-list"), {"outlet": "restaurant"}, **HDR(self.hotel)
        )
        self.assertEqual(res.data["count"], 2)
        res = self.client.get(
            reverse("services:item-list"), {"outlet": "cafe"}, **HDR(self.hotel)
        )
        self.assertEqual(res.data["count"], 0)


# --------------------------------------------------------------------------- #
# Orders                                                                        #
# --------------------------------------------------------------------------- #


class OrderTests(APITestCase, ServicesMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.make_catalog()

    def test_create_order_totals(self):
        res = self.create_order(
            items=[
                {"service_item": self.item.id, "quantity": "2"},   # 80 + 8 tax
                {"service_item": self.item2.id, "quantity": "3"},  # 30 + 0 tax
            ]
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["order_number"], "ORD00001")
        self.assertEqual(res.data["totals"], {
            "subtotal": "110.00", "tax_total": "8.00", "total": "118.00",
            "currency": "USD",
        })
        # D1a — the order and every line snapshot the hotel base currency.
        self.assertEqual(res.data["currency"], "USD")
        self.assertTrue(all(i["currency"] == "USD" for i in res.data["items"]))
        self.assertEqual(res.data["status"], "submitted")

    def test_quantity_validation(self):
        res = self.create_order(items=[{"service_item": self.item.id, "quantity": "0"}])
        self.assertEqual(res.status_code, 400)

    def test_snapshot_survives_price_change(self):
        res = self.create_order()
        oid = res.data["id"]
        self.item.unit_price = Decimal("99.00")
        self.item.name = "Renamed"
        self.item.save()
        detail = self.client.get(
            reverse("services:order-detail", args=[oid]), **HDR(self.hotel)
        )
        line = detail.data["items"][0]
        self.assertEqual(line["item_name"], "Burger")
        self.assertEqual(line["unit_price"], "40.00")
        self.assertEqual(detail.data["totals"]["total"], "88.00")

    def test_order_numbering_per_hotel(self):
        self.create_order()
        self.create_order()
        other = make_hotel(slug="o")
        mgr2 = add_member(other, "m2@x.com", kind=MembershipType.MANAGER)
        cat2 = make_category(other)
        item2 = make_item(other, cat2)
        self.client.force_authenticate(mgr2)
        res = self.create_order(hotel=other, items=[{"service_item": item2.id, "quantity": "1"}])
        self.assertEqual(res.data["order_number"], "ORD00001")  # independent sequence

    def test_filters_and_search(self):
        oid = self.create_order().data["id"]
        self.deliver(oid)
        res = self.client.get(
            reverse("services:order-list"), {"status": "delivered"}, **HDR(self.hotel)
        )
        self.assertEqual(res.data["count"], 1)
        res = self.client.get(
            reverse("services:order-list"), {"posted": "false"}, **HDR(self.hotel)
        )
        self.assertEqual(res.data["count"], 1)
        res = self.client.get(
            reverse("services:order-list"), {"search": "ORD00001"}, **HDR(self.hotel)
        )
        self.assertEqual(res.data["count"], 1)

    def test_status_workflow_and_log(self):
        oid = self.create_order().data["id"]
        self.assertEqual(self.set_status(oid, "preparing").status_code, 200)
        self.assertEqual(self.set_status(oid, "ready").status_code, 200)
        self.assertEqual(self.set_status(oid, "delivered").status_code, 200)
        detail = self.client.get(
            reverse("services:order-detail", args=[oid]), **HDR(self.hotel)
        )
        self.assertIsNotNone(detail.data["delivered_at"])
        logs = detail.data["status_logs"]
        self.assertEqual(len(logs), 4)  # created + 3 transitions

    def test_invalid_transition_rejected(self):
        oid = self.create_order().data["id"]
        self.deliver(oid)
        res = self.set_status(oid, "preparing")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_order_status_transition")

    def test_cancel_requires_reason(self):
        oid = self.create_order().data["id"]
        res = self.client.post(
            reverse("services:order-cancel", args=[oid]), {}, format="json", **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            reverse("services:order-cancel", args=[oid]),
            {"reason": "guest changed mind"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "cancelled")

    def test_cancelled_order_not_editable(self):
        oid = self.create_order().data["id"]
        self.client.post(
            reverse("services:order-cancel", args=[oid]),
            {"reason": "x"}, format="json", **HDR(self.hotel),
        )
        res = self.client.patch(
            reverse("services:order-detail", args=[oid]),
            {"notes": "hi"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 409)

    def test_delivered_items_locked(self):
        oid = self.create_order().data["id"]
        self.deliver(oid)
        res = self.client.patch(
            reverse("services:order-detail", args=[oid]),
            {"items": [{"service_item": self.item2.id, "quantity": "1"}]},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 409)

    def test_no_hard_delete_route_for_orders(self):
        oid = self.create_order().data["id"]
        res = self.client.delete(
            reverse("services:order-detail", args=[oid]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 405)

    def test_cross_tenant_stay_rejected(self):
        other = make_hotel(slug="o")
        foreign_stay = make_stay(other)
        res = self.create_order(stay=foreign_stay.id)
        self.assertEqual(res.status_code, 404)  # hotel-scoped lookup

    def test_ticket_payload(self):
        oid = self.create_order().data["id"]
        # Default = KOT: items + prep notes, deliberately NO money on it.
        res = self.client.get(
            reverse("services:order-ticket", args=[oid]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["document"], "service_ticket")
        self.assertNotIn("totals", res.data)
        self.assertNotIn("unit_price", res.data["items"][0])
        self.assertEqual(len(res.data["items"]), 1)
        # Guest check: items + taxes + totals (before settlement).
        res = self.client.get(
            reverse("services:order-ticket", args=[oid]),
            {"variant": "guest_check"}, **HDR(self.hotel),
        )
        self.assertEqual(res.data["document"], "guest_check")
        self.assertEqual(res.data["totals"]["total"], "88.00")
        self.assertEqual(res.data["items"][0]["unit_price"], "40.00")


# --------------------------------------------------------------------------- #
# Posting to folio                                                              #
# --------------------------------------------------------------------------- #


class PostingTests(APITestCase, ServicesMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.make_catalog()
        self.stay = make_stay(self.hotel)

    def _delivered_order(self, **kw):
        kw.setdefault("stay", self.stay.id)
        oid = self.create_order(**kw).data["id"]
        self.deliver(oid)
        return oid

    def test_post_creates_charge_with_exact_totals(self):
        oid = self._delivered_order(
            items=[
                {"service_item": self.item.id, "quantity": "2"},   # 80 + 8
                {"service_item": self.item2.id, "quantity": "1"},  # 10 + 0
            ]
        )
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["is_posted"])
        charge = FolioCharge.objects.get(pk=res.data["posted_charge"])
        self.assertEqual(str(charge.amount), "90.00")
        self.assertEqual(str(charge.tax_amount), "8.00")
        self.assertEqual(str(charge.total_amount), "98.00")
        self.assertEqual(charge.source, "service_order")
        self.assertEqual(charge.type, "service")
        self.assertIn("ORD00001", charge.description)
        # Balance reflects the posted order.
        folio = Folio.objects.get(pk=res.data["folio"])
        self.assertEqual(str(folio_balance(folio)["balance"]), "98.00")

    def test_posting_auto_creates_folio_for_stay(self):
        self.assertEqual(Folio.objects.count(), 0)
        oid = self._delivered_order()
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 200)
        folio = Folio.objects.get(pk=res.data["folio"])
        self.assertEqual(folio.stay_id, self.stay.id)
        self.assertEqual(folio.guest_id, self.stay.primary_guest_id)
        self.assertEqual(folio.status, FolioStatus.OPEN)

    def test_posting_reuses_open_folio(self):
        folio = create_folio(self.hotel, stay=self.stay, guest=self.stay.primary_guest)
        oid = self._delivered_order()
        res = self.post_order(oid)
        self.assertEqual(res.data["folio"], folio.id)
        self.assertEqual(Folio.objects.count(), 1)

    def test_posting_twice_rejected(self):
        oid = self._delivered_order()
        self.assertEqual(self.post_order(oid).status_code, 200)
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_already_posted")
        self.assertEqual(FolioCharge.objects.count(), 1)

    def test_posting_undelivered_rejected(self):
        oid = self.create_order(stay=self.stay.id).data["id"]
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_not_postable")

    def test_posting_cancelled_rejected(self):
        oid = self.create_order(stay=self.stay.id).data["id"]
        self.client.post(
            reverse("services:order-cancel", args=[oid]),
            {"reason": "x"}, format="json", **HDR(self.hotel),
        )
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_not_postable")

    def test_posting_without_stay_or_folio_rejected(self):
        oid = self._delivered_order(stay=None)
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_not_postable")

    def test_posting_to_closed_folio_rejected(self):
        folio = create_folio(self.hotel, stay=self.stay, guest=self.stay.primary_guest)
        folio.status = FolioStatus.CLOSED
        folio.save()
        oid = self._delivered_order()
        res = self.post_order(oid)
        # The stay's only folio is closed -> a NEW open folio is created instead
        # (closed folios never receive charges).
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.data["folio"], folio.id)

    def test_posted_order_cannot_be_cancelled(self):
        oid = self._delivered_order()
        self.post_order(oid)
        res = self.client.post(
            reverse("services:order-cancel", args=[oid]),
            {"reason": "x"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_not_editable")

    def test_charge_void_stays_in_finance(self):
        oid = self._delivered_order()
        cid = self.post_order(oid).data["posted_charge"]
        res = self.client.post(
            reverse("finance:charge-void", args=[cid]),
            {"reason": "mistake"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        charge = FolioCharge.objects.get(pk=cid)
        self.assertEqual(charge.status, PostingStatus.VOIDED)
        # Order stays posted (no un-posting) — the money trail lives in finance.
        order = ServiceOrder.objects.get(pk=oid)
        self.assertTrue(order.is_posted)


# --------------------------------------------------------------------------- #
# Overview + regression                                                         #
# --------------------------------------------------------------------------- #


class OverviewTests(APITestCase, ServicesMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.make_catalog()
        self.stay = make_stay(self.hotel)

    def test_overview_counts(self):
        o1 = self.create_order(stay=self.stay.id).data["id"]
        self.create_order()
        self.deliver(o1)
        self.post_order(o1)
        res = self.client.get(reverse("services:overview"), **HDR(self.hotel))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["orders_today"], 2)
        self.assertEqual(res.data["submitted"], 1)
        self.assertEqual(res.data["delivered"], 1)
        self.assertEqual(res.data["delivered_not_posted"], 0)
        self.assertEqual(res.data["posted_today_total"], "88.00")
        self.assertEqual(res.data["active_items"], 2)


class RegressionTests(APITestCase):
    def test_health_still_works(self):
        res = self.client.get(reverse("health"))
        self.assertEqual(res.status_code, 200)

    def test_no_out_of_scope_routes(self):
        # POS/inventory/public ordering belong to NO phase yet.
        # (tables became legitimate in the restaurant/café final closure.)
        for path in (
            "/api/v1/hotel/services/pos/",
            "/api/v1/hotel/services/inventory/",
            "/api/v1/hotel/services/public-orders/",
            # (shifts/daily-close became legitimate in Phase 12.)
            "/api/v1/hotel/payroll/",
            "/api/v1/hotel/attendance/",
        ):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class PostedOrderCorrectionTests(APITestCase, ServicesMixin):
    """Folio closure round: correcting a POSTED order is finance-side —
    void inside the charge's open business date, a linked adjustment after.
    The order itself stays posted (posted_charge is the permanent reference)
    and can never be posted twice."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.make_catalog()
        self.stay = make_stay(self.hotel)

    def _posted_charge(self):
        oid = self.create_order(
            stay=self.stay.id,
            items=[{"service_item": self.item.id, "quantity": "1"}],
        ).data["id"]
        self.deliver(oid)
        res = self.post_order(oid)
        return oid, FolioCharge.objects.get(pk=res.data["posted_charge"])

    def test_same_day_correction_is_void(self):
        oid, charge = self._posted_charge()
        r = self.client.post(
            reverse("finance:charge-void", args=[charge.id]),
            {"reason": "wrong order"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        charge.refresh_from_db()
        self.assertEqual(charge.status, "voided")
        # The order remains posted and can never be posted again.
        again = self.post_order(oid)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["code"], "order_already_posted")

    def test_after_window_correction_is_adjustment(self):
        from datetime import timedelta

        from apps.shifts.services import get_business_date

        oid, charge = self._posted_charge()
        FolioCharge.objects.filter(pk=charge.pk).update(
            charge_date=get_business_date(self.hotel) - timedelta(days=1)
        )
        # Void is now refused...
        void = self.client.post(
            reverse("finance:charge-void", args=[charge.id]),
            {"reason": "late"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(void.status_code, 409)
        self.assertEqual(void.data["code"], "void_window_closed")
        # ...the correction is a linked full adjustment.
        adj = self.client.post(
            reverse("finance:charge-adjust", args=[charge.id]),
            {"reason": "order served to wrong room"}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(adj.status_code, 201)
        adjustment = FolioCharge.objects.get(adjusts=charge)
        self.assertEqual(adjustment.total_amount, -charge.total_amount)
        charge.refresh_from_db()
        self.assertEqual(charge.status, "posted")
        self.assertEqual(str(folio_balance(charge.folio)["balance"]), "0.00")
        # The order still points at its original charge.
        again = self.post_order(oid)
        self.assertEqual(again.status_code, 409)


# --------------------------------------------------------------------------- #
# Restaurant & café final closure                                              #
# --------------------------------------------------------------------------- #

from unittest import mock

from apps.finance.models import Payment
from apps.hotels.models import HotelSettings
from apps.notifications.models import ActivityEvent
from apps.services.models import RestaurantTable
from apps.stays.models import StayStatus


class ClosureBase(APITestCase, ServicesMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.make_catalog()
        self.stay = make_stay(self.hotel)

    def settle_direct(self, oid, method="cash", hotel=None):
        return self.client.post(
            reverse("services:order-settle-direct", args=[oid]),
            {"method": method}, format="json", **HDR(hotel or self.hotel),
        )

    def cancel_item(self, oid, item_id, reason="wrong item"):
        return self.client.post(
            reverse("services:order-item-cancel", args=[oid, item_id]),
            {"reason": reason}, format="json", **HDR(self.hotel),
        )


class InHouseGuardTests(ClosureBase):
    """P0: no new operational-financial relation for a non-in-house stay."""

    def _depart(self):
        Stay.objects.filter(pk=self.stay.pk).update(
            status=StayStatus.CHECKED_OUT, actual_check_out_at=timezone.now()
        )

    def test_room_order_requires_in_house_stay(self):
        self._depart()
        res = self.create_order(stay=self.stay.id)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "stay_not_in_house")

    def test_table_order_stay_link_requires_in_house(self):
        self._depart()
        res = self.create_order(
            order_type="table", table=self.make_table().id, stay=self.stay.id
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "stay_not_in_house")

    def test_posting_refused_after_departure(self):
        oid = self.create_order(stay=self.stay.id).data["id"]
        self.deliver(oid)
        self._depart()
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "stay_not_in_house")
        self.assertFalse(ServiceOrder.objects.get(pk=oid).is_posted)

    def test_ensure_stay_folio_guard(self):
        from apps.common.exceptions import StayNotInHouse
        from apps.finance.services import ensure_stay_folio

        self._depart()
        with self.assertRaises(StayNotInHouse):
            ensure_stay_folio(self.stay)

    def test_room_order_still_fine_in_house(self):
        res = self.create_order(stay=self.stay.id)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["order_type"], "room")
        self.assertEqual(res.data["room_number"], self.stay.room.number)


class OutletFlagTests(ClosureBase):
    def _disable_cafe(self):
        HotelSettings.objects.update_or_create(
            hotel=self.hotel, defaults={"cafe_enabled": False}
        )

    def test_disabled_outlet_blocks_new_order(self):
        self._disable_cafe()
        cafe_cat = make_category(self.hotel, name="Cafe menu", outlet="cafe")
        cafe_item = make_item(self.hotel, cafe_cat, name="Latte", price="8.00", tax="0.00")
        res = self.create_order(
            order_type="table", outlet="cafe",
            table=self.make_table(outlet="cafe").id,
            items=[{"service_item": cafe_item.id, "quantity": "1"}],
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "outlet_disabled")

    def test_disabled_outlet_blocks_new_table_and_catalog(self):
        self._disable_cafe()
        table = self.client.post(
            reverse("services:table-list"),
            {"outlet": "cafe", "number": "C1"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(table.status_code, 409)
        self.assertEqual(table.data["code"], "outlet_disabled")
        cat = self.client.post(
            reverse("services:category-list"),
            {"name": "Cafe menu", "outlet": "cafe"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(cat.status_code, 409)
        cafe_cat = make_category(self.hotel, name="Old cafe", outlet="cafe")
        item = self.client.post(
            reverse("services:item-list"),
            {"category": cafe_cat.id, "name": "Latte", "unit_price": "8.00"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(item.status_code, 409)

    def test_disabled_outlet_data_still_readable(self):
        cafe_cat = make_category(self.hotel, name="Old cafe", outlet="cafe")
        self._disable_cafe()
        res = self.client.get(
            reverse("services:category-list"), {"outlet": "cafe"}, **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)

    def test_restaurant_unaffected_by_cafe_flag(self):
        self._disable_cafe()
        self.assertEqual(self.create_order().status_code, 201)


class TableTests(ClosureBase):
    def test_create_and_unique_per_outlet(self):
        res = self.client.post(
            reverse("services:table-list"),
            {"outlet": "restaurant", "number": "R1", "capacity": 4},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)
        dup = self.client.post(
            reverse("services:table-list"),
            {"outlet": "restaurant", "number": "R1"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(dup.status_code, 400)
        # Same number on the OTHER outlet is fine.
        ok = self.client.post(
            reverse("services:table-list"),
            {"outlet": "cafe", "number": "R1"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(ok.status_code, 201)

    def test_occupied_is_derived_in_list(self):
        table = self.make_table()
        self.create_order(order_type="table", table=table.id)
        res = self.client.get(reverse("services:table-list"), **HDR(self.hotel))
        row = next(r for r in res.data["results"] if r["id"] == table.id)
        self.assertTrue(row["is_occupied"])
        self.assertEqual(row["open_order"]["order_number"], "ORD00001")

    def test_out_of_service_requires_note_and_no_open_order(self):
        table = self.make_table()
        no_note = self.client.post(
            reverse("services:table-status", args=[table.id]),
            {"status": "out_of_service"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(no_note.status_code, 400)
        self.create_order(order_type="table", table=table.id)
        busy = self.client.post(
            reverse("services:table-status", args=[table.id]),
            {"status": "out_of_service", "note": "broken"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(busy.status_code, 409)
        self.assertEqual(busy.data["code"], "table_has_open_order")

    def test_oos_table_refuses_orders_and_returns(self):
        table = self.make_table()
        self.client.post(
            reverse("services:table-status", args=[table.id]),
            {"status": "out_of_service", "note": "paint"},
            format="json", **HDR(self.hotel),
        )
        res = self.create_order(order_type="table", table=table.id)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "table_out_of_service")
        back = self.client.post(
            reverse("services:table-status", args=[table.id]),
            {"status": "available"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(back.status_code, 200)
        self.assertEqual(self.create_order(order_type="table", table=table.id).status_code, 201)

    def test_one_open_order_per_table(self):
        table = self.make_table()
        self.assertEqual(self.create_order(order_type="table", table=table.id).status_code, 201)
        second = self.create_order(order_type="table", table=table.id)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data["code"], "table_occupied")

    def test_db_backstop_unique_open_order(self):
        from django.db import IntegrityError, transaction as db_tx

        table = self.make_table()
        oid = self.create_order(order_type="table", table=table.id).data["id"]
        with self.assertRaises(IntegrityError):
            with db_tx.atomic():
                ServiceOrder.objects.create(
                    hotel=self.hotel, order_number="ORDX9999", order_type="table",
                    outlet="restaurant", table=table, ordered_at=timezone.now(),
                )

    def test_cancel_frees_table(self):
        table = self.make_table()
        oid = self.create_order(order_type="table", table=table.id).data["id"]
        self.client.post(
            reverse("services:order-cancel", args=[oid]),
            {"reason": "left"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(self.create_order(order_type="table", table=table.id).status_code, 201)

    def test_used_table_delete_refused(self):
        table = self.make_table()
        self.create_order(order_type="table", table=table.id)
        res = self.client.delete(
            reverse("services:table-detail", args=[table.id]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "resource_in_use")
        fresh = self.make_table()
        self.assertEqual(
            self.client.delete(
                reverse("services:table-detail", args=[fresh.id]), **HDR(self.hotel)
            ).status_code,
            204,
        )

    def test_tables_manage_permission(self):
        staff = add_member(self.hotel, "tv@x.com", perms=["services.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("services:table-list"), **HDR(self.hotel)).status_code,
            200,
        )
        res = self.client.post(
            reverse("services:table-list"),
            {"outlet": "restaurant", "number": "P1"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 403)
        mgr = add_member(self.hotel, "tm@x.com", perms=["services.tables_manage"])
        self.client.force_authenticate(mgr)
        res = self.client.post(
            reverse("services:table-list"),
            {"outlet": "restaurant", "number": "P1"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)

    def test_cross_hotel_table_isolated(self):
        other = make_hotel(slug="o")
        foreign = self.make_table(hotel=other)
        res = self.create_order(order_type="table", table=foreign.id)
        self.assertEqual(res.status_code, 404)


class TableOrderTests(ClosureBase):
    def test_table_required_and_room_shape(self):
        res = self.create_order(order_type="table", table=None)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_order_composition")
        res = self.create_order(stay=self.stay.id, table=self.make_table().id)
        self.assertEqual(res.status_code, 400)  # room order takes no table

    def test_outlet_table_mismatch_refused(self):
        cafe_table = self.make_table(outlet="cafe")
        res = self.create_order(order_type="table", table=cafe_table.id)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_order_composition")

    def test_item_outlet_mismatch_refused(self):
        cafe_cat = make_category(self.hotel, name="Cafe menu", outlet="cafe")
        cafe_item = make_item(self.hotel, cafe_cat, name="Latte", price="8.00")
        res = self.create_order(
            order_type="table", table=self.make_table().id,
            items=[{"service_item": cafe_item.id, "quantity": "1"}],
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "outlet_mismatch")

    def test_external_customer_name_only(self):
        res = self.create_order(
            order_type="table", table=self.make_table().id,
            customer_name="Walk-in Ali",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["customer_name"], "Walk-in Ali")
        self.assertIsNone(res.data["stay"])

    def test_guest_table_order_postable(self):
        res = self.create_order(
            order_type="table", table=self.make_table().id, stay=self.stay.id
        )
        oid = res.data["id"]
        self.deliver(oid)
        self.assertEqual(self.post_order(oid).status_code, 200)

    def test_external_table_order_not_postable(self):
        oid = self.create_order(
            order_type="table", table=self.make_table().id,
            customer_name="Walk-in",
        ).data["id"]
        self.deliver(oid)
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["details"]["reason"], "no_folio")

    def test_shape_immutable_after_creation(self):
        oid = self.create_order(order_type="table", table=self.make_table().id).data["id"]
        for payload in (
            {"order_type": "room"}, {"outlet": "cafe"}, {"table": 999},
            {"stay": self.stay.id}, {"source": "cafe"},
            {"customer_name": "X"}, {"business_date": "2020-01-01"},
        ):
            res = self.client.patch(
                reverse("services:order-detail", args=[oid]),
                payload, format="json", **HDR(self.hotel),
            )
            self.assertEqual(res.status_code, 400, payload)

    def test_create_rejects_backend_fields(self):
        res = self.create_order(business_date="2020-01-01")
        self.assertEqual(res.status_code, 400)
        res = self.create_order(source="cafe")
        self.assertEqual(res.status_code, 400)


class DirectSettlementTests(ClosureBase):
    def _delivered(self, **kw):
        res = self.create_order(**kw)
        oid = res.data["id"]
        self.deliver(oid)
        return oid

    def test_full_cycle_transient_folio(self):
        oid = self._delivered(customer_name="Walk-in Ali")
        res = self.settle_direct(oid, method="cash")
        self.assertEqual(res.status_code, 200)
        data = res.data
        self.assertEqual(data["settlement"], "direct")
        self.assertIsNotNone(data["settled_at"])
        self.assertTrue(data["settlement_receipt"].startswith("RCP"))
        folio = Folio.objects.get(pk=data["folio"])
        self.assertEqual(folio.status, FolioStatus.CLOSED)
        self.assertIsNone(folio.stay)
        self.assertIsNone(folio.reservation)
        self.assertEqual(folio.customer_name, "Walk-in Ali")
        self.assertEqual(str(folio_balance(folio)["balance"]), "0.00")
        payment = Payment.objects.get(pk=data["settlement_payment"])
        self.assertEqual(str(payment.amount), "88.00")
        charge = FolioCharge.objects.get(pk=data["posted_charge"])
        self.assertEqual(str(charge.total_amount), "88.00")
        # Operational status untouched by settlement; posted_at stays folio-path only.
        self.assertEqual(data["status"], "delivered")
        self.assertFalse(data["is_posted"])

    def test_requires_delivered(self):
        oid = self.create_order().data["id"]
        res = self.settle_direct(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_not_postable")

    def test_xor_paid_order_cannot_be_posted(self):
        oid = self._delivered(stay=self.stay.id)
        self.assertEqual(self.settle_direct(oid).status_code, 200)
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertIn(res.data["code"], ("order_already_posted", "order_already_settled"))

    def test_xor_posted_order_cannot_be_paid(self):
        oid = self._delivered(stay=self.stay.id)
        self.assertEqual(self.post_order(oid).status_code, 200)
        res = self.settle_direct(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_already_posted")

    def test_double_direct_refused(self):
        oid = self._delivered()
        self.assertEqual(self.settle_direct(oid).status_code, 200)
        res = self.settle_direct(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_already_settled")

    def test_settled_order_cannot_be_cancelled_or_edited(self):
        oid = self._delivered()
        self.settle_direct(oid)
        cancel = self.client.post(
            reverse("services:order-cancel", args=[oid]),
            {"reason": "x"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(cancel.status_code, 409)
        patch = self.client.patch(
            reverse("services:order-detail", args=[oid]),
            {"notes": "late"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(patch.status_code, 409)

    def test_rollback_on_payment_failure(self):
        oid = self._delivered()
        folios_before = Folio.objects.count()
        with mock.patch(
            "apps.finance.services.record_payment",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self.settle_direct(oid)
        order = ServiceOrder.objects.get(pk=oid)
        self.assertEqual(order.settlement, "unsettled")
        self.assertIsNone(order.folio)
        self.assertEqual(Folio.objects.count(), folios_before)

    def test_payment_joins_open_shift_drawer(self):
        from apps.shifts.services import open_shift

        shift = open_shift(self.hotel, user=self.manager, opening_cash_amount="0.00")
        oid = self._delivered()
        res = self.settle_direct(oid, method="cash")
        payment = Payment.objects.get(pk=res.data["settlement_payment"])
        self.assertEqual(payment.shift_id, shift.id)

    def test_settle_frees_table_for_next_order(self):
        table = self.make_table()
        oid = self._delivered(order_type="table", table=table.id)
        self.settle_direct(oid)
        self.assertEqual(
            self.create_order(order_type="table", table=table.id).status_code, 201
        )

    def test_settle_direct_permission(self):
        oid = self._delivered()
        staff = add_member(
            self.hotel, "sd@x.com",
            perms=["service_orders.view", "service_orders.post_to_folio"],
        )
        self.client.force_authenticate(staff)
        self.assertEqual(self.settle_direct(oid).status_code, 403)
        payer = add_member(self.hotel, "sp@x.com", perms=["service_orders.settle_direct"])
        self.client.force_authenticate(payer)
        self.assertEqual(self.settle_direct(oid).status_code, 200)

    def test_receipt_reprintable_via_finance(self):
        oid = self._delivered()
        res = self.settle_direct(oid)
        receipt = self.client.get(
            reverse("finance:payment-receipt", args=[res.data["settlement_payment"]]),
            **HDR(self.hotel),
        )
        # Needs finance.view — the manager inherits it.
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.data["document"], "receipt")


class ItemCancelTests(ClosureBase):
    def _order_two_lines(self, **kw):
        res = self.create_order(
            items=[
                {"service_item": self.item.id, "quantity": "2"},   # 88.00
                {"service_item": self.item2.id, "quantity": "1"},  # 10.00
            ],
            **kw,
        )
        oid = res.data["id"]
        items = res.data["items"]
        return oid, items

    def test_cancel_requires_reason_and_excludes_from_totals(self):
        oid, items = self._order_two_lines()
        no_reason = self.client.post(
            reverse("services:order-item-cancel", args=[oid, items[0]["id"]]),
            {}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(no_reason.status_code, 400)
        res = self.cancel_item(oid, items[0]["id"])
        self.assertEqual(res.status_code, 200)
        line = next(i for i in res.data["items"] if i["id"] == items[0]["id"])
        self.assertTrue(line["is_cancelled"])
        self.assertEqual(line["cancel_reason"], "wrong item")
        self.assertEqual(line["unit_price"], "40.00")   # snapshot kept
        self.assertEqual(res.data["totals"]["total"], "10.00")

    def test_settlement_uses_reduced_total(self):
        oid, items = self._order_two_lines()
        self.cancel_item(oid, items[0]["id"])
        self.deliver(oid)
        res = self.settle_direct(oid)
        payment = Payment.objects.get(pk=res.data["settlement_payment"])
        self.assertEqual(str(payment.amount), "10.00")

    def test_last_active_item_not_cancellable(self):
        oid, items = self._order_two_lines()
        self.cancel_item(oid, items[0]["id"])
        res = self.cancel_item(oid, items[1]["id"])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "last_active_item_not_cancellable")

    def test_no_cancel_after_settlement(self):
        oid, items = self._order_two_lines()
        self.deliver(oid)
        self.settle_direct(oid)
        res = self.cancel_item(oid, items[0]["id"])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_already_settled")

    def test_kot_excludes_cancelled_lines(self):
        oid, items = self._order_two_lines()
        self.cancel_item(oid, items[0]["id"])
        res = self.client.get(
            reverse("services:order-ticket", args=[oid]), **HDR(self.hotel)
        )
        self.assertEqual(len(res.data["items"]), 1)


class BusinessDateTests(ClosureBase):
    def test_stamped_from_hotel_business_date(self):
        from apps.shifts.services import get_business_date

        res = self.create_order()
        self.assertEqual(res.data["business_date"], str(get_business_date(self.hotel)))

    def test_overview_uses_business_date(self):
        self.create_order()
        res = self.client.get(reverse("services:overview"), **HDR(self.hotel))
        self.assertEqual(res.data["orders_today"], 1)
        self.assertIn("paid_direct_today_total", res.data)
        self.assertIn("delivered_not_settled", res.data)

    def test_date_filter_uses_business_date(self):
        from apps.shifts.services import get_business_date

        self.create_order()
        res = self.client.get(
            reverse("services:order-list"),
            {"date": str(get_business_date(self.hotel))}, **HDR(self.hotel),
        )
        self.assertEqual(res.data["count"], 1)


class ClosureActivityTests(ClosureBase):
    def _types(self):
        return set(
            ActivityEvent.objects.filter(hotel=self.hotel).values_list(
                "event_type", flat=True
            )
        )

    def test_all_nine_events_recorded(self):
        table = self.make_table()
        res = self.create_order(order_type="table", table=table.id,
                                items=[
                                    {"service_item": self.item.id, "quantity": "1"},
                                    {"service_item": self.item2.id, "quantity": "1"},
                                ])
        oid = res.data["id"]
        self.cancel_item(oid, res.data["items"][0]["id"])
        self.deliver(oid)
        self.settle_direct(oid)
        # Folio-path + cancel + table events on other objects:
        room_oid = self.create_order(stay=self.stay.id).data["id"]
        self.deliver(room_oid)
        self.post_order(room_oid)
        c_oid = self.create_order().data["id"]
        self.client.post(
            reverse("services:order-cancel", args=[c_oid]),
            {"reason": "left"}, format="json", **HDR(self.hotel),
        )
        t2 = self.make_table()
        self.client.post(
            reverse("services:table-status", args=[t2.id]),
            {"status": "out_of_service", "note": "broken"},
            format="json", **HDR(self.hotel),
        )
        self.client.post(
            reverse("services:table-status", args=[t2.id]),
            {"status": "available"}, format="json", **HDR(self.hotel),
        )
        # Draft items_updated:
        d_oid = self.create_order(status="draft").data["id"]
        self.client.patch(
            reverse("services:order-detail", args=[d_oid]),
            {"items": [{"service_item": self.item2.id, "quantity": "1"}]},
            format="json", **HDR(self.hotel),
        )
        expected = {
            "service_order.created", "service_order.items_updated",
            "service_order.item_cancelled", "service_order.cancelled",
            "service_order.status_changed", "service_order.paid_direct",
            "service_order.posted_to_folio",
            "table.out_of_service", "table.back_in_service",
        }
        missing = expected - self._types()
        self.assertFalse(missing, missing)


# --------------------------------------------------------------------------- #
# Restaurant/café OPERATIONAL CLOSURE — currency, cash capture, idempotency,    #
# returns & exchanges                                                          #
# --------------------------------------------------------------------------- #

from apps.finance.models import ChargeType, PaymentMethod
from apps.finance.services import create_folio as _create_folio
from apps.services.models import (
    OrderSettlement,
    ReturnKind,
    ServiceOrderItem as _ServiceOrderItem,
    ServiceOrderReturn,
    ServiceOrderReturnItem,
)


class CurrencyMatchTests(ClosureBase):
    """D1a — the base currency is the single service currency (no FX)."""

    def test_order_and_lines_snapshot_base_currency(self):
        res = self.create_order(stay=self.stay.id)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["currency"], "USD")
        self.assertTrue(all(i["currency"] == "USD" for i in res.data["items"]))
        order = ServiceOrder.objects.get(pk=res.data["id"])
        self.assertEqual(order.currency, "USD")
        self.assertTrue(
            all(li.currency == "USD" for li in order.items.all())
        )

    def test_item_in_foreign_currency_rejected_on_create(self):
        # An item explicitly saved in a non-base currency is refused (no FX).
        self.item.currency = "EUR"
        self.item.save(update_fields=["currency"])
        res = self.create_order(stay=self.stay.id)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "currency_mismatch")
        self.assertEqual(ServiceOrder.objects.count(), 0)

    def test_empty_item_currency_normalized_to_base(self):
        # The catalog item currency is blank (the historically-dead field) — it is
        # normalized to the base and snapshotted, never rejected.
        self.assertEqual(self.item.currency, "")
        res = self.create_order(stay=self.stay.id)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["items"][0]["currency"], "USD")

    def test_post_to_folio_currency_mismatch_rejected(self):
        # The stay's folio carries a DIFFERENT (agreed) currency than the order's
        # base — posting must reject rather than silently FX-convert.
        _create_folio(
            self.hotel, stay=self.stay, guest=self.stay.primary_guest,
            agreed_currency="EUR",
        )
        oid = self.create_order(stay=self.stay.id).data["id"]
        self.deliver(oid)
        res = self.post_order(oid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "folio_currency_mismatch")
        # No charge posted, order still unsettled.
        self.assertEqual(FolioCharge.objects.count(), 0)
        self.assertEqual(
            ServiceOrder.objects.get(pk=oid).settlement, OrderSettlement.UNSETTLED
        )


class DirectSettlementCaptureTests(ClosureBase):
    """D2a — capture amount_received + change (services-side); the Payment stays
    the exact total."""

    def _delivered(self, **kw):
        oid = self.create_order(**kw).data["id"]
        self.deliver(oid)
        return oid

    def _settle(self, oid, **body):
        body.setdefault("method", "cash")
        return self.client.post(
            reverse("services:order-settle-direct", args=[oid]),
            body, format="json", **HDR(self.hotel),
        )

    def test_records_received_and_change(self):
        oid = self._delivered()  # 88.00 order
        res = self._settle(
            oid, amount_received="100.00", reference="TXN-9",
        )
        self.assertEqual(res.status_code, 200)
        order = ServiceOrder.objects.get(pk=oid)
        self.assertEqual(str(order.amount_received), "100.00")
        self.assertEqual(str(order.change_given), "12.00")
        self.assertEqual(order.settlement_reference, "TXN-9")
        self.assertEqual(order.settlement_method, "cash")
        # The finance Payment records the EXACT total, not the tender.
        payment = Payment.objects.get(pk=order.settlement_payment_id)
        self.assertEqual(str(payment.amount), "88.00")
        self.assertEqual(payment.reference, "TXN-9")

    def test_short_cash_tender_rejected_with_no_side_effect(self):
        oid = self._delivered()
        folios_before = Folio.objects.count()
        res = self._settle(oid, amount_received="50.00")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "insufficient_cash_received")
        order = ServiceOrder.objects.get(pk=oid)
        self.assertEqual(order.settlement, OrderSettlement.UNSETTLED)
        self.assertIsNone(order.amount_received)
        self.assertEqual(Folio.objects.count(), folios_before)
        self.assertEqual(Payment.objects.count(), 0)

    def test_electronic_without_received_ok(self):
        oid = self._delivered()
        res = self._settle(oid, method="card")
        self.assertEqual(res.status_code, 200)
        order = ServiceOrder.objects.get(pk=oid)
        self.assertIsNone(order.amount_received)
        self.assertIsNone(order.change_given)
        self.assertEqual(order.settlement_method, "card")
        self.assertEqual(
            str(Payment.objects.get(pk=order.settlement_payment_id).amount), "88.00"
        )


class SettleIdempotencyTests(ClosureBase):
    """D5 — settle-direct + post-to-folio idempotency."""

    def _delivered(self, **kw):
        kw.setdefault("stay", self.stay.id)
        oid = self.create_order(**kw).data["id"]
        self.deliver(oid)
        return oid

    def _settle(self, oid, **body):
        body.setdefault("method", "cash")
        return self.client.post(
            reverse("services:order-settle-direct", args=[oid]),
            body, format="json", **HDR(self.hotel),
        )

    def test_same_key_same_body_moves_money_once(self):
        oid = self._delivered()
        first = self._settle(oid, idempotency_key="K1", amount_received="100.00")
        self.assertEqual(first.status_code, 200)
        second = self._settle(oid, idempotency_key="K1", amount_received="100.00")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        # Exactly ONE payment / ONE transient folio despite the replay.
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(
            Folio.objects.filter(service_orders__id=oid).count(), 1
        )

    def test_same_key_different_body_conflicts_no_side_effect(self):
        oid = self._delivered()
        self.assertEqual(
            self._settle(oid, idempotency_key="K2", amount_received="100.00").status_code,
            200,
        )
        payments_before = Payment.objects.count()
        conflict = self._settle(oid, idempotency_key="K2", amount_received="90.00")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "idempotency_key_conflict")
        self.assertEqual(Payment.objects.count(), payments_before)

    def test_folio_post_idempotent_same_key(self):
        oid = self._delivered()
        r1 = self.client.post(
            reverse("services:order-post-to-folio", args=[oid]),
            {"idempotency_key": "P1"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(
            reverse("services:order-post-to-folio", args=[oid]),
            {"idempotency_key": "P1"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r2.status_code, 200)
        # One service charge only (the replay returned the same order).
        self.assertEqual(
            FolioCharge.objects.filter(source="service_order").count(), 1
        )


class ReturnBase(ClosureBase):
    """Helpers for return/exchange tests. The manager inherits finance.refund."""

    def _return(self, oid, *, kind="return", items, reason="customer changed mind",
                method=None, amount_received=None, reference="", idempotency_key="",
                hotel=None):
        body = {"kind": kind, "reason": reason, "items": items}
        if method:
            body["method"] = method
        if amount_received is not None:
            body["amount_received"] = amount_received
        if reference:
            body["reference"] = reference
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return self.client.post(
            reverse("services:order-return", args=[oid]),
            body, format="json", **HDR(hotel or self.hotel),
        )

    def _folio_order(self, **kw):
        """A delivered order posted to the stay's OPEN folio (FOLIO settlement)."""
        kw.setdefault("stay", self.stay.id)
        res = self.create_order(**kw)
        oid = res.data["id"]
        lines = res.data["items"]
        self.deliver(oid)
        self.assertEqual(self.post_order(oid).status_code, 200)
        return oid, lines

    def _direct_order(self, **kw):
        res = self.create_order(**kw)
        oid = res.data["id"]
        lines = res.data["items"]
        self.deliver(oid)
        self.assertEqual(self.settle_direct(oid).status_code, 200)
        return oid, lines


class RoomReturnTests(ReturnBase):
    """D3a — a ROOM (settlement=FOLIO) return counter-posts a credit on the
    guest's OPEN folio (reuse of finance ``add_charge`` in its reversal shape).
    See the report: a partial/repeatable proportional credit — void_charge /
    adjust_charge are whole-charge, once-only, and cannot express it."""

    def test_full_return_credits_open_folio(self):
        oid, lines = self._folio_order()  # 88.00
        order = ServiceOrder.objects.get(pk=oid)
        folio_id = order.folio_id
        self.assertEqual(str(folio_balance(order.folio)["balance"]), "88.00")
        res = self._return(
            oid, items=[{"original_item": lines[0]["id"], "quantity": "2"}]
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        # A credit ADJUSTMENT counter-charge on the SAME open folio.
        credit = FolioCharge.objects.get(pk=ret.reversal_charge_id)
        self.assertEqual(credit.folio_id, folio_id)
        self.assertEqual(credit.type, ChargeType.ADJUSTMENT)
        self.assertEqual(credit.source, "order_return")
        self.assertEqual(str(credit.total_amount), "-88.00")
        self.assertEqual(credit.status, PostingStatus.POSTED)
        # Folio balance net to zero — the returned amount matches to the cent.
        self.assertEqual(
            str(folio_balance(Folio.objects.get(pk=folio_id))["balance"]), "0.00"
        )
        # Append-only + void-not-delete: the ORIGINAL posted charge is untouched.
        order.refresh_from_db()
        self.assertEqual(order.settlement, OrderSettlement.FOLIO)
        self.assertEqual(
            FolioCharge.objects.get(pk=order.posted_charge_id).status,
            PostingStatus.POSTED,
        )
        self.assertEqual(ServiceOrderReturnItem.objects.filter(service_return=ret).count(), 1)

    def test_return_when_guest_folio_closed_uses_transient_refund(self):
        # Owner ruling: a ROOM return on a checked-out guest whose folio is CLOSED
        # must NOT be refused — it refunds via a NEW transient folio (like DIRECT),
        # leaving the original closed folio untouched.
        from apps.finance.services import close_folio, record_payment

        oid, lines = self._folio_order()  # 88.00 posted to the guest's OPEN folio
        order = ServiceOrder.objects.get(pk=oid)
        guest_folio = Folio.objects.get(pk=order.folio_id)
        # Simulate the guest checking out: settle + CLOSE the guest folio.
        record_payment(
            guest_folio, amount=Decimal("88.00"), method="cash", user=self.manager
        )
        close_folio(guest_folio, user=self.manager)
        guest_folio.refresh_from_db()
        self.assertEqual(guest_folio.status, FolioStatus.CLOSED)
        guest_charges_before = list(
            FolioCharge.objects.filter(folio=guest_folio)
            .order_by("id")
            .values_list("pk", "total_amount", "status")
        )

        res = self._return(
            oid, items=[{"original_item": lines[0]["id"], "quantity": "2"}],
            method="cash",
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        # A NEW transient refund folio — NOT the guest's closed folio.
        self.assertIsNotNone(ret.refund_folio_id)
        self.assertNotEqual(ret.refund_folio_id, guest_folio.id)
        refund_folio = Folio.objects.get(pk=ret.refund_folio_id)
        self.assertEqual(refund_folio.status, FolioStatus.CLOSED)
        self.assertEqual(str(folio_balance(refund_folio)["balance"]), "0.00")
        self.assertEqual(
            str(Payment.objects.get(pk=ret.refund_payment_id).amount), "-88.00"
        )
        credit = FolioCharge.objects.get(pk=ret.reversal_charge_id)
        self.assertEqual(credit.folio_id, refund_folio.id)
        self.assertEqual(str(credit.total_amount), "-88.00")
        # The ORIGINAL closed guest folio is byte-for-byte untouched (append-only).
        guest_folio.refresh_from_db()
        self.assertEqual(guest_folio.status, FolioStatus.CLOSED)
        self.assertEqual(str(folio_balance(guest_folio)["balance"]), "0.00")
        self.assertEqual(
            list(
                FolioCharge.objects.filter(folio=guest_folio)
                .order_by("id")
                .values_list("pk", "total_amount", "status")
            ),
            guest_charges_before,
        )
        order.refresh_from_db()
        self.assertEqual(order.settlement, OrderSettlement.FOLIO)

    def test_partial_then_exceed_remaining(self):
        oid, lines = self._folio_order()  # item x2
        line_id = lines[0]["id"]
        first = self._return(oid, items=[{"original_item": line_id, "quantity": "1"}])
        self.assertEqual(first.status_code, 201)
        credit = FolioCharge.objects.get(
            pk=first.data["return"]["reversal_charge"]
        )
        self.assertEqual(str(credit.total_amount), "-44.00")
        # A second return of the remaining 1 is allowed.
        second = self._return(oid, items=[{"original_item": line_id, "quantity": "1"}])
        self.assertEqual(second.status_code, 201)
        # A third exceeds what remains.
        third = self._return(oid, items=[{"original_item": line_id, "quantity": "1"}])
        self.assertEqual(third.status_code, 400)
        self.assertEqual(third.data["code"], "invalid_return_composition")

    def test_return_requires_delivered_and_settled(self):
        oid = self.create_order(stay=self.stay.id).data["id"]
        line = ServiceOrder.objects.get(pk=oid).items.first()
        res = self._return(oid, items=[{"original_item": line.id, "quantity": "1"}])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "order_not_returnable")

    def test_reason_required(self):
        oid, lines = self._folio_order()
        res = self._return(
            oid, items=[{"original_item": lines[0]["id"], "quantity": "1"}], reason=" "
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "return_reason_required")

    def test_permission_finance_refund_required(self):
        oid, lines = self._folio_order()
        body_items = [{"original_item": lines[0]["id"], "quantity": "1"}]
        staff = add_member(
            self.hotel, "noref@x.com",
            perms=["service_orders.view", "service_orders.post_to_folio"],
        )
        self.client.force_authenticate(staff)
        self.assertEqual(
            self._return(oid, items=body_items).status_code, 403
        )
        refunder = add_member(self.hotel, "ref@x.com", perms=["finance.refund"])
        self.client.force_authenticate(refunder)
        self.assertEqual(self._return(oid, items=body_items).status_code, 201)


class DirectReturnTests(ReturnBase):
    """D3a — a DIRECT return opens a NEW transient refund folio + a NEGATIVE
    payment; the ORIGINAL closed folio is never reopened or altered."""

    def test_new_refund_folio_negative_payment_original_untouched(self):
        oid, lines = self._direct_order()  # 88.00, transient folio closed
        order = ServiceOrder.objects.get(pk=oid)
        original_folio = Folio.objects.get(pk=order.folio_id)
        original_charge = FolioCharge.objects.get(pk=order.posted_charge_id)
        original_payment = Payment.objects.get(pk=order.settlement_payment_id)
        self.assertEqual(original_folio.status, FolioStatus.CLOSED)

        res = self._return(
            oid, items=[{"original_item": lines[0]["id"], "quantity": "2"}],
            method="cash",
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        # A NEW transient refund folio, closed at zero.
        self.assertIsNotNone(ret.refund_folio_id)
        self.assertNotEqual(ret.refund_folio_id, original_folio.id)
        refund_folio = Folio.objects.get(pk=ret.refund_folio_id)
        self.assertEqual(refund_folio.status, FolioStatus.CLOSED)
        self.assertEqual(str(folio_balance(refund_folio)["balance"]), "0.00")
        # A NEGATIVE payment (money out) for the returned amount.
        refund_payment = Payment.objects.get(pk=ret.refund_payment_id)
        self.assertEqual(str(refund_payment.amount), "-88.00")
        # The credit reversal charge lives on the NEW folio (not the original).
        credit = FolioCharge.objects.get(pk=ret.reversal_charge_id)
        self.assertEqual(credit.folio_id, refund_folio.id)
        self.assertEqual(str(credit.total_amount), "-88.00")

        # The ORIGINAL closed folio is byte-for-byte untouched.
        original_folio.refresh_from_db()
        original_charge.refresh_from_db()
        original_payment.refresh_from_db()
        self.assertEqual(original_folio.status, FolioStatus.CLOSED)
        self.assertEqual(str(original_charge.total_amount), "88.00")
        self.assertEqual(original_charge.status, PostingStatus.POSTED)
        self.assertEqual(str(original_payment.amount), "88.00")
        self.assertEqual(
            str(folio_balance(original_folio)["balance"]), "0.00"
        )
        # XOR still holds: the order is still DIRECT-settled.
        order.refresh_from_db()
        self.assertEqual(order.settlement, OrderSettlement.DIRECT)


class ExchangeTests(ReturnBase):
    """D3a — exchanges move ONLY the net delta; snapshots are frozen."""

    def test_exchange_same_no_money(self):
        oid, lines = self._folio_order()  # item x2 = 88 on the folio
        order = ServiceOrder.objects.get(pk=oid)
        charges_before = FolioCharge.objects.filter(folio=order.folio).count()
        res = self._return(
            oid, kind="exchange_same",
            items=[{
                "original_item": lines[0]["id"], "quantity": "1",
                "replacement_item": self.item.id, "replacement_quantity": "1",
            }],
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        self.assertIsNone(ret.delta_charge_id)
        self.assertIsNone(ret.delta_payment_id)
        # No new charge on the folio; the snapshot records both legs.
        self.assertEqual(
            FolioCharge.objects.filter(folio=order.folio).count(), charges_before
        )
        item = ServiceOrderReturnItem.objects.get(service_return=ret)
        self.assertEqual(item.replacement_item_id, self.item.id)
        self.assertEqual(str(item.replacement_total_amount), "44.00")

    def test_exchange_higher_collects_delta_on_folio(self):
        # Order a Tea (10) posted to the folio, then exchange it for a Burger (44).
        oid, lines = self._folio_order(
            items=[{"service_item": self.item2.id, "quantity": "1"}]
        )
        order = ServiceOrder.objects.get(pk=oid)
        res = self._return(
            oid, kind="exchange_higher",
            items=[{
                "original_item": lines[0]["id"], "quantity": "1",
                "replacement_item": self.item.id, "replacement_quantity": "1",
            }],
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        delta = FolioCharge.objects.get(pk=ret.delta_charge_id)
        self.assertEqual(delta.type, ChargeType.SERVICE)
        self.assertEqual(str(delta.total_amount), "34.00")
        # Folio now reflects the Burger's value (10 original + 34 delta).
        self.assertEqual(
            str(folio_balance(order.folio)["balance"]), "44.00"
        )

    def test_exchange_lower_refunds_delta_on_folio(self):
        oid, lines = self._folio_order(
            items=[{"service_item": self.item.id, "quantity": "1"}]  # 44
        )
        order = ServiceOrder.objects.get(pk=oid)
        res = self._return(
            oid, kind="exchange_lower",
            items=[{
                "original_item": lines[0]["id"], "quantity": "1",
                "replacement_item": self.item2.id, "replacement_quantity": "1",  # 10
            }],
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        delta = FolioCharge.objects.get(pk=ret.delta_charge_id)
        self.assertEqual(delta.type, ChargeType.ADJUSTMENT)
        self.assertEqual(str(delta.total_amount), "-34.00")
        self.assertEqual(str(folio_balance(order.folio)["balance"]), "10.00")

    def test_exchange_higher_direct_collects_on_new_folio(self):
        oid, lines = self._direct_order(
            items=[{"service_item": self.item2.id, "quantity": "1"}]  # 10
        )
        res = self._return(
            oid, kind="exchange_higher", method="cash",
            items=[{
                "original_item": lines[0]["id"], "quantity": "1",
                "replacement_item": self.item.id, "replacement_quantity": "1",
            }],
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        collect_folio = Folio.objects.get(pk=ret.refund_folio_id)
        self.assertEqual(collect_folio.status, FolioStatus.CLOSED)
        self.assertEqual(str(folio_balance(collect_folio)["balance"]), "0.00")
        self.assertEqual(str(Payment.objects.get(pk=ret.delta_payment_id).amount), "34.00")
        self.assertEqual(str(FolioCharge.objects.get(pk=ret.delta_charge_id).total_amount), "34.00")

    def test_exchange_higher_direct_cash_capture(self):
        # D2a consistency — a CASH delta collection captures received + change on
        # the ServiceOrderReturn; the finance Payment records the EXACT delta.
        oid, lines = self._direct_order(
            items=[{"service_item": self.item2.id, "quantity": "1"}]  # 10
        )
        order = ServiceOrder.objects.get(pk=oid)
        original_folio = Folio.objects.get(pk=order.folio_id)
        original_charge = FolioCharge.objects.get(pk=order.posted_charge_id)
        res = self._return(
            oid, kind="exchange_higher", method="cash", amount_received="50.00",
            items=[{
                "original_item": lines[0]["id"], "quantity": "1",
                "replacement_item": self.item.id, "replacement_quantity": "1",
            }],
        )
        self.assertEqual(res.status_code, 201, res.data)
        ret = ServiceOrderReturn.objects.get(pk=res.data["return"]["id"])
        # Delta = 44 - 10 = 34; tender 50 -> change 16.
        self.assertEqual(str(ret.amount_received), "50.00")
        self.assertEqual(str(ret.change_given), "16.00")
        self.assertEqual(res.data["return"]["amount_received"], "50.00")
        self.assertEqual(res.data["return"]["change_given"], "16.00")
        # The Payment records the EXACT delta (not the tender).
        self.assertEqual(str(Payment.objects.get(pk=ret.delta_payment_id).amount), "34.00")
        collect_folio = Folio.objects.get(pk=ret.refund_folio_id)
        self.assertEqual(collect_folio.status, FolioStatus.CLOSED)
        self.assertEqual(str(folio_balance(collect_folio)["balance"]), "0.00")
        # The ORIGINAL closed transient folio + charge are untouched.
        original_folio.refresh_from_db()
        original_charge.refresh_from_db()
        self.assertEqual(original_folio.status, FolioStatus.CLOSED)
        self.assertEqual(str(original_charge.total_amount), "10.00")
        order.refresh_from_db()
        self.assertEqual(order.settlement, OrderSettlement.DIRECT)

    def test_exchange_higher_direct_short_tender_rejected(self):
        oid, lines = self._direct_order(
            items=[{"service_item": self.item2.id, "quantity": "1"}]  # 10
        )
        payments_before = Payment.objects.count()
        folios_before = Folio.objects.count()
        res = self._return(
            oid, kind="exchange_higher", method="cash", amount_received="20.00",  # < 34
            items=[{
                "original_item": lines[0]["id"], "quantity": "1",
                "replacement_item": self.item.id, "replacement_quantity": "1",
            }],
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "insufficient_cash_received")
        # No side effect: no return, no collect folio, no payment.
        self.assertEqual(ServiceOrderReturn.objects.filter(order_id=oid).count(), 0)
        self.assertEqual(Payment.objects.count(), payments_before)
        self.assertEqual(Folio.objects.count(), folios_before)

    def test_exchange_kind_mismatch_rejected(self):
        oid, lines = self._folio_order(
            items=[{"service_item": self.item2.id, "quantity": "1"}]  # 10
        )
        # Claiming "higher" while the replacement is cheaper is refused.
        res = self._return(
            oid, kind="exchange_higher",
            items=[{
                "original_item": lines[0]["id"], "quantity": "1",
                "replacement_item": self.item2.id, "replacement_quantity": "1",
            }],
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_return_composition")


class ReturnIdempotencyTests(ReturnBase):
    """D5 — return idempotency."""

    def test_same_key_creates_one_return(self):
        oid, lines = self._folio_order()
        body = {
            "kind": "return", "reason": "x",
            "items": [{"original_item": lines[0]["id"], "quantity": "1"}],
            "idempotency_key": "R1",
        }
        first = self.client.post(
            reverse("services:order-return", args=[oid]), body,
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            reverse("services:order-return", args=[oid]), body,
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["return"]["id"], second.data["return"]["id"])
        self.assertEqual(ServiceOrderReturn.objects.filter(order_id=oid).count(), 1)
        self.assertEqual(
            FolioCharge.objects.filter(source="order_return").count(), 1
        )

    def test_same_key_different_body_conflicts(self):
        oid, lines = self._folio_order()
        base = {
            "kind": "return",
            "items": [{"original_item": lines[0]["id"], "quantity": "1"}],
            "idempotency_key": "R2",
        }
        ok = self.client.post(
            reverse("services:order-return", args=[oid]),
            {**base, "reason": "first reason"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(ok.status_code, 201)
        conflict = self.client.post(
            reverse("services:order-return", args=[oid]),
            {**base, "reason": "totally different reason"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["code"], "idempotency_key_conflict")
        self.assertEqual(ServiceOrderReturn.objects.filter(order_id=oid).count(), 1)
