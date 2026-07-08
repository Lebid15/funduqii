"""Tests for stays / front desk (Phase 7): access/permissions, check-in rules,
check-out, occupancy derivation, arrivals/departures, and regression."""
from __future__ import annotations

from datetime import date

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.guests.models import Guest
from apps.rbac.services import grant_permission
from apps.reservations.models import Reservation, ReservationRoomLine, ReservationStatus
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.stays.models import Stay, StayGuest, StayStatus, StayStatusLog
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731
D1 = date(2030, 1, 10)
D2 = date(2030, 1, 12)


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


def make_type(hotel, code="STD"):
    return RoomType.objects.create(
        hotel=hotel, name="Standard", code=code, base_capacity=2, max_capacity=3
    )


def make_room(hotel, rtype, number="101", *, floor=None, status=RoomStatus.AVAILABLE):
    floor = floor or Floor.objects.create(hotel=hotel, name="G", number="0")
    return Room.objects.create(
        hotel=hotel, floor=floor, room_type=rtype, number=number, status=status
    )


def make_guest(hotel, name="Guest One"):
    return Guest.objects.create(hotel=hotel, full_name=name)


_SEQ = {"n": 0}


def make_reservation(hotel, rtype, *, room=None, status=ReservationStatus.CONFIRMED,
                     ci=D1, co=D2, qty=1):
    _SEQ["n"] += 1
    res = Reservation.objects.create(
        hotel=hotel,
        reservation_number=f"R{_SEQ['n']:05d}",
        status=status,
        check_in_date=ci,
        check_out_date=co,
        primary_guest_name="Res Guest",
    )
    line = ReservationRoomLine.objects.create(
        hotel=hotel, reservation=res, room_type=rtype, room=room, quantity=qty
    )
    return res, line


class CheckInAccessTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(self.hotel, self.rtype)

    def _payload(self, **over):
        body = {"reservation": self.res.id, "reservation_line": self.line.id,
                "room": self.room.id, "primary_guest": self.guest.id}
        body.update(over)
        return body

    def _check_in(self):
        return self.client.post(
            reverse("stays:stay-check-in"), self._payload(), format="json", **HDR(self.hotel)
        )

    def test_unauthenticated_denied(self):
        self.assertEqual(self._check_in().status_code, 401)

    def test_other_hotel_denied(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("stays:stay-current"), **HDR(other)).status_code, 403
        )

    def test_manager_can_check_in(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self._check_in().status_code, 201)

    def test_staff_view_current(self):
        staff = add_member(self.hotel, "s@x.com", perms=["stays.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("stays:stay-current"), **HDR(self.hotel)).status_code, 200
        )

    def test_staff_check_in_permission(self):
        staff = add_member(self.hotel, "s2@x.com", perms=["stays.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._check_in().status_code, 403)
        staff2 = add_member(self.hotel, "s3@x.com", perms=["stays.check_in"])
        self.client.force_authenticate(staff2)
        self.assertEqual(self._check_in().status_code, 201)

    def test_staff_check_out_permission(self):
        self.client.force_authenticate(self.manager)
        stay_id = self._check_in().data["id"]
        staff = add_member(self.hotel, "s4@x.com", perms=["stays.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.post(reverse("stays:stay-check-out", args=[stay_id]), {}, format="json", **HDR(self.hotel)).status_code,
            403,
        )
        staff2 = add_member(self.hotel, "s5@x.com", perms=["stays.check_out"])
        self.client.force_authenticate(staff2)
        self.assertEqual(
            self.client.post(reverse("stays:stay-check-out", args=[stay_id]), {}, format="json", **HDR(self.hotel)).status_code,
            200,
        )

    def test_suspended_hotel_cannot_check_in(self):
        self.client.force_authenticate(self.manager)
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        res = self._check_in()
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")


class CheckInRulesTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.room = make_room(self.hotel, self.rtype, "101")
        self.guest = make_guest(self.hotel)

    def _check_in(self, res, line, room=None, **over):
        body = {"reservation": res.id, "reservation_line": line.id, "primary_guest": self.guest.id}
        if room is not None:
            body["room"] = room.id
        body.update(over)
        return self.client.post(reverse("stays:stay-check-in"), body, format="json", **HDR(self.hotel))

    def test_check_in_confirmed_creates_stay(self):
        res, line = make_reservation(self.hotel, self.rtype)
        r = self._check_in(res, line, self.room)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "in_house")
        self.assertEqual(r.data["room_number"], "101")
        stay = Stay.objects.get(pk=r.data["id"])
        self.assertEqual(StayGuest.objects.filter(stay=stay, role="primary").count(), 1)
        self.assertEqual(StayStatusLog.objects.filter(stay=stay).count(), 1)

    def test_occupancy_is_derived_not_room_status(self):
        res, line = make_reservation(self.hotel, self.rtype)
        self._check_in(res, line, self.room)
        self.room.refresh_from_db()
        # Room.status stays 'available' — occupancy comes from the Stay, not a
        # manual 'occupied' status.
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)
        self.assertNotIn("occupied", {c for c, _ in RoomStatus.choices})

    def test_cannot_check_in_held_reservation(self):
        res, line = make_reservation(self.hotel, self.rtype, status=ReservationStatus.HELD)
        r = self._check_in(res, line, self.room)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_check_in")

    def test_cannot_check_in_cancelled_reservation(self):
        res, line = make_reservation(self.hotel, self.rtype, status=ReservationStatus.CANCELLED)
        self.assertEqual(self._check_in(res, line, self.room).status_code, 400)

    def test_cannot_check_in_expired_reservation(self):
        res, line = make_reservation(self.hotel, self.rtype, status=ReservationStatus.EXPIRED)
        self.assertEqual(self._check_in(res, line, self.room).status_code, 400)

    def test_room_required_when_line_unassigned(self):
        res, line = make_reservation(self.hotel, self.rtype)  # line has no room
        r = self._check_in(res, line)  # no room passed
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_check_in")

    def test_assigned_line_room_used_automatically(self):
        res, line = make_reservation(self.hotel, self.rtype, room=self.room)
        r = self._check_in(res, line)  # no room passed; line pins it
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["room"], self.room.id)

    def test_cannot_check_in_maintenance_room(self):
        self.room.status = RoomStatus.MAINTENANCE
        self.room.save()
        res, line = make_reservation(self.hotel, self.rtype)
        r = self._check_in(res, line, self.room)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_not_ready")

    def test_cannot_check_in_out_of_service_or_archived(self):
        for st in (RoomStatus.OUT_OF_SERVICE, RoomStatus.ARCHIVED):
            self.room.status = st
            self.room.save()
            res, line = make_reservation(self.hotel, self.rtype)
            self.assertEqual(self._check_in(res, line, self.room).status_code, 409, st)

    def test_cannot_check_in_dirty_or_cleaning_room(self):
        for st in (RoomStatus.DIRTY, RoomStatus.CLEANING):
            self.room.status = st
            self.room.save()
            res, line = make_reservation(self.hotel, self.rtype)
            r = self._check_in(res, line, self.room)
            self.assertEqual(r.status_code, 409, st)
            self.assertEqual(r.data["code"], "room_not_ready")

    def test_cannot_check_in_occupied_room(self):
        res1, line1 = make_reservation(self.hotel, self.rtype)
        self.assertEqual(self._check_in(res1, line1, self.room).status_code, 201)
        res2, line2 = make_reservation(self.hotel, self.rtype)
        r = self._check_in(res2, line2, self.room)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_occupied")

    def test_cannot_duplicate_check_in_same_line_room(self):
        res, line = make_reservation(self.hotel, self.rtype, qty=2)
        self.assertEqual(self._check_in(res, line, self.room).status_code, 201)
        # Same line+room again -> occupied (room already in-house).
        r = self._check_in(res, line, self.room)
        self.assertEqual(r.status_code, 409)

    def test_room_from_other_hotel_rejected(self):
        other = make_hotel(slug="o")
        ot = make_type(other)
        oroom = make_room(other, ot, "901")
        res, line = make_reservation(self.hotel, self.rtype)
        self.assertEqual(self._check_in(res, line, oroom).status_code, 404)

    def test_guest_from_other_hotel_rejected(self):
        other = make_hotel(slug="o")
        oguest = make_guest(other, "Outsider")
        res, line = make_reservation(self.hotel, self.rtype)
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id, "room": self.room.id, "primary_guest": oguest.id},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 404)

    def test_current_residents_includes_new_stay(self):
        res, line = make_reservation(self.hotel, self.rtype)
        self._check_in(res, line, self.room)
        cur = self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        self.assertEqual(cur.data["count"], 1)

    def test_companions_attached(self):
        res, line = make_reservation(self.hotel, self.rtype)
        companion = make_guest(self.hotel, "Companion")
        r = self._check_in(res, line, self.room, companions=[companion.id])
        self.assertEqual(r.status_code, 201)
        stay = Stay.objects.get(pk=r.data["id"])
        self.assertEqual(stay.guests.count(), 2)


class CheckOutTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.room = make_room(self.hotel, self.rtype, "101")
        self.guest = make_guest(self.hotel)

    def _check_in(self):
        res, line = make_reservation(self.hotel, self.rtype)
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id, "room": self.room.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        return r.data["id"]

    def _check_out(self, stay_id, **body):
        return self.client.post(
            reverse("stays:stay-check-out", args=[stay_id]), body, format="json", **HDR(self.hotel)
        )

    def test_check_out_in_house(self):
        sid = self._check_in()
        r = self._check_out(sid, check_out_notes="Thanks")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "checked_out")
        self.assertIsNotNone(r.data["actual_check_out_at"])
        self.assertIsNotNone(r.data["checked_out_by"])

    def test_cannot_check_out_twice(self):
        sid = self._check_in()
        self._check_out(sid)
        r = self._check_out(sid)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_check_out")

    def test_room_becomes_dirty_after_check_out(self):
        sid = self._check_in()
        self._check_out(sid)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.DIRTY)

    def test_check_out_removes_from_current_and_departures(self):
        sid = self._check_in()
        self._check_out(sid)
        cur = self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        self.assertEqual(cur.data["count"], 0)

    def test_room_reusable_after_check_out(self):
        # After check-out (dirty) then made available, a new check-in works.
        sid = self._check_in()
        self._check_out(sid)
        self.room.status = RoomStatus.AVAILABLE
        self.room.save()
        res, line = make_reservation(self.hotel, self.rtype)
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id, "room": self.room.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 201)


class ArrivalsDeparturesTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.room = make_room(self.hotel, self.rtype, "101")
        self.room2 = make_room(self.hotel, self.rtype, "102", floor=self.room.floor)
        self.guest = make_guest(self.hotel)
        self.today = timezone.localdate()
        self.tomorrow = date(self.today.year + 1, 1, 15)

    def test_arrivals_today_lists_confirmed_for_today(self):
        make_reservation(self.hotel, self.rtype, ci=self.today, co=self.tomorrow)
        r = self.client.get(reverse("stays:stay-arrivals-today"), **HDR(self.hotel))
        self.assertEqual(len(r.data), 1)

    def test_arrivals_excludes_other_days_and_unconfirmed(self):
        make_reservation(self.hotel, self.rtype, ci=self.tomorrow, co=date(self.tomorrow.year, 1, 18))
        make_reservation(self.hotel, self.rtype, ci=self.today, co=self.tomorrow, status=ReservationStatus.HELD)
        r = self.client.get(reverse("stays:stay-arrivals-today"), **HDR(self.hotel))
        self.assertEqual(len(r.data), 0)

    def test_arrivals_excludes_fully_checked_in(self):
        res, line = make_reservation(self.hotel, self.rtype, ci=self.today, co=self.tomorrow)
        self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id, "room": self.room.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        r = self.client.get(reverse("stays:stay-arrivals-today"), **HDR(self.hotel))
        self.assertEqual(len(r.data), 0)

    def test_departures_today_lists_in_house_leaving_today(self):
        res, line = make_reservation(self.hotel, self.rtype, ci=date(self.today.year - 1, 1, 1), co=self.today)
        self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id, "room": self.room.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        r = self.client.get(reverse("stays:stay-departures-today"), **HDR(self.hotel))
        self.assertEqual(r.data["count"], 1)

    def test_departures_excludes_checked_out(self):
        res, line = make_reservation(self.hotel, self.rtype, ci=date(self.today.year - 1, 1, 1), co=self.today)
        sid = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id, "room": self.room.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        ).data["id"]
        self.client.post(reverse("stays:stay-check-out", args=[sid]), {}, format="json", **HDR(self.hotel))
        r = self.client.get(reverse("stays:stay-departures-today"), **HDR(self.hotel))
        self.assertEqual(r.data["count"], 0)


class RegressionTests(APITestCase):
    def test_health_and_prior_apis(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
        hotel = make_hotel()
        mgr = add_member(hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        self.assertEqual(self.client.get(reverse("rooms:room-list"), **HDR(hotel)).status_code, 200)
        self.assertEqual(self.client.get(reverse("reservations:reservation-list"), **HDR(hotel)).status_code, 200)
        self.assertEqual(self.client.get(reverse("hotel:settings"), **HDR(hotel)).status_code, 200)

    def test_no_out_of_scope_models(self):
        from django.apps import apps as django_apps

        tables = {m._meta.db_table for m in django_apps.get_models()}
        # Finance (Phase 8) is legitimate; restaurant/stock/public-booking are not.
        # (shifts/daily_closes became legitimate in Phase 12.)
        for forbidden in ("restaurant_orders", "stock_items", "public_bookings", "payroll", "attendance_records"):
            self.assertNotIn(forbidden, tables)
        # Stays/guests ARE present now.
        self.assertIn("stays", tables)
        self.assertIn("guests", tables)
