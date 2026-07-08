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
    "service_orders.view", "service_orders.create", "service_orders.update",
    "service_orders.cancel", "service_orders.status_update",
    "service_orders.post_to_folio",
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
    def make_catalog(self):
        self.category = make_category(self.hotel)
        self.item = make_item(self.hotel, self.category)          # 40.00 +10%
        self.item2 = make_item(self.hotel, self.category, name="Tea", price="10.00", tax="0.00")

    def create_order(self, hotel=None, **body):
        hotel = hotel or self.hotel
        body.setdefault("items", [{"service_item": self.item.id, "quantity": "2"}])
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
             "tax_rate": "5.00", "item_type": "cafe"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)
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
            reverse("services:item-list"), {"item_type": "restaurant"}, **HDR(self.hotel)
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
        })
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
        res = self.client.get(
            reverse("services:order-ticket", args=[oid]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["document"], "service_ticket")
        self.assertEqual(res.data["totals"]["total"], "88.00")
        self.assertEqual(len(res.data["items"]), 1)


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
        # POS/inventory/tables/public ordering belong to NO phase yet.
        for path in (
            "/api/v1/hotel/services/pos/",
            "/api/v1/hotel/services/inventory/",
            "/api/v1/hotel/services/tables/",
            "/api/v1/hotel/services/public-orders/",
            # (shifts/daily-close became legitimate in Phase 12.)
            "/api/v1/hotel/payroll/",
            "/api/v1/hotel/attendance/",
        ):
            self.assertEqual(self.client.get(path).status_code, 404, path)
