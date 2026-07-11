"""Tests for stays / front desk (Phase 7 + final closure): access/permissions,
check-in rules (quantity cap, arrival-date guard), check-out (folio gate,
early departure), extend/shorten/room-move, occupancy derivation,
arrivals/departures on the hotel business date, and regression."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

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
# The arrival-date guard (final closure) refuses future arrivals, so test
# reservations are anchored to today's date.
D1 = timezone.localdate()
D2 = D1 + timedelta(days=2)


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
        body = {"checkout_reason": "early test"}  # planned end is D2 (early)
        staff = add_member(self.hotel, "s4@x.com", perms=["stays.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.post(reverse("stays:stay-check-out", args=[stay_id]), body, format="json", **HDR(self.hotel)).status_code,
            403,
        )
        staff2 = add_member(self.hotel, "s5@x.com", perms=["stays.check_out"])
        self.client.force_authenticate(staff2)
        self.assertEqual(
            self.client.post(reverse("stays:stay-check-out", args=[stay_id]), body, format="json", **HDR(self.hotel)).status_code,
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
        # Stays in this class end on D2 (the future), so checking out today is
        # an early departure — the reason is mandatory by the closure rule.
        body.setdefault("checkout_reason", "early departure test")
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


# --------------------------------------------------------------------------- #
# Final closure round                                                          #
# --------------------------------------------------------------------------- #


class CheckInQuantityCapTests(APITestCase):
    """A reservation line never admits more stays than its booked quantity."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.r101 = make_room(self.hotel, self.rtype, "101")
        self.floor = self.r101.floor
        self.r102 = make_room(self.hotel, self.rtype, "102", floor=self.floor)
        self.r103 = make_room(self.hotel, self.rtype, "103", floor=self.floor)
        self.guest = make_guest(self.hotel)

    def _ci(self, res, line, room, hotel=None):
        body = {"reservation": res.id, "primary_guest": self.guest.id, "room": room.id}
        if line is not None:
            body["reservation_line"] = line.id
        return self.client.post(
            reverse("stays:stay-check-in"), body, format="json",
            **HDR(hotel or self.hotel),
        )

    def test_line_qty1_allows_single_stay_only(self):
        res, line = make_reservation(self.hotel, self.rtype, qty=1)
        self.assertEqual(self._ci(res, line, self.r101).status_code, 201)
        r = self._ci(res, line, self.r102)  # DIFFERENT free room, same line
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "reservation_line_full")

    def test_line_qty2_allows_two_stays_only(self):
        res, line = make_reservation(self.hotel, self.rtype, qty=2)
        self.assertEqual(self._ci(res, line, self.r101).status_code, 201)
        self.assertEqual(self._ci(res, line, self.r102).status_code, 201)
        r = self._ci(res, line, self.r103)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "reservation_line_full")

    def test_cancelled_stays_do_not_count(self):
        res, line = make_reservation(self.hotel, self.rtype, qty=1)
        first = self._ci(res, line, self.r101)
        self.assertEqual(first.status_code, 201)
        Stay.objects.filter(pk=first.data["id"]).update(
            status=StayStatus.CANCELLED
        )
        self.assertEqual(self._ci(res, line, self.r102).status_code, 201)

    def test_reservation_level_cap_without_line(self):
        res, _line = make_reservation(self.hotel, self.rtype, qty=1)
        self.assertEqual(self._ci(res, None, self.r101).status_code, 201)
        r = self._ci(res, None, self.r102)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "reservation_line_full")

    def test_normal_check_in_unaffected(self):
        res, line = make_reservation(self.hotel, self.rtype, qty=1)
        r = self._ci(res, line, self.r101)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "in_house")

    def test_cap_isolated_between_hotels(self):
        # Fully admitting a same-shaped reservation in ANOTHER hotel must not
        # consume this hotel's quantity.
        other = make_hotel(slug="other")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        otype = make_type(other)
        oroom = make_room(other, otype, "101")
        oguest = make_guest(other)
        ores, oline = make_reservation(other, otype, qty=1)
        Stay.objects.create(
            hotel=other, reservation=ores, reservation_line=oline, room=oroom,
            primary_guest=oguest, status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1, planned_check_out_date=D2,
            actual_check_in_at=timezone.now(),
        )
        res, line = make_reservation(self.hotel, self.rtype, qty=1)
        self.assertEqual(self._ci(res, line, self.r101).status_code, 201)


class ArrivalDateGuardTests(APITestCase):
    """Check-in is refused before the reservation's arrival date - measured by
    the HOTEL business date, never the server clock."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.room = make_room(self.hotel, self.rtype, "101")
        self.guest = make_guest(self.hotel)

    def _ci(self, res, line, room):
        return self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id,
             "room": room.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )

    def test_arrival_today_checks_in(self):
        res, line = make_reservation(self.hotel, self.rtype, ci=D1, co=D2)
        self.assertEqual(self._ci(res, line, self.room).status_code, 201)

    def test_future_arrival_refused(self):
        res, line = make_reservation(
            self.hotel, self.rtype, ci=D1 + timedelta(days=5), co=D1 + timedelta(days=7)
        )
        r = self._ci(res, line, self.room)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "arrival_date_in_future")
        self.assertEqual(r.data["details"]["business_date"], str(D1))

    def test_past_arrival_still_valid_checks_in(self):
        res, line = make_reservation(
            self.hotel, self.rtype, ci=D1 - timedelta(days=3), co=D2
        )
        self.assertEqual(self._ci(res, line, self.room).status_code, 201)

    def _with_hotel_far_timezone(self):
        """Kiritimati (UTC+14) at a frozen instant where its date differs from
        the server date: 2030-06-01T20:00Z -> server=2030-06-01, hotel=2030-06-02."""
        from apps.hotels.models import HotelSettings

        HotelSettings.objects.update_or_create(
            hotel=self.hotel, defaults={"timezone": "Pacific/Kiritimati"}
        )
        frozen = datetime(2030, 6, 1, 20, 0, tzinfo=dt_timezone.utc)
        return mock.patch(
            "apps.shifts.services.timezone.now", return_value=frozen
        ), date(2030, 6, 1), date(2030, 6, 2)

    def test_business_date_used_not_server_date(self):
        patcher, server_date, hotel_date = self._with_hotel_far_timezone()
        with patcher:
            # Arriving on the HOTEL's date checks in even though the server
            # is still on the previous date...
            res, line = make_reservation(
                self.hotel, self.rtype, ci=hotel_date, co=hotel_date + timedelta(days=2)
            )
            self.assertEqual(self._ci(res, line, self.room).status_code, 201)

    def test_server_date_arrival_is_not_enough(self):
        patcher, server_date, hotel_date = self._with_hotel_far_timezone()
        with patcher:
            # ...while a reservation arriving one day past the hotel date
            # (still "the future" for the hotel) is refused with the hotel's
            # business date in the details.
            res, line = make_reservation(
                self.hotel, self.rtype,
                ci=hotel_date + timedelta(days=1), co=hotel_date + timedelta(days=3),
            )
            r = self._ci(res, line, self.room)
            self.assertEqual(r.status_code, 409)
            self.assertEqual(r.data["code"], "arrival_date_in_future")
            self.assertEqual(r.data["details"]["business_date"], str(hotel_date))

    def test_arrivals_and_departures_views_use_business_date(self):
        patcher, server_date, hotel_date = self._with_hotel_far_timezone()
        with patcher:
            # An arrival dated on the HOTEL's business date is listed...
            make_reservation(
                self.hotel, self.rtype, ci=hotel_date, co=hotel_date + timedelta(days=2)
            )
            # ...while one dated on the SERVER's date is not.
            make_reservation(
                self.hotel, self.rtype, ci=server_date - timedelta(days=1),
                co=server_date,
            )
            r = self.client.get(reverse("stays:stay-arrivals-today"), **HDR(self.hotel))
            self.assertEqual(len(r.data), 1)
            self.assertEqual(r.data[0]["check_in_date"], str(hotel_date))
            # Departures: an in-house stay planned to end on the hotel date.
            res, line = make_reservation(
                self.hotel, self.rtype, ci=hotel_date - timedelta(days=1), co=hotel_date
            )
            Stay.objects.create(
                hotel=self.hotel, reservation=res, reservation_line=line,
                room=self.room, primary_guest=self.guest,
                status=StayStatus.IN_HOUSE,
                planned_check_in_date=res.check_in_date,
                planned_check_out_date=res.check_out_date,
                actual_check_in_at=timezone.now(),
            )
            r = self.client.get(
                reverse("stays:stay-departures-today"), **HDR(self.hotel)
            )
            self.assertEqual(r.data["count"], 1)


class StayChangeBase(APITestCase):
    """Shared setup for extend / shorten / move tests: an in-house stay on
    room 101, arrived today, planned check-out D1+3."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.r101 = make_room(self.hotel, self.rtype, "101")
        self.floor = self.r101.floor
        self.r102 = make_room(self.hotel, self.rtype, "102", floor=self.floor)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(
            self.hotel, self.rtype, ci=D1, co=D1 + timedelta(days=3)
        )
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": self.res.id, "reservation_line": self.line.id,
             "room": self.r101.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        assert r.status_code == 201, r.data
        self.stay = Stay.objects.get(pk=r.data["id"])

    def _post(self, name, body, stay=None):
        return self.client.post(
            reverse(f"stays:{name}", args=[(stay or self.stay).id]),
            body, format="json", **HDR(self.hotel),
        )


class ExtendStayTests(StayChangeBase):
    def test_extend_success_updates_stay_and_reservation(self):
        new_end = D1 + timedelta(days=5)
        r = self._post("stay-extend", {"new_check_out_date": str(new_end), "reason": "guest asked"})
        self.assertEqual(r.status_code, 200)
        self.stay.refresh_from_db()
        self.res.refresh_from_db()
        self.assertEqual(self.stay.planned_check_out_date, new_end)
        self.assertEqual(self.res.check_out_date, new_end)
        log = StayStatusLog.objects.filter(stay=self.stay).latest("id")
        self.assertIn("extended", log.note)
        self.assertIn("guest asked", log.note)
        self.assertEqual(log.changed_by, self.manager)

    def test_extend_requires_later_date(self):
        r = self._post("stay-extend", {"new_check_out_date": str(D1 + timedelta(days=2))})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_stay_change")

    def test_extend_blocked_by_next_reservation_on_room(self):
        # Back-to-back next booking pinned to the same room.
        make_reservation(
            self.hotel, self.rtype, room=self.r101,
            ci=D1 + timedelta(days=3), co=D1 + timedelta(days=5),
        )
        r = self._post("stay-extend", {"new_check_out_date": str(D1 + timedelta(days=4))})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_assignment_conflict")

    def test_extend_blocked_when_type_fully_booked(self):
        # Both remaining slots of the type are consumed over the extension
        # window: 102 is pinned and one unassigned booking floats.
        make_reservation(
            self.hotel, self.rtype, room=self.r102,
            ci=D1 + timedelta(days=3), co=D1 + timedelta(days=5),
        )
        make_reservation(
            self.hotel, self.rtype,
            ci=D1 + timedelta(days=3), co=D1 + timedelta(days=5),
        )
        r = self._post("stay-extend", {"new_check_out_date": str(D1 + timedelta(days=4))})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "no_availability")

    def test_extend_refused_on_maintenance_room(self):
        Room.objects.filter(pk=self.r101.pk).update(status=RoomStatus.MAINTENANCE)
        r = self._post("stay-extend", {"new_check_out_date": str(D1 + timedelta(days=5))})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_not_ready")

    def test_extend_requires_in_house(self):
        self.client.post(
            reverse("stays:stay-check-out", args=[self.stay.id]),
            {"checkout_reason": "early"}, format="json", **HDR(self.hotel),
        )
        r = self._post("stay-extend", {"new_check_out_date": str(D1 + timedelta(days=5))})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_stay_change")

    def test_extend_permission_enforced(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["stays.view"])
        self.client.force_authenticate(staff)
        r = self._post("stay-extend", {"new_check_out_date": str(D1 + timedelta(days=5))})
        self.assertEqual(r.status_code, 403)
        staff2 = add_member(self.hotel, "se@x.com", perms=["stays.extend"])
        self.client.force_authenticate(staff2)
        r = self._post("stay-extend", {"new_check_out_date": str(D1 + timedelta(days=5))})
        self.assertEqual(r.status_code, 200)


class ShortenStayTests(StayChangeBase):
    def test_shorten_success_frees_inventory(self):
        from apps.reservations.availability import AvailabilityService

        new_end = D1 + timedelta(days=1)
        r = self._post("stay-shorten", {"new_check_out_date": str(new_end), "reason": "plans changed"})
        self.assertEqual(r.status_code, 200)
        self.stay.refresh_from_db()
        self.res.refresh_from_db()
        self.assertEqual(self.stay.planned_check_out_date, new_end)
        self.assertEqual(self.res.check_out_date, new_end)
        # The freed window no longer consumes inventory.
        self.assertEqual(
            AvailabilityService.reserved_quantity(
                self.hotel, self.rtype, new_end, D1 + timedelta(days=3)
            ),
            0,
        )
        self.assertEqual(self.stay.status, StayStatus.IN_HOUSE)

    def test_shorten_requires_earlier_date(self):
        r = self._post("stay-shorten", {"new_check_out_date": str(D1 + timedelta(days=3))})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_stay_change")

    def test_shorten_not_before_business_date(self):
        r = self._post("stay-shorten", {"new_check_out_date": str(D1 - timedelta(days=1))})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["details"]["reason"], "before_business_date")

    def test_shorten_not_on_or_before_check_in(self):
        r = self._post("stay-shorten", {"new_check_out_date": str(D1)})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["details"]["reason"], "before_check_in")

    def test_shorten_never_checks_out_and_keeps_charges(self):
        from apps.finance import services as fin
        from apps.finance.models import PostingStatus

        # Check-in auto-opens the stay folio (folio closure round) — reuse it.
        folio = fin.ensure_stay_folio(self.stay)
        charge = fin.add_charge(
            folio, charge_type="service", description="minibar",
            quantity=1, unit_amount="30.00",
        )
        r = self._post("stay-shorten", {"new_check_out_date": str(D1 + timedelta(days=1))})
        self.assertEqual(r.status_code, 200)
        self.stay.refresh_from_db()
        charge.refresh_from_db()
        self.assertEqual(self.stay.status, StayStatus.IN_HOUSE)
        self.assertEqual(charge.status, PostingStatus.POSTED)

    def test_shorten_permission_enforced(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["stays.view"])
        self.client.force_authenticate(staff)
        r = self._post("stay-shorten", {"new_check_out_date": str(D1 + timedelta(days=1))})
        self.assertEqual(r.status_code, 403)


class RoomMoveTests(StayChangeBase):
    def setUp(self):
        super().setUp()
        # A one-guest type for the capacity test.
        self.small_type = RoomType.objects.create(
            hotel=self.hotel, name="Single", code="SGL",
            base_capacity=1, max_capacity=1,
        )
        self.r201 = make_room(self.hotel, self.small_type, "201", floor=self.floor)

    def _move(self, room, reason="AC broken", stay=None):
        return self._post(
            "stay-move-room", {"room": room.id, "reason": reason}, stay=stay
        )

    def test_move_success(self):
        r = self._move(self.r102)
        self.assertEqual(r.status_code, 200)
        self.stay.refresh_from_db()
        self.r101.refresh_from_db()
        self.assertEqual(self.stay.room_id, self.r102.id)
        self.assertEqual(self.stay.status, StayStatus.IN_HOUSE)
        self.assertEqual(self.r101.status, RoomStatus.DIRTY)
        # Move log: old room, new room, actor, reason.
        log = StayStatusLog.objects.filter(stay=self.stay).latest("id")
        self.assertIn("room moved 101 -> 102", log.note)
        self.assertIn("AC broken", log.note)
        self.assertEqual(log.changed_by, self.manager)
        # One cleanup task for the vacated room, NOT keyed to the stay (the
        # real check-out task must stay possible later).
        from apps.operations.models import HousekeepingTask

        task = HousekeepingTask.objects.get(hotel=self.hotel, room=self.r101)
        self.assertIsNone(task.stay_id)
        # The line follows the guest so the new room stays protected.
        self.line.refresh_from_db()
        self.assertEqual(self.line.room_id, self.r102.id)

    def test_move_then_checkout_still_raises_cleaning_task(self):
        self._move(self.r102)
        self.client.post(
            reverse("stays:stay-check-out", args=[self.stay.id]),
            {"checkout_reason": "early"}, format="json", **HDR(self.hotel),
        )
        from apps.operations.models import HousekeepingTask

        self.assertEqual(
            HousekeepingTask.objects.filter(hotel=self.hotel, stay=self.stay).count(),
            1,
        )

    def test_move_to_occupied_room_refused(self):
        res2, line2 = make_reservation(self.hotel, self.rtype, ci=D1, co=D1 + timedelta(days=2))
        self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res2.id, "reservation_line": line2.id,
             "room": self.r102.id, "primary_guest": make_guest(self.hotel, "G2").id},
            format="json", **HDR(self.hotel),
        )
        r = self._move(self.r102)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_occupied")

    def test_move_to_dirty_or_maintenance_refused(self):
        for st in (RoomStatus.DIRTY, RoomStatus.CLEANING, RoomStatus.MAINTENANCE):
            Room.objects.filter(pk=self.r102.pk).update(status=st)
            r = self._move(self.r102)
            self.assertEqual(r.status_code, 409, st)
            self.assertEqual(r.data["code"], "room_not_ready")

    def test_move_capacity_refused(self):
        # Two companions -> three guests, the single room takes one.
        for name in ("C1", "C2"):
            StayGuest.objects.create(
                hotel=self.hotel, stay=self.stay,
                guest=make_guest(self.hotel, name), role="companion",
            )
        r = self._move(self.r201)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["details"]["reason"], "capacity_exceeded")

    def test_move_blocked_by_next_reservation_on_new_room(self):
        make_reservation(
            self.hotel, self.rtype, room=self.r102,
            ci=D1 + timedelta(days=1), co=D1 + timedelta(days=3),
        )
        r = self._move(self.r102)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_assignment_conflict")

    def test_move_requires_reason(self):
        r = self._post("stay-move-room", {"room": self.r102.id, "reason": ""})
        self.assertEqual(r.status_code, 400)

    def test_move_same_room_refused(self):
        r = self._move(self.r101)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["details"]["reason"], "same_room")

    def test_move_cross_hotel_room_refused(self):
        other = make_hotel(slug="o")
        oroom = make_room(other, make_type(other), "901")
        r = self._move(oroom)
        self.assertEqual(r.status_code, 404)

    def test_move_permission_enforced(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["stays.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._move(self.r102).status_code, 403)
        staff2 = add_member(self.hotel, "sm@x.com", perms=["stays.move_room"])
        self.client.force_authenticate(staff2)
        self.assertEqual(self._move(self.r102).status_code, 200)

    def test_move_candidates_exclude_bad_rooms(self):
        # 102 available+free -> listed; occupied (101 = ours), dirty and
        # pinned rooms -> excluded; the single room fits one guest -> listed.
        r103 = make_room(self.hotel, self.rtype, "103", floor=self.floor,
                         status=RoomStatus.DIRTY)
        r104 = make_room(self.hotel, self.rtype, "104", floor=self.floor)
        make_reservation(  # pins 104 for the stay's window
            self.hotel, self.rtype, room=r104, ci=D1, co=D1 + timedelta(days=3)
        )
        r = self.client.get(
            reverse("stays:stay-move-candidates", args=[self.stay.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        numbers = {c["number"] for c in r.data}
        self.assertIn("102", numbers)
        self.assertNotIn("101", numbers)
        self.assertNotIn("103", numbers)
        self.assertNotIn("104", numbers)
        self.assertIn("201", numbers)  # 1 guest fits the single room


class CheckOutFolioTests(StayChangeBase):
    def _co(self, **body):
        body.setdefault("checkout_reason", "early departure test")
        return self.client.post(
            reverse("stays:stay-check-out", args=[self.stay.id]),
            body, format="json", **HDR(self.hotel),
        )

    def _folio(self):
        from apps.finance import services as fin

        # Check-in auto-opens the stay folio (folio closure round) — reuse it.
        return fin.ensure_stay_folio(self.stay)

    def test_checkout_without_folio_succeeds(self):
        self.assertEqual(self._co().status_code, 200)

    def test_checkout_zero_balance_closes_folio(self):
        from apps.finance import services as fin
        from apps.finance.models import FolioStatus

        folio = self._folio()
        fin.add_charge(folio, charge_type="service", description="dinner",
                       quantity=1, unit_amount="50.00")
        fin.record_payment(folio, amount="50.00", method="cash")
        self.assertEqual(self._co().status_code, 200)
        folio.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.CLOSED)

    def test_checkout_blocked_on_positive_balance(self):
        from apps.finance import services as fin
        from apps.finance.models import FolioStatus

        folio = self._folio()
        fin.add_charge(folio, charge_type="service", description="dinner",
                       quantity=1, unit_amount="50.00")
        r = self._co()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_balance_outstanding")
        # Nothing changed: stay in-house, room untouched, folio open.
        self.stay.refresh_from_db()
        self.r101.refresh_from_db()
        folio.refresh_from_db()
        self.assertEqual(self.stay.status, StayStatus.IN_HOUSE)
        self.assertEqual(self.r101.status, RoomStatus.AVAILABLE)
        self.assertEqual(folio.status, FolioStatus.OPEN)

    def test_checkout_blocked_on_negative_balance(self):
        from apps.finance import services as fin

        folio = self._folio()
        fin.record_payment(folio, amount="30.00", method="cash")
        r = self._co()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_balance_outstanding")

    def test_folio_summary_endpoint(self):
        from apps.finance import services as fin

        folio = self._folio()
        fin.add_charge(folio, charge_type="service", description="dinner",
                       quantity=1, unit_amount="80.00")
        r = self.client.get(
            reverse("stays:stay-folio-summary", args=[self.stay.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["has_folio"])
        self.assertTrue(r.data["is_early_departure"])
        self.assertEqual(r.data["balance"], "80.00")
        self.assertEqual(len(r.data["open_folios"]), 1)


class EarlyDepartureTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.r101 = make_room(self.hotel, self.rtype, "101")
        self.r102 = make_room(self.hotel, self.rtype, "102", floor=self.r101.floor)
        self.guest = make_guest(self.hotel)

    def _admit(self, *, ci, co, room=None):
        res, line = make_reservation(self.hotel, self.rtype, ci=ci, co=co)
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id,
             "room": (room or self.r101).id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        assert r.status_code == 201, r.data
        return res, Stay.objects.get(pk=r.data["id"])

    def _co(self, stay, **body):
        return self.client.post(
            reverse("stays:stay-check-out", args=[stay.id]),
            body, format="json", **HDR(self.hotel),
        )

    def test_on_time_departure_needs_no_reason(self):
        res, stay = self._admit(ci=D1 - timedelta(days=2), co=D1)
        r = self._co(stay)
        self.assertEqual(r.status_code, 200)
        log = StayStatusLog.objects.filter(stay=stay).latest("id")
        self.assertEqual(log.note, "checked out")

    def test_early_departure_requires_reason(self):
        res, stay = self._admit(ci=D1, co=D1 + timedelta(days=4))
        r = self._co(stay)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "early_departure_reason_required")
        r = self._co(stay, checkout_reason="flight change")
        self.assertEqual(r.status_code, 200)
        log = StayStatusLog.objects.filter(stay=stay).latest("id")
        self.assertIn("early departure", log.note)

    def test_early_departure_releases_inventory(self):
        from apps.reservations.availability import AvailabilityService

        res, stay = self._admit(ci=D1, co=D1 + timedelta(days=5))
        self.assertEqual(
            self._co(stay, checkout_reason="left early").status_code, 200
        )
        res.refresh_from_db()
        # The reservation end shrinks to the one-night floor...
        self.assertEqual(res.check_out_date, D1 + timedelta(days=1))
        # ...so the freed nights consume nothing.
        self.assertEqual(
            AvailabilityService.reserved_quantity(
                self.hotel, self.rtype, D1 + timedelta(days=1), D1 + timedelta(days=5)
            ),
            0,
        )

    def test_early_departure_keeps_charges(self):
        from apps.finance import services as fin
        from apps.finance.models import PostingStatus

        res, stay = self._admit(ci=D1, co=D1 + timedelta(days=4))
        # Check-in auto-opens the stay folio (folio closure round) — reuse it.
        folio = fin.ensure_stay_folio(stay)
        fin.add_charge(folio, charge_type="service", description="laundry",
                       quantity=1, unit_amount="20.00")
        fin.record_payment(folio, amount="20.00", method="cash")
        self.assertEqual(
            self._co(stay, checkout_reason="left early").status_code, 200
        )
        charge = folio.charges.get()
        self.assertEqual(charge.status, PostingStatus.POSTED)

    def test_early_departure_does_not_touch_other_reservations(self):
        other_res, _ = make_reservation(
            self.hotel, self.rtype, room=self.r102, ci=D1, co=D1 + timedelta(days=5)
        )
        res, stay = self._admit(ci=D1, co=D1 + timedelta(days=5))
        self._co(stay, checkout_reason="left early")
        other_res.refresh_from_db()
        self.assertEqual(other_res.check_out_date, D1 + timedelta(days=5))

    def test_early_departure_multi_line_keeps_pending_sibling_window(self):
        # A second, not-yet-admitted line still needs the original window, so
        # the reservation must NOT shrink.
        res, line = make_reservation(self.hotel, self.rtype, ci=D1, co=D1 + timedelta(days=4))
        ReservationRoomLine.objects.create(
            hotel=self.hotel, reservation=res, room_type=self.rtype, quantity=1
        )
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id,
             "room": self.r101.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        stay = Stay.objects.get(pk=r.data["id"])
        self._co(stay, checkout_reason="left early")
        res.refresh_from_db()
        self.assertEqual(res.check_out_date, D1 + timedelta(days=4))


class CheckInFolioTests(APITestCase):
    """Folio closure round: every successful check-in opens the stay's ONE
    operational folio inside the same transaction (rollback on failure)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(self.hotel, self.rtype)

    def _check_in(self):
        return self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": self.res.id, "reservation_line": self.line.id,
             "room": self.room.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )

    def test_check_in_creates_open_folio(self):
        from apps.finance.models import Folio, FolioStatus

        self.assertEqual(self._check_in().status_code, 201)
        stay = Stay.objects.get(hotel=self.hotel)
        folio = Folio.objects.get(hotel=self.hotel, stay=stay)
        self.assertEqual(folio.status, FolioStatus.OPEN)
        self.assertEqual(folio.guest_id, self.guest.id)
        self.assertEqual(folio.reservation_id, self.res.id)
        self.assertEqual(folio.customer_name, self.guest.full_name)
        self.assertEqual(folio.currency, "USD")

    def test_check_in_folio_is_idempotent_single(self):
        from apps.finance.models import Folio
        from apps.finance.services import ensure_stay_folio

        self._check_in()
        stay = Stay.objects.get(hotel=self.hotel)
        first = Folio.objects.get(hotel=self.hotel, stay=stay)
        again = ensure_stay_folio(stay)
        self.assertEqual(again.id, first.id)
        self.assertEqual(Folio.objects.filter(hotel=self.hotel, stay=stay).count(), 1)

    def test_failed_folio_rolls_back_whole_check_in(self):
        from apps.finance.models import Folio

        with mock.patch(
            "apps.finance.services.next_number", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self._check_in()
        self.assertEqual(Stay.objects.filter(hotel=self.hotel).count(), 0)
        self.assertEqual(Folio.objects.filter(hotel=self.hotel).count(), 0)

    def test_second_manual_folio_for_stay_refused_via_api(self):
        self._check_in()
        stay = Stay.objects.get(hotel=self.hotel)
        # The manager membership inherits all finance permissions.
        r = self.client.post(
            reverse("finance:folio-list"), {"stay": stay.id}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_finance_operation")
