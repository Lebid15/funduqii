"""Tests for floors, room types and rooms (Phase 5).

Covers authorization + tenant isolation (incl. cross-tenant references),
per-resource CRUD + validation + delete guards, room status changes with the
required-note rule and status log, filtering/search, the suspended-hotel rule,
and regressions.
"""
from __future__ import annotations

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.rbac.services import grant_permission
from apps.rooms.models import Floor, Room, RoomStatusLog, RoomType
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=()):
    user = User.objects.create_user(
        email=email, password="StrongPass!234", full_name="Member"
    )
    membership = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True
    )
    for code in perms:
        grant_permission(membership, code)
    return user


def make_floor(hotel, **kw):
    return Floor.objects.create(hotel=hotel, name=kw.pop("name", "Ground"), **kw)


def make_type(hotel, code="STD", **kw):
    return RoomType.objects.create(
        hotel=hotel, name=kw.pop("name", "Standard"), code=code,
        base_capacity=kw.pop("base_capacity", 2), max_capacity=kw.pop("max_capacity", 3),
        **kw,
    )


def make_room(hotel, floor, rtype, number="101", **kw):
    return Room.objects.create(
        hotel=hotel, floor=floor, room_type=rtype, number=number, **kw
    )


HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731


class AccessTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(self.hotel)).status_code,
            401,
        )

    def test_user_without_membership_denied(self):
        outsider = User.objects.create_user(
            email="o@x.com", password="StrongPass!234", full_name="O"
        )
        self.client.force_authenticate(outsider)
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_cannot_access_other_hotel(self):
        other = make_hotel(slug="other")
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(other)).status_code, 403
        )

    def test_platform_owner_not_auto_member(self):
        owner = User.objects.create_platform_owner(
            email="owner@x.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_staff_view_permission(self):
        staff = add_member(self.hotel, "s@x.com", perms=["rooms.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(self.hotel)).status_code,
            200,
        )

    def test_staff_without_permission_denied(self):
        staff = add_member(self.hotel, "s2@x.com")
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_staff_create_permission(self):
        staff = add_member(self.hotel, "s3@x.com", perms=["rooms.create"])
        self.client.force_authenticate(staff)
        res = self.client.post(
            reverse("rooms:floor-list"), {"name": "First"}, format="json", **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 201)

    def test_suspended_hotel_read_only(self):
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("rooms:floor-list"), **HDR(self.hotel)).status_code,
            200,
        )
        res = self.client.post(
            reverse("rooms:floor-list"), {"name": "X"}, format="json", **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")


class FloorTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_create_update_list_scoped(self):
        res = self.client.post(
            reverse("rooms:floor-list"),
            {"name": "Ground", "number": "0", "sort_order": 1},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)
        fid = res.data["id"]
        upd = self.client.patch(
            reverse("rooms:floor-detail", args=[fid]),
            {"name": "Lobby"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(upd.data["name"], "Lobby")
        # Another hotel's floors are not listed.
        other = make_hotel(slug="o")
        make_floor(other, name="Other")
        listing = self.client.get(reverse("rooms:floor-list"), **HDR(self.hotel))
        self.assertEqual(listing.data["count"], 1)

    def test_cannot_delete_floor_with_rooms(self):
        floor = make_floor(self.hotel)
        rtype = make_type(self.hotel)
        make_room(self.hotel, floor, rtype)
        res = self.client.delete(
            reverse("rooms:floor-detail", args=[floor.id]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "resource_in_use")

    def test_can_delete_empty_floor(self):
        floor = make_floor(self.hotel)
        res = self.client.delete(
            reverse("rooms:floor-detail", args=[floor.id]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 204)


class RoomTypeTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def _create(self, **body):
        return self.client.post(
            reverse("rooms:room-type-list"), body, format="json", **HDR(self.hotel)
        )

    def test_create_and_code_unique_per_hotel(self):
        self.assertEqual(
            self._create(name="Standard", code="STD", base_capacity=2, max_capacity=3).status_code,
            201,
        )
        dup = self._create(name="Std2", code="STD", base_capacity=1, max_capacity=1)
        self.assertEqual(dup.status_code, 400)

    def test_same_code_allowed_in_other_hotel(self):
        make_type(self.hotel, code="STD")
        other = make_hotel(slug="o")
        add_member(other, "m2@x.com", kind=MembershipType.MANAGER)
        # Reusing the same code in a different hotel is allowed (model-level).
        self.assertFalse(
            RoomType.objects.filter(hotel=other, code="STD").exists()
        )
        RoomType.objects.create(
            hotel=other, name="S", code="STD", base_capacity=1, max_capacity=1
        )
        self.assertTrue(RoomType.objects.filter(hotel=other, code="STD").exists())

    def test_capacity_validation(self):
        res = self._create(name="Bad", code="B", base_capacity=4, max_capacity=2)
        self.assertEqual(res.status_code, 400)

    def test_cannot_delete_type_with_rooms(self):
        rtype = make_type(self.hotel)
        floor = make_floor(self.hotel)
        make_room(self.hotel, floor, rtype)
        res = self.client.delete(
            reverse("rooms:room-type-detail", args=[rtype.id]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 409)


class RoomTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(self.hotel)

    def _create(self, **body):
        body.setdefault("floor", self.floor.id)
        body.setdefault("room_type", self.rtype.id)
        return self.client.post(
            reverse("rooms:room-list"), body, format="json", **HDR(self.hotel)
        )

    def test_create_and_read(self):
        res = self._create(number="101")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["number"], "101")
        self.assertEqual(res.data["floor_name"], "Ground")
        self.assertEqual(res.data["room_type_code"], "STD")
        self.assertEqual(res.data["status"], "available")

    def test_number_unique_per_hotel(self):
        self._create(number="101")
        dup = self._create(number="101")
        self.assertEqual(dup.status_code, 400)

    def test_same_number_allowed_in_other_hotel(self):
        self._create(number="101")
        other = make_hotel(slug="o")
        of = make_floor(other)
        ot = make_type(other)
        make_room(other, of, ot, number="101")
        self.assertEqual(Room.objects.filter(number="101").count(), 2)

    def test_cannot_use_floor_from_another_hotel(self):
        other = make_hotel(slug="o")
        of = make_floor(other)
        res = self._create(number="201", floor=of.id)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "cross_tenant_reference")

    def test_cannot_use_room_type_from_another_hotel(self):
        other = make_hotel(slug="o")
        ot = make_type(other)
        res = self._create(number="202", room_type=ot.id)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "cross_tenant_reference")

    def test_filters_and_search(self):
        f2 = make_floor(self.hotel, name="First", sort_order=2)
        t2 = make_type(self.hotel, code="DLX", name="Deluxe")
        make_room(self.hotel, self.floor, self.rtype, number="101")
        make_room(self.hotel, f2, t2, number="201", display_name="Sea view")
        base = reverse("rooms:room-list")
        self.assertEqual(self.client.get(base, {"floor": f2.id}, **HDR(self.hotel)).data["count"], 1)
        self.assertEqual(self.client.get(base, {"room_type": t2.id}, **HDR(self.hotel)).data["count"], 1)
        self.assertEqual(self.client.get(base, {"search": "sea"}, **HDR(self.hotel)).data["count"], 1)
        self.assertEqual(self.client.get(base, {"search": "201"}, **HDR(self.hotel)).data["count"], 1)

    def test_status_update_and_log(self):
        room = make_room(self.hotel, self.floor, self.rtype)
        res = self.client.post(
            reverse("rooms:room-status", args=[room.id]),
            {"status": "dirty"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "dirty")
        self.assertIsNotNone(res.data["status_changed_at"])
        self.assertEqual(RoomStatusLog.objects.filter(room=room).count(), 1)

    def test_status_note_required_for_maintenance(self):
        room = make_room(self.hotel, self.floor, self.rtype)
        res = self.client.post(
            reverse("rooms:room-status", args=[room.id]),
            {"status": "maintenance"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "status_note_required")
        ok = self.client.post(
            reverse("rooms:room-status", args=[room.id]),
            {"status": "maintenance", "note": "AC broken"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["status_note"], "AC broken")

    def test_invalid_status_rejected(self):
        room = make_room(self.hotel, self.floor, self.rtype)
        res = self.client.post(
            reverse("rooms:room-status", args=[room.id]),
            {"status": "occupied"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 400)

    def test_status_update_requires_permission(self):
        staff = add_member(self.hotel, "s@x.com", perms=["rooms.view"])
        room = make_room(self.hotel, self.floor, self.rtype)
        self.client.force_authenticate(staff)
        res = self.client.post(
            reverse("rooms:room-status", args=[room.id]),
            {"status": "dirty"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 403)

    def test_archived_hidden_by_default(self):
        make_room(self.hotel, self.floor, self.rtype, number="101")
        make_room(self.hotel, self.floor, self.rtype, number="102", status="archived")
        base = reverse("rooms:room-list")
        self.assertEqual(self.client.get(base, **HDR(self.hotel)).data["count"], 1)
        self.assertEqual(
            self.client.get(base, {"include_archived": "true"}, **HDR(self.hotel)).data["count"],
            2,
        )
        self.assertEqual(
            self.client.get(base, {"status": "archived"}, **HDR(self.hotel)).data["count"],
            1,
        )

    def test_room_detail_isolation(self):
        room = make_room(self.hotel, self.floor, self.rtype)
        other = make_hotel(slug="o")
        add_member(other, "m2@x.com", kind=MembershipType.MANAGER)
        res = self.client.get(
            reverse("rooms:room-detail", args=[room.id]), **HDR(other)
        )
        self.assertEqual(res.status_code, 403)  # not a member of `other`? actually manager is of self.hotel


class RegressionTests(APITestCase):
    def test_health_and_forbidden_routes(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
        for path in ("/api/v1/guests/", "/api/v1/payments/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_hotel_settings_still_works(self):
        hotel = make_hotel()
        mgr = add_member(hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        self.assertEqual(
            self.client.get(reverse("hotel:settings"), **HDR(hotel)).status_code, 200
        )

    def test_no_out_of_scope_models(self):
        from django.apps import apps as django_apps

        tables = {m._meta.db_table for m in django_apps.get_models()}
        # Finance (Phase 8) is legitimate; restaurant/stock/daily-close/shifts are not.
        # (shifts/daily_closes became legitimate in Phase 12.)
        for forbidden in ("restaurant_orders", "stock_items", "payroll", "attendance_records"):
            self.assertNotIn(forbidden, tables)


# --- Operational board (owner task) ------------------------------------------


class OperationalBoardTests(APITestCase):
    """READ-ONLY board: computed display statuses, summaries, tenancy."""

    def setUp(self):
        import datetime

        from django.utils import timezone as dj_tz

        from apps.guests.models import Guest
        from apps.reservations.models import Reservation, ReservationRoomLine
        from apps.stays.models import Stay

        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.floor = make_floor(self.hotel, name="First", number="1")
        self.rtype = make_type(self.hotel)

        today = datetime.date.today()
        self.r_available = make_room(self.hotel, self.floor, self.rtype, "101")
        self.r_occupied = make_room(self.hotel, self.floor, self.rtype, "102")
        self.r_reserved = make_room(self.hotel, self.floor, self.rtype, "103")
        self.r_dirty_occupied = make_room(
            self.hotel, self.floor, self.rtype, "104", status="dirty"
        )
        self.r_archived = make_room(
            self.hotel, self.floor, self.rtype, "199", status="archived"
        )

        guest = Guest.objects.create(hotel=self.hotel, full_name="Guest One")

        # The active reservation the current stay came from...
        self.res_current = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-001",
            check_in_date=today,
            check_out_date=today + datetime.timedelta(days=2),
            primary_guest_name="Guest One",
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=self.res_current,
            room_type=self.rtype,
            room=self.r_occupied,
            quantity=1,
        )
        self.stay = Stay.objects.create(
            hotel=self.hotel,
            reservation=self.res_current,
            room=self.r_occupied,
            primary_guest=guest,
            planned_check_in_date=today,
            planned_check_out_date=today + datetime.timedelta(days=2),
            actual_check_in_at=dj_tz.now(),
        )
        # ...and a FUTURE reservation for the same occupied room.
        self.res_next = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-002",
            check_in_date=today + datetime.timedelta(days=3),
            check_out_date=today + datetime.timedelta(days=5),
            primary_guest_name="Guest Two",
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=self.res_next,
            room_type=self.rtype,
            room=self.r_occupied,
            quantity=1,
        )
        # An upcoming confirmed reservation on an otherwise-available room.
        self.res_upcoming = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-003",
            check_in_date=today + datetime.timedelta(days=1),
            check_out_date=today + datetime.timedelta(days=2),
            primary_guest_name="Guest Three",
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=self.res_upcoming,
            room_type=self.rtype,
            room=self.r_reserved,
            quantity=1,
        )
        # A stay on the DIRTY room too — the manual state must win the display.
        guest2 = Guest.objects.create(hotel=self.hotel, full_name="Guest Four")
        Stay.objects.create(
            hotel=self.hotel,
            room=self.r_dirty_occupied,
            primary_guest=guest2,
            planned_check_in_date=today,
            planned_check_out_date=today + datetime.timedelta(days=1),
            actual_check_in_at=dj_tz.now(),
        )

    def _get(self):
        return self.client.get(
            reverse("rooms:room-operational-board"), **HDR(self.hotel)
        )

    def test_requires_rooms_view(self):
        staff = add_member(self.hotel, "np@x.com", perms=["reservations.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._get().status_code, 403)

    def test_staff_with_rooms_view_allowed(self):
        staff = add_member(self.hotel, "v@x.com", perms=["rooms.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._get().status_code, 200)

    def test_display_statuses_and_priority(self):
        self.client.force_authenticate(self.manager)
        rooms = {r["number"]: r for r in self._get().data["rooms"]}
        self.assertEqual(rooms["101"]["display_status"], "available")
        self.assertEqual(rooms["102"]["display_status"], "occupied")
        self.assertEqual(rooms["103"]["display_status"], "reserved")
        # Manual dirty beats the in-house stay (owner priority).
        self.assertEqual(rooms["104"]["display_status"], "dirty")
        self.assertEqual(rooms["199"]["display_status"], "archived")
        # Stored operational status is never rewritten.
        self.assertEqual(rooms["102"]["operational_status"], "available")

    def test_current_stay_and_next_reservation(self):
        self.client.force_authenticate(self.manager)
        rooms = {r["number"]: r for r in self._get().data["rooms"]}
        occupied = rooms["102"]
        self.assertEqual(occupied["current_stay"]["guest_name"], "Guest One")
        self.assertEqual(occupied["current_stay"]["reservation_number"], "R-001")
        # The stay''s own reservation is skipped — R-002 is the NEXT one.
        self.assertEqual(
            occupied["next_reservation"]["reservation_number"], "R-002"
        )
        self.assertEqual(
            rooms["103"]["next_reservation"]["reservation_number"], "R-003"
        )
        self.assertIsNone(rooms["101"]["next_reservation"])

    def test_summary_and_floor_counts_exclude_archived(self):
        self.client.force_authenticate(self.manager)
        data = self._get().data
        summary = data["summary"]
        self.assertEqual(summary["total"], 4)  # 199 archived is excluded
        self.assertEqual(summary["available"], 1)
        self.assertEqual(summary["occupied"], 1)
        self.assertEqual(summary["reserved"], 1)
        self.assertEqual(summary["dirty"], 1)
        self.assertEqual(summary["attention"], 1)
        floor = data["floors"][0]
        self.assertEqual(floor["total"], 4)
        self.assertEqual(floor["availability_rate"], 25)

    def test_tenant_isolation(self):
        other = make_hotel(slug="other")
        of = make_floor(other, name="O")
        ot = make_type(other, code="OT")
        make_room(other, of, ot, "901")
        self.client.force_authenticate(self.manager)
        numbers = [r["number"] for r in self._get().data["rooms"]]
        self.assertNotIn("901", numbers)
