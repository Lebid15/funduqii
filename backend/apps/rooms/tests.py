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
        from apps.shifts.services import get_business_date
        from apps.stays.models import Stay

        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.floor = make_floor(self.hotel, name="First", number="1")
        self.rtype = make_type(self.hotel)

        # Anchor on the board's business date (not the naive system clock) so the
        # future-only reservation (room 103) is deterministically future.
        today = get_business_date(self.hotel)
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
        # Frontend-compat display_status (collapsed single value) unchanged.
        self.assertEqual(rooms["101"]["display_status"], "available")
        self.assertEqual(rooms["102"]["display_status"], "occupied")
        # H3: 103's only reservation (R-003) starts TOMORROW — a purely future
        # booking no longer reserves the room today, so it reads free/available.
        self.assertEqual(rooms["103"]["display_status"], "available")
        # Manual dirty beats the in-house stay (owner priority).
        self.assertEqual(rooms["104"]["display_status"], "dirty")
        self.assertEqual(rooms["199"]["display_status"], "archived")
        # Stored operational status is never rewritten.
        self.assertEqual(rooms["102"]["operational_status"], "available")
        # NEW — occupancy and operational are reported on SEPARATE axes.
        self.assertEqual(rooms["101"]["occupancy_status"], "free")
        self.assertEqual(rooms["101"]["operational_status"], "available")
        self.assertEqual(rooms["102"]["occupancy_status"], "occupied")
        self.assertEqual(rooms["102"]["operational_status"], "available")
        # H3: future-only reservation -> occupancy free (not reserved today).
        self.assertEqual(rooms["103"]["occupancy_status"], "free")
        self.assertEqual(rooms["103"]["operational_status"], "available")
        # The occupied+dirty room: display collapses to "dirty", but occupancy
        # is still reported as occupied and the manual state as dirty — the two
        # axes no longer mask each other.
        self.assertEqual(rooms["104"]["occupancy_status"], "occupied")
        self.assertEqual(rooms["104"]["operational_status"], "dirty")

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
        from apps.stays.models import Stay, StayStatus

        self.client.force_authenticate(self.manager)
        data = self._get().data
        summary = data["summary"]
        self.assertEqual(summary["total"], 4)  # 199 archived is excluded
        # H3: 101 AND 103 are available now (103's reservation is future-only).
        self.assertEqual(summary["available"], 2)
        self.assertEqual(summary["available_now"], 2)  # explicit alias key
        # occupied MUST equal the real IN_HOUSE stays on non-archived rooms
        # (102 + 104) — the occupied+dirty room no longer vanishes behind its
        # manual state (the collapse bug).
        real_in_house = (
            Stay.objects.filter(hotel=self.hotel, status=StayStatus.IN_HOUSE)
            .exclude(room__status="archived")
            .count()
        )
        self.assertEqual(real_in_house, 2)
        self.assertEqual(summary["occupied"], real_in_house)
        # H3: the only reservation (103's R-003) is future-only -> reserves nothing today.
        self.assertEqual(summary["reserved"], 0)
        self.assertEqual(summary["dirty"], 1)
        self.assertEqual(summary["attention"], 1)
        # The occupied+dirty room (104) is counted in BOTH occupied and dirty.
        rooms = {r["number"]: r for r in data["rooms"]}
        self.assertEqual(rooms["104"]["occupancy_status"], "occupied")
        self.assertEqual(rooms["104"]["operational_status"], "dirty")
        floor = data["floors"][0]
        self.assertEqual(floor["total"], 4)
        self.assertEqual(floor["availability_rate"], 50)  # 2 of 4 available

    def test_tenant_isolation(self):
        other = make_hotel(slug="other")
        of = make_floor(other, name="O")
        ot = make_type(other, code="OT")
        make_room(other, of, ot, "901")
        self.client.force_authenticate(self.manager)
        numbers = [r["number"] for r in self._get().data["rooms"]]
        self.assertNotIn("901", numbers)


# --- Rooms rework (ROOMS-REWORK-01) ------------------------------------------
# Extra fixtures for stays / reservation lines, reused by the new board,
# delete-guard and bulk-create tests below.


def make_stay(hotel, room, *, guest_name="Guest", days=2):
    import datetime

    from django.utils import timezone as dj_tz

    from apps.guests.models import Guest
    from apps.stays.models import Stay

    today = datetime.date.today()
    guest = Guest.objects.create(hotel=hotel, full_name=guest_name)
    return Stay.objects.create(
        hotel=hotel,
        room=room,
        primary_guest=guest,
        planned_check_in_date=today,
        planned_check_out_date=today + datetime.timedelta(days=days),
        actual_check_in_at=dj_tz.now(),
    )


def make_reservation_line(hotel, *, rtype, room=None, number="RX", days=2):
    import datetime

    from apps.reservations.models import Reservation, ReservationRoomLine
    from apps.shifts.services import get_business_date

    # Anchor fixtures on the hotel's BUSINESS DATE — the exact date the board
    # uses (get_business_date -> timezone.localdate()). Basing them on the naive
    # system date.today() can be a day off from localdate() (server TZ vs. host
    # clock), which the H3 covering check (check_in <= business_date < check_out)
    # would then read as a future-only booking.
    base = get_business_date(hotel)
    res = Reservation.objects.create(
        hotel=hotel,
        reservation_number=number,
        check_in_date=base,
        check_out_date=base + datetime.timedelta(days=days),
        primary_guest_name="G",
    )
    return ReservationRoomLine.objects.create(
        hotel=hotel, reservation=res, room_type=rtype, room=room, quantity=1
    )


class BoardAxesTests(APITestCase):
    """occupancy_status / operational_status / available_now on SEPARATE axes."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel, name="F1", number="1")
        self.rtype = make_type(self.hotel)

    def _rows(self):
        res = self.client.get(
            reverse("rooms:room-operational-board"), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 200)
        return {r["number"]: r for r in res.data["rooms"]}

    def test_occupancy_free_occupied_reserved(self):
        make_room(self.hotel, self.floor, self.rtype, "101")  # free
        occ = make_room(self.hotel, self.floor, self.rtype, "102")
        make_stay(self.hotel, occ)
        rsv = make_room(self.hotel, self.floor, self.rtype, "103")
        make_reservation_line(self.hotel, rtype=self.rtype, room=rsv, number="R-1")
        rows = self._rows()
        self.assertEqual(rows["101"]["occupancy_status"], "free")
        self.assertEqual(rows["102"]["occupancy_status"], "occupied")
        self.assertEqual(rows["103"]["occupancy_status"], "reserved")

    def test_occupied_beats_reserved(self):
        # A room with BOTH an in-house stay and a blocking reservation is
        # occupied (occupancy priority), never reserved.
        room = make_room(self.hotel, self.floor, self.rtype, "201")
        make_stay(self.hotel, room)
        make_reservation_line(self.hotel, rtype=self.rtype, room=room, number="R-2")
        self.assertEqual(self._rows()["201"]["occupancy_status"], "occupied")

    def test_occupied_room_stays_occupied_when_dirty(self):
        room = make_room(self.hotel, self.floor, self.rtype, "301", status="dirty")
        make_stay(self.hotel, room)
        row = self._rows()["301"]
        # Occupancy is independent of the manual state — dirty does not hide it.
        self.assertEqual(row["occupancy_status"], "occupied")
        self.assertEqual(row["operational_status"], "dirty")
        self.assertFalse(row["available_now"])

    def test_operational_independent_of_occupancy(self):
        room = make_room(
            self.hotel, self.floor, self.rtype, "401",
            status="maintenance", status_note="fix",
        )
        row = self._rows()["401"]
        self.assertEqual(row["occupancy_status"], "free")
        self.assertEqual(row["operational_status"], "maintenance")
        self.assertFalse(row["available_now"])

    def test_available_now_all_gates_open(self):
        make_room(self.hotel, self.floor, self.rtype, "501")
        row = self._rows()["501"]
        self.assertTrue(row["available_now"])
        self.assertEqual(row["occupancy_status"], "free")
        self.assertEqual(row["operational_status"], "available")
        self.assertTrue(row["floor_is_active"])
        self.assertTrue(row["room_type_is_active"])

    def test_available_now_false_on_inactive_room(self):
        make_room(self.hotel, self.floor, self.rtype, "502", is_active=False)
        self.assertFalse(self._rows()["502"]["available_now"])

    def test_available_now_false_on_inactive_floor(self):
        f2 = make_floor(self.hotel, name="F2", number="2", is_active=False)
        make_room(self.hotel, f2, self.rtype, "601")
        row = self._rows()["601"]
        self.assertFalse(row["available_now"])
        self.assertFalse(row["floor_is_active"])

    def test_available_now_false_on_inactive_room_type(self):
        t2 = make_type(self.hotel, code="INA", name="Inactive", is_active=False)
        make_room(self.hotel, self.floor, t2, "701")
        row = self._rows()["701"]
        self.assertFalse(row["available_now"])
        self.assertFalse(row["room_type_is_active"])

    def test_available_now_false_when_dirty(self):
        make_room(self.hotel, self.floor, self.rtype, "801", status="dirty")
        self.assertFalse(self._rows()["801"]["available_now"])

    def test_available_now_false_when_reserved(self):
        room = make_room(self.hotel, self.floor, self.rtype, "901")
        make_reservation_line(self.hotel, rtype=self.rtype, room=room, number="R-9")
        self.assertFalse(self._rows()["901"]["available_now"])

    def test_available_now_false_when_occupied(self):
        room = make_room(self.hotel, self.floor, self.rtype, "111")
        make_stay(self.hotel, room)
        self.assertFalse(self._rows()["111"]["available_now"])

    def test_summaries_two_axes(self):
        make_room(self.hotel, self.floor, self.rtype, "101")  # free + available
        occ = make_room(self.hotel, self.floor, self.rtype, "102")  # occupied clean
        make_stay(self.hotel, occ, guest_name="A")
        od = make_room(  # occupied + dirty (overlap on both axes)
            self.hotel, self.floor, self.rtype, "103", status="dirty"
        )
        make_stay(self.hotel, od, guest_name="B")
        rsv = make_room(self.hotel, self.floor, self.rtype, "104")  # reserved
        make_reservation_line(self.hotel, rtype=self.rtype, room=rsv, number="R-1")
        make_room(  # maintenance (attention, free)
            self.hotel, self.floor, self.rtype, "105",
            status="maintenance", status_note="x",
        )
        make_room(self.hotel, self.floor, self.rtype, "199", status="archived")

        res = self.client.get(
            reverse("rooms:room-operational-board"), **HDR(self.hotel)
        )
        summary = res.data["summary"]
        self.assertEqual(summary["total"], 5)  # 199 archived excluded
        self.assertEqual(summary["occupied"], 2)  # 102 + 103
        self.assertEqual(summary["reserved"], 1)  # 104
        self.assertEqual(summary["available"], 1)  # 101 only
        self.assertEqual(summary["available_now"], 1)
        self.assertEqual(summary["dirty"], 1)  # 103
        self.assertEqual(summary["maintenance"], 1)  # 105
        self.assertEqual(summary["cleaning"], 0)
        self.assertEqual(summary["out_of_service"], 0)
        # attention = dirty + cleaning + maintenance + out_of_service.
        self.assertEqual(summary["attention"], 2)
        floor = res.data["floors"][0]
        self.assertEqual(floor["occupied"], 2)
        self.assertEqual(floor["available"], 1)
        self.assertEqual(floor["availability_rate"], round(1 * 100 / 5))


class RoomDeleteGuardTests(APITestCase):
    """R1: deleting a referenced room is a clean 409, never a 500."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(self.hotel)

    def _delete(self, room):
        return self.client.delete(
            reverse("rooms:room-detail", args=[room.id]), **HDR(self.hotel)
        )

    def test_delete_free_room_succeeds(self):
        room = make_room(self.hotel, self.floor, self.rtype, "101")
        self.assertEqual(self._delete(room).status_code, 204)
        self.assertFalse(Room.objects.filter(id=room.id).exists())

    def test_delete_room_with_stay_conflict(self):
        room = make_room(self.hotel, self.floor, self.rtype, "102")
        make_stay(self.hotel, room)
        res = self._delete(room)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "resource_in_use")
        self.assertEqual(res.data["details"]["reason"], "room_has_stays")
        self.assertTrue(Room.objects.filter(id=room.id).exists())

    def test_delete_room_with_reservation_conflict(self):
        room = make_room(self.hotel, self.floor, self.rtype, "103")
        make_reservation_line(self.hotel, rtype=self.rtype, room=room, number="R-1")
        res = self._delete(room)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "resource_in_use")
        self.assertEqual(res.data["details"]["reason"], "room_has_reservations")

    def test_delete_room_never_returns_500(self):
        # Both PROTECT relations present -> guard yields 409, not an unhandled
        # ProtectedError 500.
        room = make_room(self.hotel, self.floor, self.rtype, "104")
        make_stay(self.hotel, room)
        make_reservation_line(self.hotel, rtype=self.rtype, room=room, number="R-2")
        res = self._delete(room)
        self.assertNotEqual(res.status_code, 500)
        self.assertEqual(res.status_code, 409)


class RoomTypeDeleteGuardTests(APITestCase):
    """R2: room type delete blocks on rooms AND on reservation lines."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel)

    def _delete(self, rtype):
        return self.client.delete(
            reverse("rooms:room-type-detail", args=[rtype.id]), **HDR(self.hotel)
        )

    def test_delete_type_with_rooms_conflict(self):
        rtype = make_type(self.hotel, code="A")
        make_room(self.hotel, self.floor, rtype, "101")
        res = self._delete(rtype)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["details"]["reason"], "room_type_has_rooms")

    def test_delete_type_with_reservation_line_conflict(self):
        # A reservation line references the type but NO room uses it (the R2
        # gap: the old guard only checked .rooms).
        rtype = make_type(self.hotel, code="B")
        make_reservation_line(self.hotel, rtype=rtype, room=None, number="R-1")
        res = self._delete(rtype)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "resource_in_use")
        self.assertEqual(res.data["details"]["reason"], "room_type_has_reservations")

    def test_delete_unused_type_succeeds(self):
        rtype = make_type(self.hotel, code="C")
        self.assertEqual(self._delete(rtype).status_code, 204)


class FloorDeleteRegressionTests(APITestCase):
    """The floor delete guard is unchanged by this rework."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def _delete(self, floor):
        return self.client.delete(
            reverse("rooms:floor-detail", args=[floor.id]), **HDR(self.hotel)
        )

    def test_delete_floor_with_rooms_still_conflicts(self):
        floor = make_floor(self.hotel)
        rtype = make_type(self.hotel)
        make_room(self.hotel, floor, rtype, "101")
        res = self._delete(floor)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["details"]["reason"], "floor_has_rooms")

    def test_delete_empty_floor_succeeds(self):
        floor = make_floor(self.hotel)
        self.assertEqual(self._delete(floor).status_code, 204)


class RoomBulkCreateTests(APITestCase):
    """POST /rooms/bulk/ — all-or-nothing batch create."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(self.hotel)

    def _bulk(self, rooms, hotel=None):
        hotel = hotel or self.hotel
        return self.client.post(
            reverse("rooms:room-bulk-create"),
            {"rooms": rooms},
            format="json",
            **HDR(hotel),
        )

    def _row(self, number, **kw):
        row = {
            "number": number,
            "floor": self.floor.id,
            "room_type": self.rtype.id,
        }
        row.update(kw)
        return row

    def test_success_returns_created_count_and_rooms(self):
        res = self._bulk(
            [
                self._row("101"),
                self._row("102", display_name="Sea", is_active=False),
                self._row("103", initial_status="dirty"),
            ]
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["created_count"], 3)
        self.assertEqual(len(res.data["rooms"]), 3)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 3)
        self.assertEqual(
            {r["number"] for r in res.data["rooms"]}, {"101", "102", "103"}
        )
        dirty = Room.objects.get(hotel=self.hotel, number="103")
        self.assertEqual(dirty.status, "dirty")
        self.assertEqual(RoomStatusLog.objects.filter(room=dirty).count(), 1)

    def test_all_or_nothing_rolls_back(self):
        # The 2nd row is cross-tenant -> nothing is written.
        other = make_hotel(slug="o")
        of = make_floor(other)
        res = self._bulk(
            [self._row("101"), self._row("102", floor=of.id)]
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "cross_tenant_reference")
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_duplicate_within_request(self):
        # M1: duplicate WITHIN the request -> typed duplicate_room_number,
        # source "request", with the offending numbers.
        res = self._bulk([self._row("101"), self._row("101")])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "duplicate_room_number")
        self.assertEqual(res.data["details"]["source"], "request")
        self.assertIn("101", res.data["details"]["numbers"])
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_duplicate_within_hotel(self):
        # M1: collision with an EXISTING hotel number -> duplicate_room_number,
        # source "existing".
        make_room(self.hotel, self.floor, self.rtype, "101")
        res = self._bulk([self._row("101")])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "duplicate_room_number")
        self.assertEqual(res.data["details"]["source"], "existing")
        self.assertIn("101", res.data["details"]["numbers"])
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 1)

    def test_cross_tenant_floor(self):
        other = make_hotel(slug="o")
        of = make_floor(other)
        res = self._bulk([self._row("201", floor=of.id)])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "cross_tenant_reference")
        self.assertEqual(res.data["details"]["field"], "floor")

    def test_cross_tenant_room_type(self):
        other = make_hotel(slug="o")
        ot = make_type(other, code="OT")
        res = self._bulk([self._row("202", room_type=ot.id)])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "cross_tenant_reference")
        self.assertEqual(res.data["details"]["field"], "room_type")

    def test_note_required_for_maintenance(self):
        res = self._bulk([self._row("301", initial_status="maintenance")])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "status_note_required")
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_maintenance_logs_but_does_not_notify(self):
        from apps.notifications.models import Notification

        # A second manager WOULD receive a maintenance notification if the
        # fan-out fired (managers are always eligible, actor excluded) — so a
        # non-zero delta here would prove the mute is broken.
        add_member(self.hotel, "mgr2@x.com", kind=MembershipType.MANAGER)
        before = Notification.objects.count()
        res = self._bulk(
            [self._row("301", initial_status="maintenance", status_note="AC broken")]
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["rooms"][0]["status"], "maintenance")
        room_id = res.data["rooms"][0]["id"]
        self.assertEqual(RoomStatusLog.objects.filter(room_id=room_id).count(), 1)
        # decision 2: bulk mutes the per-room notification fan-out entirely.
        self.assertEqual(Notification.objects.count(), before)

    def test_archived_initial_status_rejected(self):
        res = self._bulk([self._row("301", initial_status="archived")])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_over_max_rejected(self):
        # M1: over the hard cap -> typed bulk_request_too_large with limit/requested.
        rows = [self._row(str(1000 + i)) for i in range(101)]
        res = self._bulk(rows)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "bulk_request_too_large")
        self.assertEqual(int(res.data["details"]["limit"]), 100)
        self.assertEqual(int(res.data["details"]["requested"]), 101)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_oversized_list_rejected_before_row_validation(self):
        # L1 hardening: 101 structurally INVALID rows (empty dicts). If DRF ran
        # per-row validation first we'd get field errors; the view's early size
        # check makes it bulk_request_too_large instead — proving the rejection
        # precedes (expensive) per-element validation.
        res = self._bulk([{} for _ in range(101)])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "bulk_request_too_large")
        self.assertEqual(int(res.data["details"]["requested"]), 101)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_malformed_top_level_array_body_clean_4xx(self):
        # L1 edge case: a TOP-LEVEL JSON array body (instead of {"rooms": [...]})
        # makes request.data a list. The early size check must guard against
        # calling .get on a non-dict; the request falls through to the serializer
        # which rejects the wrong shape with a clean 4xx — never a 500.
        res = self.client.post(
            reverse("rooms:room-bulk-create"),
            [self._row("101")],
            format="json",
            **HDR(self.hotel),
        )
        self.assertGreaterEqual(res.status_code, 400)
        self.assertLess(res.status_code, 500)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_empty_rejected(self):
        res = self._bulk([])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_requires_create_permission(self):
        staff = add_member(self.hotel, "view@x.com", perms=["rooms.view"])
        self.client.force_authenticate(staff)
        res = self._bulk([self._row("101")])
        self.assertEqual(res.status_code, 403)

    def test_suspended_hotel_blocked(self):
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        res = self._bulk([self._row("101")])
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_tenant_isolation(self):
        # The manager is not a member of `other` -> forbidden.
        other = make_hotel(slug="o")
        res = self._bulk([self._row("101")], hotel=other)
        self.assertEqual(res.status_code, 403)


class RoomBulkQuotaTests(APITestCase):
    """Bulk create checks the plan's room_limit on the FULL batch count."""

    def setUp(self):
        from decimal import Decimal

        from apps.subscriptions import services as sub_services
        from apps.subscriptions.models import SubscriptionPlan

        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(self.hotel)
        plan = SubscriptionPlan.objects.create(
            name="Basic", slug="basic", price=Decimal("49.00"), currency="USD",
            billing_cycle="monthly", trial_days=14, is_active=True,
            is_public=True, room_limit=3,
        )
        sub_services.activate_subscription(self.hotel, plan)

    def _bulk(self, rooms):
        return self.client.post(
            reverse("rooms:room-bulk-create"),
            {"rooms": rooms},
            format="json",
            **HDR(self.hotel),
        )

    def _rows(self, n):
        return [
            {"number": str(100 + i), "floor": self.floor.id, "room_type": self.rtype.id}
            for i in range(n)
        ]

    def test_over_room_limit_full_count_blocked(self):
        res = self._bulk(self._rows(4))  # 4 > limit 3, checked as one unit
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "room_limit_reached")
        # Detail values serialise as strings through the error envelope.
        self.assertEqual(int(res.data["details"]["requested"]), 4)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_within_room_limit_ok(self):
        res = self._bulk(self._rows(3))  # exactly at limit
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 3)


class RoomQuotaBackCompatTests(APITestCase):
    """check_room_quota(count=..) is backward compatible with the old count=1
    gate (``usage + 1 > limit`` == old ``usage >= limit``)."""

    def setUp(self):
        from decimal import Decimal

        from apps.subscriptions import services as sub_services
        from apps.subscriptions.models import SubscriptionPlan

        self.hotel = make_hotel()
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(self.hotel)
        plan = SubscriptionPlan.objects.create(
            name="Basic", slug="basic", price=Decimal("49.00"), currency="USD",
            billing_cycle="monthly", trial_days=14, is_active=True,
            is_public=True, room_limit=2,
        )
        sub_services.activate_subscription(self.hotel, plan)

    def test_count_default_matches_single_room_gate(self):
        from apps.common.exceptions import RoomLimitReached
        from apps.subscriptions.entitlements import check_room_quota

        # usage 0, limit 2: default count and explicit count=1 both pass.
        check_room_quota(self.hotel)
        check_room_quota(self.hotel, count=1)
        # Fill to the limit, then both forms must block identically.
        make_room(self.hotel, self.floor, self.rtype, "101")
        make_room(self.hotel, self.floor, self.rtype, "102")
        with self.assertRaises(RoomLimitReached):
            check_room_quota(self.hotel)
        with self.assertRaises(RoomLimitReached):
            check_room_quota(self.hotel, count=1)

    def test_count_n_checks_full_batch(self):
        from apps.common.exceptions import RoomLimitReached
        from apps.subscriptions.entitlements import check_room_quota

        # usage 0, limit 2: count=2 ok, count=3 blocked.
        check_room_quota(self.hotel, count=2)
        with self.assertRaises(RoomLimitReached):
            check_room_quota(self.hotel, count=3)


# --- ROOMS-REWORK-01 fix round (H1 / H2 / H3 / L2) --------------------------


class RoomSingleCreateReworkTests(APITestCase):
    """H2: single create funnels through the SHARED central service (quota +
    room creation + initial-status RoomStatusLog in one atomic txn). H1: a
    non-available initial status also requires rooms.status_update."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(self.hotel)

    def _create(self, user=None, **body):
        self.client.force_authenticate(user or self.manager)
        body.setdefault("floor", self.floor.id)
        body.setdefault("room_type", self.rtype.id)
        return self.client.post(
            reverse("rooms:room-list"), body, format="json", **HDR(self.hotel)
        )

    def test_default_available_create_writes_no_log(self):
        res = self._create(number="101")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "available")
        room = Room.objects.get(hotel=self.hotel, number="101")
        self.assertEqual(RoomStatusLog.objects.filter(room=room).count(), 0)

    def test_initial_status_writes_log_atomically(self):
        res = self._create(number="102", initial_status="dirty")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "dirty")
        room = Room.objects.get(hotel=self.hotel, number="102")
        self.assertEqual(room.status, "dirty")
        logs = RoomStatusLog.objects.filter(room=room)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().new_status, "dirty")

    def test_maintenance_requires_note(self):
        res = self._create(number="103", initial_status="maintenance")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "status_note_required")
        self.assertFalse(Room.objects.filter(hotel=self.hotel, number="103").exists())

    def test_maintenance_with_note_ok(self):
        res = self._create(
            number="104", initial_status="maintenance", status_note="AC broken"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "maintenance")
        self.assertEqual(res.data["status_note"], "AC broken")
        room = Room.objects.get(hotel=self.hotel, number="104")
        self.assertEqual(RoomStatusLog.objects.filter(room=room).count(), 1)

    def test_archived_initial_status_rejected(self):
        res = self._create(number="105", initial_status="archived")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Room.objects.filter(hotel=self.hotel, number="105").exists())

    def test_create_only_user_blocked_from_non_available(self):
        staff = add_member(self.hotel, "c@x.com", perms=["rooms.create"])
        res = self._create(user=staff, number="106", initial_status="dirty")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "permission_denied")
        # H1 is checked BEFORE any write -> nothing created.
        self.assertFalse(Room.objects.filter(hotel=self.hotel, number="106").exists())

    def test_create_only_user_available_ok(self):
        staff = add_member(self.hotel, "c2@x.com", perms=["rooms.create"])
        res = self._create(user=staff, number="107")  # available -> create alone
        self.assertEqual(res.status_code, 201)

    def test_create_plus_status_update_user_succeeds(self):
        staff = add_member(
            self.hotel, "cs@x.com", perms=["rooms.create", "rooms.status_update"]
        )
        res = self._create(user=staff, number="108", initial_status="dirty")
        self.assertEqual(res.status_code, 201)
        room = Room.objects.get(hotel=self.hotel, number="108")
        self.assertEqual(room.status, "dirty")
        self.assertEqual(RoomStatusLog.objects.filter(room=room).count(), 1)

    def test_update_does_not_wipe_status_note(self):
        # Regression: the write serializer's create-only status_note must never
        # blow away a room's real status_note on a PUT (they collide by name).
        room = make_room(
            self.hotel, self.floor, self.rtype, "109",
            status="maintenance", status_note="keep me",
        )
        self.client.force_authenticate(self.manager)
        res = self.client.put(
            reverse("rooms:room-detail", args=[room.id]),
            {
                "number": "109",
                "display_name": "Renamed",
                "floor": self.floor.id,
                "room_type": self.rtype.id,
                "is_active": True,
            },
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        room.refresh_from_db()
        self.assertEqual(room.status, "maintenance")
        self.assertEqual(room.status_note, "keep me")
        self.assertEqual(room.display_name, "Renamed")

    def test_service_integrity_error_is_clean_4xx(self):
        # L2: a concurrent duplicate number reaches Room.objects.create and
        # raises IntegrityError; the central service translates it to a clean
        # DuplicateRoomNumber (400), never a 500. Simulated by calling the
        # service with an existing number (bypassing the serializer pre-check
        # the same way a race would).
        from apps.common.exceptions import DuplicateRoomNumber
        from apps.rooms import services

        make_room(self.hotel, self.floor, self.rtype, "200")
        with self.assertRaises(DuplicateRoomNumber) as ctx:
            services.create_room(
                self.hotel,
                number="200",
                floor=self.floor,
                room_type=self.rtype,
                user=self.manager,
            )
        self.assertEqual(ctx.exception.default_code, "duplicate_room_number")
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["source"], "existing")
        # The failed create rolled back — still exactly one "200".
        self.assertEqual(Room.objects.filter(hotel=self.hotel, number="200").count(), 1)

    def test_non_duplicate_integrity_error_not_mislabeled(self):
        # L2: a NON-duplicate integrity error must NOT be relabelled as a
        # duplicate. A stale floor instance (its row deleted) makes the room
        # insert fail the FK constraint, not the unique room-number one, so the
        # original IntegrityError propagates (atomic still rolls back).
        from django.db import IntegrityError

        from apps.rooms import services

        stale_floor = make_floor(self.hotel, name="Temp")
        stale_floor.delete()  # floor_id now points to a non-existent row
        with self.assertRaises(IntegrityError):
            services.create_room(
                self.hotel,
                number="900",
                floor=stale_floor,
                room_type=self.rtype,
                user=self.manager,
            )
        self.assertFalse(Room.objects.filter(hotel=self.hotel, number="900").exists())


class RoomBulkCreateStatusPermissionTests(APITestCase):
    """H1: a non-available initial status on ANY bulk row also requires
    rooms.status_update, enforced before any write (all-or-nothing)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(self.hotel)

    def _row(self, number, **kw):
        row = {"number": number, "floor": self.floor.id, "room_type": self.rtype.id}
        row.update(kw)
        return row

    def _bulk(self, rooms):
        return self.client.post(
            reverse("rooms:room-bulk-create"),
            {"rooms": rooms},
            format="json",
            **HDR(self.hotel),
        )

    def test_create_only_user_blocked_from_non_available(self):
        staff = add_member(self.hotel, "c@x.com", perms=["rooms.create"])
        self.client.force_authenticate(staff)
        res = self._bulk([self._row("101"), self._row("102", initial_status="dirty")])
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "permission_denied")
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 0)

    def test_create_only_user_all_available_ok(self):
        staff = add_member(self.hotel, "c2@x.com", perms=["rooms.create"])
        self.client.force_authenticate(staff)
        res = self._bulk([self._row("101"), self._row("102")])
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 2)

    def test_create_plus_status_update_user_succeeds(self):
        staff = add_member(
            self.hotel, "cs@x.com", perms=["rooms.create", "rooms.status_update"]
        )
        self.client.force_authenticate(staff)
        res = self._bulk([self._row("101"), self._row("102", initial_status="dirty")])
        self.assertEqual(res.status_code, 201)
        dirty = Room.objects.get(hotel=self.hotel, number="102")
        self.assertEqual(dirty.status, "dirty")
        self.assertEqual(RoomStatusLog.objects.filter(room=dirty).count(), 1)


class BoardReservedByBusinessDateTests(APITestCase):
    """H3: a room is RESERVED only when a blocking reservation COVERS the
    business date (check_in <= business_date < check_out). A purely future
    booking does not reserve the room today; the checkout day frees it."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel, name="F1", number="1")
        self.rtype = make_type(self.hotel)

    def _reserve(self, room, *, in_offset, out_offset, number):
        import datetime

        from apps.reservations.models import Reservation, ReservationRoomLine
        from apps.shifts.services import get_business_date

        base = get_business_date(self.hotel)  # the exact date the board uses
        res = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number=number,
            check_in_date=base + datetime.timedelta(days=in_offset),
            check_out_date=base + datetime.timedelta(days=out_offset),
            primary_guest_name="G",
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel, reservation=res, room_type=self.rtype, room=room,
            quantity=1,
        )
        return res

    def _row(self, number):
        res = self.client.get(
            reverse("rooms:room-operational-board"), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 200)
        return {r["number"]: r for r in res.data["rooms"]}[number]

    def test_future_only_reservation_not_reserved(self):
        room = make_room(self.hotel, self.floor, self.rtype, "101")
        self._reserve(room, in_offset=1, out_offset=3, number="R-FUT")
        row = self._row("101")
        self.assertEqual(row["occupancy_status"], "free")
        self.assertTrue(row["available_now"])
        # ...but it is still surfaced as the NEXT upcoming reservation.
        self.assertEqual(row["next_reservation"]["reservation_number"], "R-FUT")

    def test_covering_reservation_reserved(self):
        room = make_room(self.hotel, self.floor, self.rtype, "102")
        self._reserve(room, in_offset=0, out_offset=2, number="R-COV")
        row = self._row("102")
        self.assertEqual(row["occupancy_status"], "reserved")
        self.assertFalse(row["available_now"])

    def test_checkout_day_frees_room(self):
        # Half-open [check_in, check_out): a reservation whose checkout IS the
        # business date no longer covers it -> the room is free again.
        room = make_room(self.hotel, self.floor, self.rtype, "103")
        self._reserve(room, in_offset=-2, out_offset=0, number="R-OUT")
        row = self._row("103")
        self.assertEqual(row["occupancy_status"], "free")
        self.assertTrue(row["available_now"])

    def test_summary_reserved_counts_only_covering(self):
        covering = make_room(self.hotel, self.floor, self.rtype, "201")
        self._reserve(covering, in_offset=0, out_offset=2, number="R-1")
        future = make_room(self.hotel, self.floor, self.rtype, "202")
        self._reserve(future, in_offset=2, out_offset=4, number="R-2")
        res = self.client.get(
            reverse("rooms:room-operational-board"), **HDR(self.hotel)
        )
        summary = res.data["summary"]
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["reserved"], 1)  # only the covering reservation
        self.assertEqual(summary["available"], 1)  # the future-only room is bookable now


# --- Board additive fields (ROOMS-POLISH-BE) ---------------------------------
# Two PURELY ADDITIVE operational-board DTO fields (no migration, no model
# change): a top-level `currency` (hotel default, USD fallback) and a per-row
# `amenities` list mirrored from the room's room_type.


class BoardCurrencyFieldTests(APITestCase):
    """Top-level `currency` on the operational board (additive)."""

    def _board(self, hotel):
        from apps.rooms.services import operational_board

        return operational_board(hotel)

    def test_currency_from_hotel_settings_when_set(self):
        from apps.hotels.models import HotelSettings

        hotel = make_hotel(slug="cur-eur")
        HotelSettings.objects.create(hotel=hotel, default_currency="EUR")
        self.assertEqual(self._board(hotel)["currency"], "EUR")

    def test_currency_falls_back_to_usd_without_settings(self):
        # No HotelSettings row at all -> USD fallback.
        hotel = make_hotel(slug="cur-none")
        self.assertEqual(self._board(hotel)["currency"], "USD")

    def test_currency_falls_back_to_usd_when_blank(self):
        from apps.hotels.models import HotelSettings

        hotel = make_hotel(slug="cur-blank")
        HotelSettings.objects.create(hotel=hotel, default_currency="")
        self.assertEqual(self._board(hotel)["currency"], "USD")


class BoardAmenitiesFieldTests(APITestCase):
    """Per-row `amenities` on the operational board.

    §6.1: the board `amenities` value is now the room's EFFECTIVE feature list
    (type defaults − exclusions + additions). The payload KEY is unchanged
    (`amenities`) so the frontend board contract is preserved; with empty
    overrides (the default) it still mirrors the type exactly.
    """

    def _rows_by_number(self, hotel):
        from apps.rooms.services import operational_board

        return {r["number"]: r for r in operational_board(hotel)["rooms"]}

    def test_amenities_mirror_room_type_and_default_empty(self):
        hotel = make_hotel(slug="amn")
        floor = make_floor(hotel, name="G", number="0")
        with_amn = make_type(hotel, code="AMN", amenities=["wifi", "tv", "ac"])
        bare = make_type(hotel, code="BARE")  # amenities JSONField defaults to []
        make_room(hotel, floor, with_amn, "201")
        make_room(hotel, floor, bare, "202")

        rows = self._rows_by_number(hotel)
        # Empty overrides -> board `amenities` == effective == type mirror.
        self.assertEqual(rows["201"]["amenities"], ["wifi", "tv", "ac"])
        self.assertIsInstance(rows["201"]["amenities"], list)
        self.assertEqual(rows["202"]["amenities"], [])
        self.assertIsInstance(rows["202"]["amenities"], list)

    def test_board_amenities_reflect_effective_additions_and_exclusions(self):
        hotel = make_hotel(slug="amn-eff")
        floor = make_floor(hotel, name="G", number="0")
        rtype = make_type(hotel, code="EFF", amenities=["wifi", "tv", "ac"])
        make_room(
            hotel, floor, rtype, "301",
            feature_additions=["balcony"], feature_exclusions=["ac"],
        )
        rows = self._rows_by_number(hotel)
        # ac excluded, balcony appended, order = kept type order then additions.
        self.assertEqual(rows["301"]["amenities"], ["wifi", "tv", "balcony"])


class RoomEffectiveFeaturesTests(APITestCase):
    """Round 2 §6.1 — per-room EFFECTIVE features (ADDITIVE overrides).

    effective = live type amenities − feature_exclusions + feature_additions
    (ORDERED, DEDUPED). Overrides are edited on the room UPDATE endpoint under
    the existing ``rooms.update`` permission; type edits flow LIVE to
    non-excluding rooms because effective reads ``room_type.amenities`` at
    access time (no backfill, no copy onto the room).
    """

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "mgr@x.com", kind=MembershipType.MANAGER
        )
        self.client.force_authenticate(self.manager)
        self.floor = make_floor(self.hotel)
        self.rtype = make_type(
            self.hotel, code="STD", amenities=["wifi", "tv", "ac"]
        )
        self.room = make_room(self.hotel, self.floor, self.rtype, "101")

    def _detail_url(self, room=None):
        return reverse("rooms:room-detail", args=[(room or self.room).id])

    def _patch(self, body, room=None, hotel=None):
        return self.client.patch(
            self._detail_url(room), body, format="json", **HDR(hotel or self.hotel)
        )

    # --- model-level effective_features property ----------------------------

    def test_default_effective_mirrors_type(self):
        self.assertEqual(self.room.effective_features, ["wifi", "tv", "ac"])

    def test_addition_appears_in_effective(self):
        self.room.feature_additions = ["balcony"]
        self.assertEqual(
            self.room.effective_features, ["wifi", "tv", "ac", "balcony"]
        )

    def test_exclusion_removed_from_effective(self):
        self.room.feature_exclusions = ["ac"]
        self.assertEqual(self.room.effective_features, ["wifi", "tv"])

    def test_effective_is_ordered_and_deduped(self):
        # An addition equal to a type feature is not repeated; type order kept.
        self.room.feature_additions = ["wifi", "balcony", "balcony"]
        self.room.feature_exclusions = ["tv"]
        self.assertEqual(self.room.effective_features, ["wifi", "ac", "balcony"])

    def test_excluded_feature_never_present_even_if_also_added(self):
        # Robustness: a stale/direct-DB row with the same feature in BOTH lists
        # still never surfaces the excluded feature.
        self.room.feature_additions = ["ac"]
        self.room.feature_exclusions = ["ac"]
        self.assertNotIn("ac", self.room.effective_features)

    def test_type_edit_flows_to_non_excluding_room(self):
        self.rtype.amenities = ["wifi", "tv", "ac", "minibar"]
        self.rtype.save()
        self.room.refresh_from_db()
        self.assertIn("minibar", self.room.effective_features)

    def test_exclusion_survives_type_edit(self):
        self.room.feature_exclusions = ["ac"]
        self.room.save()
        self.rtype.amenities = ["wifi", "tv", "ac", "minibar"]
        self.rtype.save()
        self.room.refresh_from_db()
        eff = self.room.effective_features
        self.assertNotIn("ac", eff)  # exclusion preserved across the type edit
        self.assertIn("minibar", eff)  # new type feature flows in

    def test_change_room_type_recomputes_effective(self):
        other_type = make_type(
            self.hotel, code="LUX", amenities=["jacuzzi", "wifi"]
        )
        self.room.feature_additions = ["balcony"]
        self.room.save()
        self.room.room_type = other_type
        self.room.save()
        self.room.refresh_from_db()
        # room-scoped additions survive; effective recomputes vs the NEW type.
        self.assertEqual(self.room.feature_additions, ["balcony"])
        self.assertEqual(
            self.room.effective_features, ["jacuzzi", "wifi", "balcony"]
        )

    # --- API: read contract --------------------------------------------------

    def test_detail_serializer_exposes_feature_contract(self):
        res = self.client.get(self._detail_url(), **HDR(self.hotel))
        self.assertEqual(res.status_code, 200)
        for key in (
            "feature_additions",
            "feature_exclusions",
            "effective_features",
            "inherited_features",
        ):
            self.assertIn(key, res.data)
        self.assertEqual(res.data["inherited_features"], ["wifi", "tv", "ac"])
        self.assertEqual(res.data["effective_features"], ["wifi", "tv", "ac"])
        self.assertEqual(res.data["feature_additions"], [])
        self.assertEqual(res.data["feature_exclusions"], [])

    # --- API: editing overrides ---------------------------------------------

    def test_patch_addition_appears_in_effective(self):
        res = self._patch({"feature_additions": ["balcony"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["feature_additions"], ["balcony"])
        self.assertEqual(
            res.data["effective_features"], ["wifi", "tv", "ac", "balcony"]
        )
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_additions, ["balcony"])

    def test_patch_exclusion_removes_from_effective_and_board(self):
        from apps.rooms.services import operational_board

        res = self._patch({"feature_exclusions": ["ac"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["effective_features"], ["wifi", "tv"])
        row = next(
            r
            for r in operational_board(self.hotel)["rooms"]
            if r["number"] == "101"
        )
        self.assertEqual(row["amenities"], ["wifi", "tv"])

    def test_reset_to_type_with_empty_overrides(self):
        self._patch(
            {"feature_additions": ["balcony"], "feature_exclusions": ["ac"]}
        )
        res = self._patch({"feature_additions": [], "feature_exclusions": []})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["effective_features"], ["wifi", "tv", "ac"])
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_additions, [])
        self.assertEqual(self.room.feature_exclusions, [])

    def test_features_trimmed_and_deduped_on_write(self):
        res = self._patch(
            {"feature_additions": ["  balcony ", "balcony", "   "]}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["feature_additions"], ["balcony"])

    # --- API: validation -----------------------------------------------------

    def test_feature_in_both_additions_and_exclusions_rejected(self):
        res = self._patch(
            {"feature_additions": ["ac"], "feature_exclusions": ["ac"]}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("feature_additions", res.data["details"])
        self.room.refresh_from_db()  # nothing persisted
        self.assertEqual(self.room.feature_additions, [])
        self.assertEqual(self.room.feature_exclusions, [])

    def test_excluding_non_type_feature_accepted_as_dormant(self):
        # §6.1 (owner semantic): exclusions are PERMANENT per-room overrides. An
        # exclusion MAY name a feature that is NOT currently in the type — a
        # "dormant" exclusion. It is ACCEPTED and PERSISTED, has no effect on
        # the current effective list, and would reactivate if the feature later
        # returns to the type. No auto-cleanup, no silent drop.
        res = self._patch({"feature_exclusions": ["sauna"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["feature_exclusions"], ["sauna"])
        # Nothing currently in the type is named, so effective still mirrors it.
        self.assertEqual(res.data["effective_features"], ["wifi", "tv", "ac"])
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_exclusions, ["sauna"])

    def test_non_list_feature_rejected(self):
        res = self._patch({"feature_additions": "balcony"})
        self.assertEqual(res.status_code, 400)

    def test_non_string_feature_rejected(self):
        res = self._patch({"feature_additions": [123]})
        self.assertEqual(res.status_code, 400)

    # --- API: permanent-override lifecycle (§6.1 owner semantic) -------------

    def test_permanent_exclusion_lifecycle_reactivates(self):
        # End-to-end proof that an exclusion is a PERMANENT per-room override
        # that survives type changes and reactivates when the feature returns.
        #
        # 1) Exclude an INHERITED feature -> stored + dropped from effective.
        res = self._patch({"feature_exclusions": ["ac"]})
        self.assertEqual(res.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_exclusions, ["ac"])
        self.assertEqual(self.room.effective_features, ["wifi", "tv"])

        # 2) Remove the feature FROM THE TYPE -> the exclusion is PRESERVED
        #    (now dormant) and effective simply no longer lists it.
        self.rtype.amenities = ["wifi", "tv"]
        self.rtype.save()
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_exclusions, ["ac"])  # still stored
        self.assertEqual(self.room.effective_features, ["wifi", "tv"])
        self.assertNotIn("ac", self.room.effective_features)

        # 3) Re-add the feature TO THE TYPE -> the STORED exclusion REACTIVATES
        #    and drops it from effective again (no re-save of the room needed).
        self.rtype.amenities = ["wifi", "tv", "ac"]
        self.rtype.save()
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_exclusions, ["ac"])  # never cleaned
        self.assertEqual(self.room.effective_features, ["wifi", "tv"])
        self.assertNotIn("ac", self.room.effective_features)

    def test_patch_other_fields_preserves_dormant_exclusion(self):
        # A dormant exclusion (feature not currently in the type) must survive a
        # PATCH that changes only OTHER fields — overrides are not resubmitted,
        # so they are neither re-validated nor dropped.
        self._patch({"feature_exclusions": ["sauna"]})
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_exclusions, ["sauna"])

        res = self._patch({"display_name": "Corner Suite"})
        self.assertEqual(res.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.display_name, "Corner Suite")
        self.assertEqual(self.room.feature_exclusions, ["sauna"])  # preserved

    # --- API: permissions + tenancy -----------------------------------------

    def test_rooms_update_required_to_edit_features(self):
        viewer = add_member(self.hotel, "viewer@x.com", perms=["rooms.view"])
        self.client.force_authenticate(viewer)
        res = self._patch({"feature_additions": ["balcony"]})
        self.assertEqual(res.status_code, 403)
        self.room.refresh_from_db()
        self.assertEqual(self.room.feature_additions, [])

    def test_rooms_update_permission_can_edit_features(self):
        editor = add_member(self.hotel, "editor@x.com", perms=["rooms.update"])
        self.client.force_authenticate(editor)
        res = self._patch({"feature_additions": ["balcony"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["feature_additions"], ["balcony"])

    def test_tenant_isolation_on_feature_edit(self):
        # A manager of self.hotel cannot reach another hotel's room through its
        # own hotel context (queryset is hotel-scoped) -> 404, no cross-tenant
        # write to the feature fields.
        other = make_hotel(slug="other-feat")
        of = make_floor(other, name="OG")
        ot = make_type(other, code="OTX", amenities=["wifi"])
        oroom = make_room(other, of, ot, "999")
        res = self._patch(
            {"feature_additions": ["balcony"]}, room=oroom, hotel=self.hotel
        )
        self.assertEqual(res.status_code, 404)
        oroom.refresh_from_db()
        self.assertEqual(oroom.feature_additions, [])

    def test_create_ignores_features_and_defaults_empty(self):
        res = self.client.post(
            reverse("rooms:room-list"),
            {
                "number": "150",
                "floor": self.floor.id,
                "room_type": self.rtype.id,
                "feature_additions": ["balcony"],
            },
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)
        room = Room.objects.get(hotel=self.hotel, number="150")
        self.assertEqual(room.feature_additions, [])
        self.assertEqual(room.feature_exclusions, [])


# --- Compact room OPTIONS feed (operations-tab dropdowns, decision 16) --------


class RoomOptionsTests(APITestCase):
    """GET /rooms/options/ — COMPACT, hotel-scoped, server-side searchable,
    paginated (DefaultPagination) options feed for the operations-tab dropdowns.

    Fixes the silent >100-rooms drop (the dropdowns pulled ``rooms/?page_size=100``)
    WITHOUT an unbounded all-rooms response. This is ADDITIVE — the room list
    endpoint is unaffected (asserted below).
    """

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.ground = make_floor(self.hotel, name="Ground", number="0")
        self.first = make_floor(self.hotel, name="First", number="1", sort_order=2)
        self.std = make_type(self.hotel, code="STD", name="Standard")
        self.deluxe = make_type(self.hotel, code="DLX", name="Deluxe")

    def _url(self):
        return reverse("rooms:room-options")

    def _get(self, params=None, hotel=None):
        return self.client.get(self._url(), params or {}, **HDR(hotel or self.hotel))

    # --- permission ---------------------------------------------------------

    def test_requires_rooms_view_permission(self):
        staff = add_member(self.hotel, "np@x.com", perms=["reservations.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._get().status_code, 403)

    def test_staff_with_rooms_view_allowed(self):
        staff = add_member(self.hotel, "v@x.com", perms=["rooms.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._get().status_code, 200)

    def test_unauthenticated_denied(self):
        self.client.force_authenticate(None)
        self.assertEqual(self._get().status_code, 401)

    # --- server-side search -------------------------------------------------

    def test_search_by_number(self):
        make_room(self.hotel, self.ground, self.std, "101")
        make_room(self.hotel, self.ground, self.std, "202")
        rows = self._get({"search": "101"}).data["results"]
        self.assertEqual([r["number"] for r in rows], ["101"])

    def test_search_by_room_type_name(self):
        make_room(self.hotel, self.ground, self.std, "101")  # Standard
        make_room(self.hotel, self.first, self.deluxe, "301")  # Deluxe
        rows = self._get({"search": "delux"}).data["results"]
        self.assertEqual({r["number"] for r in rows}, {"301"})
        self.assertEqual(rows[0]["room_type_name"], "Deluxe")

    def test_search_by_floor_name(self):
        make_room(self.hotel, self.ground, self.std, "101")  # Ground
        make_room(self.hotel, self.first, self.std, "201")  # First
        rows = self._get({"search": "first"}).data["results"]
        self.assertEqual({r["number"] for r in rows}, {"201"})
        self.assertEqual(rows[0]["floor_name"], "First")

    def test_search_is_hotel_scoped(self):
        make_room(self.hotel, self.ground, self.std, "101")
        other = make_hotel(slug="other")
        of = make_floor(other, name="OtherGround")
        ot = make_type(other, code="OSTD", name="OtherStandard")
        make_room(other, of, ot, "101")  # same number, different hotel
        # A plain listing never leaks the other hotel's room...
        self.assertEqual(self._get().data["count"], 1)
        self.assertEqual(
            {r["number"] for r in self._get().data["results"]}, {"101"}
        )
        # ...and neither does a search that WOULD match it by type/floor name.
        self.assertEqual(self._get({"search": "OtherStandard"}).data["count"], 0)
        self.assertEqual(self._get({"search": "OtherGround"}).data["count"], 0)

    def test_other_hotel_rooms_never_appear(self):
        make_room(self.hotel, self.ground, self.std, "101")
        other = make_hotel(slug="other2")
        of = make_floor(other)
        ot = make_type(other, code="OT")
        make_room(other, of, ot, "900")
        numbers = {r["number"] for r in self._get().data["results"]}
        self.assertNotIn("900", numbers)

    # --- pagination / >100 rooms are NOT dropped ----------------------------

    def test_pagination_envelope_and_default_page_size(self):
        for i in range(30):
            make_room(self.hotel, self.ground, self.std, str(100 + i))
        data = self._get().data
        self.assertEqual(data["count"], 30)
        self.assertEqual(len(data["results"]), 25)  # DefaultPagination.page_size
        self.assertIsNotNone(data["next"])  # page 2 reachable

    def test_over_100_rooms_are_not_dropped(self):
        # The exact bug this endpoint fixes: page_size=100 silently dropped every
        # room past the first 100. Seed 105 rooms, walk EVERY page, and prove the
        # union equals all 105 — the later rooms ARE reachable via pagination.
        seeded = {str(100 + i) for i in range(105)}
        for number in sorted(seeded):
            make_room(self.hotel, self.ground, self.std, number)
        collected = []
        page = 1
        while True:
            data = self._get({"page": page}).data
            self.assertEqual(data["count"], 105)
            collected.extend(r["number"] for r in data["results"])
            if not data["next"]:
                break
            page += 1
            self.assertLessEqual(page, 20)  # guard against an infinite loop
        self.assertEqual(len(collected), 105)  # no duplicates, none dropped
        self.assertEqual(set(collected), seeded)  # every room reachable
        # The rooms AFTER the first 100 are present (the precise regression).
        self.assertTrue({"201", "202", "203", "204"}.issubset(set(collected)))

    def test_page_size_is_capped_not_unbounded(self):
        for i in range(105):
            make_room(self.hotel, self.ground, self.std, str(100 + i))
        # Even if a client asks for far more, DefaultPagination caps at 100 —
        # proving this is NOT an unbounded all-rooms endpoint (decision 16).
        data = self._get({"page_size": 500}).data
        self.assertEqual(len(data["results"]), 100)
        self.assertEqual(data["count"], 105)
        self.assertIsNotNone(data["next"])

    # --- compact payload ----------------------------------------------------

    def test_payload_is_compact_only_four_fields(self):
        make_room(
            self.hotel, self.first, self.deluxe, "301", display_name="Sea view"
        )
        row = self._get().data["results"][0]
        self.assertEqual(
            set(row.keys()), {"id", "number", "floor_name", "room_type_name"}
        )
        self.assertEqual(row["number"], "301")
        self.assertEqual(row["floor_name"], "First")
        self.assertEqual(row["room_type_name"], "Deluxe")
        # None of the heavy room-detail fields leak into the dropdown payload.
        for heavy in (
            "status",
            "effective_features",
            "feature_additions",
            "display_name",
            "is_active",
            "created_at",
        ):
            self.assertNotIn(heavy, row)

    # --- archived default ---------------------------------------------------

    def test_archived_rooms_excluded_by_default(self):
        make_room(self.hotel, self.ground, self.std, "101")
        make_room(self.hotel, self.ground, self.std, "102", status="archived")
        self.assertEqual(self._get().data["count"], 1)
        self.assertEqual(
            {r["number"] for r in self._get().data["results"]}, {"101"}
        )

    # --- N+1 ----------------------------------------------------------------

    def test_no_n_plus_one_query_count_constant(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # ONE room on the page, warm up, capture the baseline query count.
        make_room(self.hotel, self.ground, self.std, "100")
        self._get()  # warm any one-time setup
        with CaptureQueriesContext(connection) as ctx:
            resp1 = self._get()
        self.assertEqual(len(resp1.data["results"]), 1)
        baseline = len(ctx.captured_queries)

        # Grow to several rooms across DIFFERENT floors and types (a naive
        # serializer would issue a per-row query for floor_name/room_type_name);
        # select_related keeps the count flat regardless of N.
        make_room(self.hotel, self.first, self.deluxe, "101")
        make_room(self.hotel, self.ground, self.deluxe, "102")
        make_room(self.hotel, self.first, self.std, "103")
        with self.assertNumQueries(baseline):
            resp4 = self._get()
        self.assertEqual(len(resp4.data["results"]), 4)

    # --- the existing room list endpoint is unchanged -----------------------

    def test_existing_room_list_endpoint_unchanged(self):
        # Sanity: the additive options route does not disturb the room list — it
        # still returns the full RoomSerializer shape (heavy fields options drops).
        make_room(self.hotel, self.ground, self.std, "101")
        row = self.client.get(
            reverse("rooms:room-list"), **HDR(self.hotel)
        ).data["results"][0]
        self.assertIn("status", row)
        self.assertIn("effective_features", row)
        self.assertIn("room_type_code", row)
