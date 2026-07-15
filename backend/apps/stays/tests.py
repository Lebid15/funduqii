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


class ImmediateCheckInRegressionTests(APITestCase):
    """RESERVATIONS-FINAL-CLOSURE §3 — protect the atomic immediate check-in path.

    Covers the HIGH-1 fix (commit 1250fad): an occupant whose national id is a
    DIFFERENT raw format but the SAME normalized value as an existing guest must
    REUSE that guest during promotion — never create a duplicate that trips the
    per-hotel unique constraint and rolls the whole check-in back. Also asserts a
    single reused folio, a non-duplicated deposit, and full atomic rollback.
    """

    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(self.hotel, "imm@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)
        self.room = make_room(self.hotel, self.rtype)

    def _run(self, *, occupants=None, deposit=None):
        from apps.stays.orchestration import execute_immediate_check_in

        return execute_immediate_check_in(
            self.hotel,
            lines=[{"room_type": self.rtype, "quantity": 1, "room": self.room}],
            occupants=occupants,
            room=self.room,
            deposit=deposit,
            room_assignment_mode="manual",
            user=self.user,
            check_in_date=D1,
            check_out_date=D2,
            source="walk_in",
            primary_guest_name="Walk In Guest",
        )

    def test_occupant_guest_reused_by_normalized_national_id(self):
        # Existing guest stored as "1234-5678"; the companion arrives as "12345678"
        # — a different raw format but the SAME normalized value.
        existing = Guest.objects.create(
            hotel=self.hotel, full_name="Existing Guest", national_id="1234-5678"
        )
        before = Guest.objects.filter(hotel=self.hotel).count()  # == 1 (existing)

        result = self._run(
            occupants=[
                {
                    "first_name": "Comp",
                    "last_name": "Anion",
                    "national_id": "12345678",
                    "relationship": "other",
                }
            ],
            deposit={"amount": "40.00", "method": "cash"},
        )

        # No IntegrityError; only the PRIMARY guest is new — the companion reused
        # the existing guest (matched on the normalized national id).
        self.assertEqual(
            Guest.objects.filter(hotel=self.hotel).count(), before + 1
        )
        stay = result["stay"]
        companion_guest_ids = set(
            StayGuest.objects.filter(stay=stay).values_list("guest_id", flat=True)
        )
        self.assertIn(existing.id, companion_guest_ids)
        # Stay admitted in-house on the chosen room.
        self.assertEqual(stay.status, StayStatus.IN_HOUSE)
        self.assertEqual(stay.room_id, self.room.id)
        # ONE folio — the deposit folio reused for the stay (no duplicate ledger).
        res = result["reservation"]
        self.assertEqual(res.folios.count(), 1)
        folio = res.folios.get()
        self.assertEqual(folio.stay_id, stay.id)
        # The deposit is not duplicated: exactly one payment on the reused folio.
        self.assertEqual(folio.payments.count(), 1)
        self.assertIsNotNone(result["folio"])
        self.assertEqual(result["folio"].id, folio.id)

    def test_full_rollback_when_a_critical_step_fails(self):
        from apps.finance.models import Folio, Payment
        from apps.stays import orchestration

        before = {
            "res": Reservation.objects.count(),
            "stay": Stay.objects.count(),
            "folio": Folio.objects.count(),
            "payment": Payment.objects.count(),
        }
        # Inject a failure AFTER the reservation + deposit + stay are created; the
        # whole compose is one transaction, so nothing may persist.
        with mock.patch.object(
            orchestration,
            "promote_reservation_occupants",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertRaises(RuntimeError):
                self._run(deposit={"amount": "25.00", "method": "cash"})

        self.assertEqual(Reservation.objects.count(), before["res"])
        self.assertEqual(Stay.objects.count(), before["stay"])
        self.assertEqual(Folio.objects.count(), before["folio"])
        self.assertEqual(Payment.objects.count(), before["payment"])


class RoomChargePostingTests(APITestCase):
    """STAYS-ARRIVALS-DEPARTURES §24/§31 (owner correction) — room nights are
    posted PER NIGHT as they become due by the hotel business date, never all
    front-loaded at check-in; each night is its own idempotent charge; an
    extension defers its nights; an unpriced room posts nothing."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "rc@x.com", kind=MembershipType.MANAGER)
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3, base_rate="100.00",
        )
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(
            self.hotel, self.rtype, room=self.room
        )  # D1 -> D2 = nights D1, D1+1

    def _check_in(self, res, line, room, guest):
        from apps.stays.services import CheckInService

        return CheckInService.execute(
            self.hotel,
            reservation=res,
            reservation_line=line,
            room=room,
            primary_guest=guest,
            companions=(),
            user=self.manager,
        )

    def test_no_future_nights_posted_at_check_in(self):
        from apps.finance.models import ChargeType
        from apps.finance.services import folio_balance

        # Arrival day (business_date == D1): no night has been consumed yet, so
        # the folio must NOT be pre-loaded with the whole planned stay.
        stay = self._check_in(self.res, self.line, self.room, self.guest)
        folio = stay.folios.get()
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 0)
        self.assertEqual(str(folio_balance(folio)["balance"]), "0.00")

    def test_due_nights_posted_each_as_its_own_charge(self):
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges, folio_balance

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        folio = stay.folios.get()
        # As of the departure date, both nights (D1, D1+1) are due.
        posted = ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(posted, 2)
        charges = folio.charges.filter(
            type=ChargeType.ROOM, status=PostingStatus.POSTED
        )
        self.assertEqual(charges.count(), 2)  # one charge PER night
        for c in charges:
            self.assertEqual(str(c.total_amount), "100.00")
        self.assertEqual(str(folio_balance(folio)["balance"]), "200.00")

    def test_posting_is_idempotent(self):
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        folio = stay.folios.get()
        self.assertEqual(ensure_due_room_charges(stay, as_of=D2, user=self.manager), 2)
        # A retry / daily close / pre-checkout net must never double-post.
        self.assertEqual(ensure_due_room_charges(stay, as_of=D2, user=self.manager), 0)
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 2)

    def test_early_departure_charges_only_consumed_nights(self):
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges, folio_balance

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        folio = stay.folios.get()
        # Leaving on D1+1: only night D1 was consumed; the future night is NOT posted.
        posted = ensure_due_room_charges(
            stay, as_of=D1 + timedelta(days=1), user=self.manager
        )
        self.assertEqual(posted, 1)
        self.assertEqual(
            folio.charges.filter(type=ChargeType.ROOM, status=PostingStatus.POSTED).count(),
            1,
        )
        self.assertEqual(str(folio_balance(folio)["balance"]), "100.00")

    def test_extension_defers_its_nights(self):
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges, folio_balance
        from apps.stays.services import ExtendStayService

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        folio = stay.folios.get()
        ExtendStayService.execute(
            stay, new_check_out_date=D2 + timedelta(days=1), user=self.manager
        )
        stay.refresh_from_db()  # pick up the new planned_check_out_date
        # Extending posts NOTHING immediately (business_date is still D1).
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 0)
        # As of the new departure, the 3 nights (D1, D1+1, D2) are due.
        posted = ensure_due_room_charges(
            stay, as_of=D2 + timedelta(days=1), user=self.manager
        )
        self.assertEqual(posted, 3)
        self.assertEqual(
            folio.charges.filter(type=ChargeType.ROOM, status=PostingStatus.POSTED).count(),
            3,
        )
        self.assertEqual(str(folio_balance(folio)["balance"]), "300.00")

    def test_unpriced_room_posts_no_charge(self):
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges

        rtype2 = make_type(self.hotel, code="UNP")  # no base_rate
        room2 = make_room(self.hotel, rtype2, number="102")
        res2, line2 = make_reservation(self.hotel, rtype2, room=room2)
        stay = self._check_in(res2, line2, room2, make_guest(self.hotel, name="G2"))
        folio = stay.folios.get()
        self.assertEqual(ensure_due_room_charges(stay, as_of=D2, user=self.manager), 0)
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 0)

    def test_room_night_unique_under_concurrent_posting(self):
        """Owner concurrency guard — two interleaved posts of the SAME night can
        never both succeed: the partial unique index (folio, room_night) rejects
        the second, leaving exactly one posted charge."""
        from django.db import IntegrityError, transaction

        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import (
            ROOM_NIGHT_SOURCE, add_charge, ensure_stay_folio,
        )

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        folio = ensure_stay_folio(stay, user=self.manager)
        night = stay.planned_check_in_date
        add_charge(
            folio, charge_type=ChargeType.ROOM, description="night", quantity=1,
            unit_amount="100.00", source=ROOM_NIGHT_SOURCE, room_night=night,
            user=self.manager,
        )
        # A racer that read a stale "not posted" tries the same night.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                add_charge(
                    folio, charge_type=ChargeType.ROOM, description="dup", quantity=1,
                    unit_amount="100.00", source=ROOM_NIGHT_SOURCE, room_night=night,
                    user=self.manager,
                )
        self.assertEqual(
            folio.charges.filter(
                type=ChargeType.ROOM, room_night=night, status=PostingStatus.POSTED
            ).count(),
            1,
        )
        # A DIFFERENT charge type reusing a source is NOT constrained (room_night
        # stays NULL) — the guard is scoped to room nights only.
        add_charge(
            folio, charge_type=ChargeType.SERVICE, description="svc", quantity=1,
            unit_amount="10.00", user=self.manager,
        )
        add_charge(
            folio, charge_type=ChargeType.SERVICE, description="svc2", quantity=1,
            unit_amount="10.00", user=self.manager,
        )  # no collision

    def test_ensure_swallows_a_concurrent_night_conflict(self):
        """A night charge that appears BETWEEN ensure's read and its insert (a
        true race) is caught: ensure does not raise a 500 and does not duplicate."""
        from unittest.mock import patch

        from apps.finance import services as fin
        from apps.finance.models import ChargeType, PostingStatus

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        real_add = fin.add_charge
        injected = {"done": False}

        def racing_add(folio, **kw):
            if not injected["done"] and kw.get("room_night") is not None:
                injected["done"] = True
                real_add(folio, **kw)  # a competitor posts this night first
                return real_add(folio, **kw)  # our insert now collides
            return real_add(folio, **kw)

        with patch.object(fin, "add_charge", side_effect=racing_add):
            fin.ensure_due_room_charges(stay, as_of=D2, user=self.manager)  # must NOT raise

        folio = stay.folios.get()
        nights = folio.charges.filter(
            type=ChargeType.ROOM, status=PostingStatus.POSTED, room_night__isnull=False
        )
        # No duplicate: one posted charge per distinct night.
        self.assertEqual(nights.count(), nights.values("room_night").distinct().count())
        self.assertEqual(nights.count(), 2)


class FolioLifecycleGateTests(APITestCase):
    """§32/§38/§42 — awaiting-final-charges blocks check-out; a closed folio can
    be reopened with a reason."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "afc@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)  # unpriced -> folio balance stays 0
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(self.hotel, self.rtype, room=self.room)

    def _check_in(self):
        from apps.stays.services import CheckInService

        return CheckInService.execute(
            self.hotel, reservation=self.res, reservation_line=self.line,
            room=self.room, primary_guest=self.guest, companions=(), user=self.manager,
        )

    def test_awaiting_final_charges_blocks_checkout_until_cleared(self):
        from apps.common.exceptions import FolioAwaitingFinalCharges
        from apps.finance.services import set_folio_awaiting_final_charges
        from apps.stays.services import CheckOutService

        stay = self._check_in()
        folio = stay.folios.get()
        set_folio_awaiting_final_charges(
            folio, awaiting=True, note="restaurant", user=self.manager
        )
        with self.assertRaises(FolioAwaitingFinalCharges):
            CheckOutService.execute(stay, checkout_reason="early departure", user=self.manager)
        # Cleared -> departure proceeds (balance is 0 on the unpriced room).
        set_folio_awaiting_final_charges(folio, awaiting=False, user=self.manager)
        out = CheckOutService.execute(stay, checkout_reason="early departure", user=self.manager)
        self.assertEqual(out.status, StayStatus.CHECKED_OUT)

    def test_closed_folio_can_be_reopened_with_reason(self):
        from apps.finance.models import FolioStatus
        from apps.finance.services import reopen_folio
        from apps.stays.services import CheckOutService

        stay = self._check_in()
        folio = stay.folios.get()
        CheckOutService.execute(stay, checkout_reason="early departure", user=self.manager)  # closes the balanced folio
        folio.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.CLOSED)
        reopen_folio(folio, reason="late charge correction", user=self.manager)
        folio.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.OPEN)

    def test_reopen_requires_a_reason(self):
        from apps.common.exceptions import VoidReasonRequired
        from apps.finance.services import reopen_folio
        from apps.stays.services import CheckOutService

        stay = self._check_in()
        folio = stay.folios.get()
        CheckOutService.execute(stay, checkout_reason="early departure", user=self.manager)
        folio.refresh_from_db()
        with self.assertRaises(VoidReasonRequired):
            reopen_folio(folio, reason="  ", user=self.manager)


class ReverseCheckInTests(APITestCase):
    """§30 — reverse a mistaken check-in: void the room charges, keep the deposit,
    detach the folio to pre-arrival, cancel the stay, free the room."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "rev@x.com", kind=MembershipType.MANAGER)
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3, base_rate="100.00",
        )
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(self.hotel, self.rtype, room=self.room)

    def _check_in(self):
        from apps.stays.services import CheckInService

        return CheckInService.execute(
            self.hotel, reservation=self.res, reservation_line=self.line,
            room=self.room, primary_guest=self.guest, companions=(), user=self.manager,
        )

    def test_reverse_voids_room_charge_keeps_deposit_frees_room(self):
        from apps.finance.models import ChargeType, FolioStatus, PostingStatus
        from apps.finance.services import folio_balance, record_reservation_payment
        from apps.stays.services import ReverseCheckInService

        from apps.finance.services import ensure_due_room_charges

        # Deposit before arrival -> opens the reservation's pre-arrival folio.
        record_reservation_payment(
            self.res, amount="40.00", method="cash", user=self.manager
        )
        stay = self._check_in()  # reuses the deposit folio
        ensure_due_room_charges(stay, as_of=stay.planned_check_out_date, user=self.manager)
        folio = stay.folios.get()
        self.assertEqual(str(folio_balance(folio)["balance"]), "160.00")  # 200 - 40

        ReverseCheckInService.execute(stay, reason="wrong guest", user=self.manager)

        stay.refresh_from_db()
        self.assertEqual(stay.status, StayStatus.CANCELLED)
        folio.refresh_from_db()
        # Room charge voided; folio detached back to the reservation (pre-arrival).
        self.assertEqual(
            folio.charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).count(),
            0,
        )
        self.assertIsNone(folio.stay_id)
        self.assertEqual(folio.reservation_id, self.res.id)
        self.assertEqual(folio.status, FolioStatus.OPEN)
        # Deposit survives -> -40 credit on the pre-arrival folio.
        self.assertEqual(str(folio_balance(folio)["balance"]), "-40.00")
        # The room is free again (no in-house stay).
        self.assertFalse(
            Stay.objects.filter(room=self.room, status=StayStatus.IN_HOUSE).exists()
        )

    def test_cannot_reverse_a_non_in_house_stay(self):
        from apps.common.exceptions import InvalidStayChange
        from apps.stays.services import ReverseCheckInService

        stay = self._check_in()
        ReverseCheckInService.execute(stay, reason="x", user=self.manager)  # -> cancelled
        with self.assertRaises(InvalidStayChange):
            ReverseCheckInService.execute(stay, reason="again", user=self.manager)

    def test_reverse_refused_after_business_day_closed(self):
        """Owner correction — a check-in whose room charges are in a CLOSED
        business day cannot be reversed (no voiding of closed history); the stay
        and folio are left untouched."""
        from apps.common.exceptions import ReverseCheckInDayClosed
        from apps.finance.services import ensure_due_room_charges, folio_balance
        from apps.shifts.models import DailyClose, DailyCloseStatus
        from apps.stays.services import ReverseCheckInService

        stay = self._check_in()
        ensure_due_room_charges(stay, as_of=stay.planned_check_out_date, user=self.manager)
        folio = stay.folios.get()
        before = str(folio_balance(folio)["balance"])
        # The room charges were posted on business date D1; close that day.
        DailyClose.objects.create(
            hotel=self.hotel, close_number="DCREV01", business_date=D1,
            status=DailyCloseStatus.CLOSED, snapshot_json={}, totals_json={},
        )
        with self.assertRaises(ReverseCheckInDayClosed):
            ReverseCheckInService.execute(stay, reason="too late", user=self.manager)
        stay.refresh_from_db()
        self.assertEqual(stay.status, StayStatus.IN_HOUSE)  # unchanged
        folio.refresh_from_db()
        self.assertIsNotNone(folio.stay_id)  # not detached
        self.assertEqual(str(folio_balance(folio)["balance"]), before)  # unchanged

    def test_reverse_requires_a_reason(self):
        from apps.common.exceptions import ReverseCheckInReasonRequired
        from apps.stays.services import ReverseCheckInService

        stay = self._check_in()
        with self.assertRaises(ReverseCheckInReasonRequired):
            ReverseCheckInService.execute(stay, reason="  ", user=self.manager)

    def test_reverse_check_in_endpoint(self):
        stay = self._check_in()
        self.client.force_authenticate(self.manager)
        resp = self.client.post(
            reverse("stays:stay-reverse-check-in", args=[stay.id]),
            {"reason": "wrong guest"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200)
        stay.refresh_from_db()
        self.assertEqual(stay.status, StayStatus.CANCELLED)


class InsuranceTests(APITestCase):
    """§35 — refundable insurance held separately: record, refund, deduct (posts
    a settling payment to the folio), and the check-out gate until it is settled."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "ins@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)  # unpriced -> folio balance stays 0
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(self.hotel, self.rtype, room=self.room)

    def _check_in(self):
        from apps.stays.services import CheckInService

        return CheckInService.execute(
            self.hotel, reservation=self.res, reservation_line=self.line,
            room=self.room, primary_guest=self.guest, companions=(), user=self.manager,
        )

    def test_record_then_full_refund(self):
        from apps.finance.models import InsuranceStatus
        from apps.finance.services import record_insurance, refund_insurance

        stay = self._check_in()
        ins = record_insurance(
            hotel=self.hotel, amount="100.00", stay=stay,
            reservation=self.res, user=self.manager,
        )
        self.assertEqual(ins.status, InsuranceStatus.HELD)
        self.assertEqual(str(ins.held_amount), "100.00")
        refund_insurance(ins, reason="no damage", user=self.manager)  # full refund
        ins.refresh_from_db()
        self.assertEqual(ins.status, InsuranceStatus.REFUNDED)
        self.assertEqual(str(ins.held_amount), "0.00")

    def test_deduct_posts_a_settling_payment_to_the_folio(self):
        from apps.finance.models import ChargeType, InsuranceStatus
        from apps.finance.services import (
            add_charge, deduct_insurance, folio_balance, record_insurance,
        )

        stay = self._check_in()
        folio = stay.folios.get()
        add_charge(
            folio, charge_type=ChargeType.OTHER, description="damage",
            quantity=1, unit_amount="30.00", user=self.manager,
        )
        self.assertEqual(str(folio_balance(folio)["balance"]), "30.00")
        ins = record_insurance(hotel=self.hotel, amount="100.00", stay=stay, user=self.manager)
        deduct_insurance(ins, amount="30.00", reason="damage cover", user=self.manager)
        # The deduction posted a payment that settled the folio.
        self.assertEqual(str(folio_balance(folio)["balance"]), "0.00")
        ins.refresh_from_db()
        self.assertEqual(str(ins.deducted_amount), "30.00")
        self.assertEqual(str(ins.held_amount), "70.00")
        self.assertEqual(ins.status, InsuranceStatus.PARTIALLY_DEDUCTED)

    def test_checkout_blocked_until_insurance_settled(self):
        from apps.common.exceptions import InsuranceNotSettled
        from apps.finance.services import record_insurance, refund_insurance
        from apps.stays.services import CheckOutService

        stay = self._check_in()
        ins = record_insurance(hotel=self.hotel, amount="50.00", stay=stay, user=self.manager)
        with self.assertRaises(InsuranceNotSettled):
            CheckOutService.execute(stay, checkout_reason="early", user=self.manager)
        refund_insurance(ins, reason="returned", user=self.manager)  # settle
        out = CheckOutService.execute(stay, checkout_reason="early", user=self.manager)
        self.assertEqual(out.status, StayStatus.CHECKED_OUT)

    def test_deduct_capped_at_outstanding_balance(self):
        """§35 review-fix — deduction cannot exceed the folio's outstanding
        balance (else it would create a credit that could be paid back)."""
        from apps.common.exceptions import InvalidFinanceOperation
        from apps.finance.services import deduct_insurance, record_insurance

        stay = self._check_in()  # unpriced -> folio balance 0
        ins = record_insurance(hotel=self.hotel, amount="100.00", stay=stay, user=self.manager)
        with self.assertRaises(InvalidFinanceOperation):
            deduct_insurance(ins, amount="30.00", reason="damage", user=self.manager)

    def test_record_rejects_unaccepted_currency(self):
        """§35 review-fix — insurance currency is validated against the hotel's
        accepted currencies."""
        from apps.common.exceptions import InvalidFinanceOperation
        from apps.finance.services import record_insurance

        stay = self._check_in()
        with self.assertRaises(InvalidFinanceOperation):
            record_insurance(
                hotel=self.hotel, amount="100.00", currency="XXX",
                stay=stay, user=self.manager,
            )

    def test_checkout_blocked_by_reservation_linked_insurance(self):
        """§35 review-fix — insurance taken at booking (stay not yet linked)
        still blocks the stay's departure."""
        from apps.common.exceptions import InsuranceNotSettled
        from apps.finance.services import record_insurance
        from apps.stays.services import CheckOutService

        stay = self._check_in()
        record_insurance(
            hotel=self.hotel, amount="50.00", reservation=self.res,
            stay=None, user=self.manager,
        )
        with self.assertRaises(InsuranceNotSettled):
            CheckOutService.execute(stay, checkout_reason="early", user=self.manager)

    def test_record_endpoint_missing_amount_is_400(self):
        """§35 review-fix — a malformed/missing amount is a 400, not a 500."""
        self.client.force_authenticate(self.manager)
        stay = self._check_in()
        r = self.client.post(
            reverse("finance:insurance-list-create"),
            {"stay": stay.id}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)

    def test_insurance_endpoints(self):
        stay = self._check_in()
        self.client.force_authenticate(self.manager)
        r = self.client.post(
            reverse("finance:insurance-list-create"),
            {"amount": "100.00", "stay": stay.id}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["status"], "held")
        iid = r.json()["id"]
        lst = self.client.get(
            reverse("finance:insurance-list-create") + f"?stay={stay.id}",
            **HDR(self.hotel),
        )
        self.assertEqual(len(lst.json()), 1)
        rf = self.client.post(
            reverse("finance:insurance-refund", args=[iid]),
            {"reason": "returned"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(rf.status_code, 200)
        self.assertEqual(rf.json()["status"], "refunded")


class SettlementAndRefundTests(APITestCase):
    """§34/§37 — settle a stay folio (multi-currency aware) and refund a credit."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "set@x.com", kind=MembershipType.MANAGER)
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3, base_rate="100.00",
        )
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(self.hotel, self.rtype, room=self.room)

    def _check_in(self):
        from apps.finance.services import ensure_due_room_charges
        from apps.stays.services import CheckInService

        stay = CheckInService.execute(
            self.hotel, reservation=self.res, reservation_line=self.line,
            room=self.room, primary_guest=self.guest, companions=(), user=self.manager,
        )
        # Post the two planned nights so the folio holds a 200 room charge.
        ensure_due_room_charges(stay, as_of=stay.planned_check_out_date, user=self.manager)
        return stay

    def test_settle_folio_to_zero(self):
        from apps.finance.services import folio_balance, record_folio_settlement

        stay = self._check_in()
        folio = stay.folios.get()
        self.assertEqual(str(folio_balance(folio)["balance"]), "200.00")  # room charge
        record_folio_settlement(folio, method="cash", amount="200.00", user=self.manager)
        self.assertEqual(str(folio_balance(folio)["balance"]), "0.00")

    def test_refund_a_credit_balance(self):
        from apps.finance.services import (
            folio_balance, record_folio_settlement, refund_folio_credit,
        )

        stay = self._check_in()
        folio = stay.folios.get()
        record_folio_settlement(folio, method="cash", amount="250.00", user=self.manager)
        self.assertEqual(str(folio_balance(folio)["balance"]), "-50.00")  # overpaid
        refund_folio_credit(folio, reason="overpayment", user=self.manager)
        self.assertEqual(str(folio_balance(folio)["balance"]), "0.00")

    def test_refund_requires_a_credit(self):
        from apps.common.exceptions import InvalidFinanceOperation
        from apps.finance.services import refund_folio_credit

        stay = self._check_in()
        folio = stay.folios.get()  # 200 owed, no credit
        with self.assertRaises(InvalidFinanceOperation):
            refund_folio_credit(folio, reason="x", user=self.manager)


class StaysOverviewTests(APITestCase):
    """§6/§50 — the six-card overview counts come from the backend in one call."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "ov@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)
        self.rooms = [
            make_room(self.hotel, self.rtype, number=str(101 + i)) for i in range(3)
        ]

    def _overview(self):
        self.client.force_authenticate(self.manager)
        return self.client.get(
            reverse("stays:stay-overview"), **HDR(self.hotel)
        ).json()

    def test_overview_counts(self):
        # An arriving-today reservation (confirmed, today, no stay yet).
        make_reservation(self.hotel, self.rtype, room=self.rooms[0])
        # A current resident (in-house stay checked in today).
        from apps.stays.services import CheckInService

        r2, l2 = make_reservation(self.hotel, self.rtype, room=self.rooms[1])
        CheckInService.execute(
            self.hotel, reservation=r2, reservation_line=l2, room=self.rooms[1],
            primary_guest=make_guest(self.hotel, name="R2"), companions=(),
            user=self.manager,
        )

        data = self._overview()
        self.assertEqual(data["arriving_today"], 1)
        self.assertGreaterEqual(data["awaiting_check_in"], 1)
        self.assertEqual(data["current_residents"], 1)
        self.assertEqual(data["checked_in_today"], 1)
        self.assertEqual(data["departing_today"], 0)
        self.assertIn("business_date", data)
        self.assertIn("needs_attention", data)

    def test_overview_requires_stays_view(self):
        viewer = add_member(self.hotel, "noview-ov@x.com", perms=[])
        self.client.force_authenticate(viewer)
        resp = self.client.get(reverse("stays:stay-overview"), **HDR(self.hotel))
        self.assertEqual(resp.status_code, 403)


class FolioCycleEndpointsTests(APITestCase):
    """§32/§34/§37/§42 — folio settle / awaiting-charges / reopen / refund endpoints."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "fe@x.com", kind=MembershipType.MANAGER)
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3, base_rate="100.00",
        )
        self.room = make_room(self.hotel, self.rtype)
        self.guest = make_guest(self.hotel)
        self.res, self.line = make_reservation(self.hotel, self.rtype, room=self.room)
        self.client.force_authenticate(self.manager)

    def _folio(self):
        from apps.finance.services import ensure_due_room_charges
        from apps.stays.services import CheckInService

        stay = CheckInService.execute(
            self.hotel, reservation=self.res, reservation_line=self.line,
            room=self.room, primary_guest=self.guest, companions=(), user=self.manager,
        )
        # Post the two planned nights (as if the stay's nights are all consumed)
        # so the folio holds a 200 room charge for the lifecycle tests.
        ensure_due_room_charges(stay, as_of=stay.planned_check_out_date, user=self.manager)
        return stay.folios.get()

    def _post(self, name, folio, body):
        return self.client.post(
            reverse(name, args=[folio.id]), body, format="json", **HDR(self.hotel)
        )

    def test_settle_endpoint(self):
        from apps.finance.services import folio_balance

        folio = self._folio()
        resp = self._post("finance:folio-settle", folio, {"method": "cash", "amount": "200.00"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(folio_balance(folio)["balance"]), "0.00")

    def test_awaiting_then_reopen_endpoints(self):
        from apps.finance.models import FolioStatus
        from apps.finance.services import close_folio

        folio = self._folio()
        self.assertEqual(
            self._post("finance:folio-awaiting-charges", folio,
                       {"awaiting": True, "note": "restaurant"}).status_code, 200)
        folio.refresh_from_db()
        self.assertTrue(folio.awaiting_final_charges)
        self._post("finance:folio-settle", folio, {"method": "cash", "amount": "200.00"})
        self._post("finance:folio-awaiting-charges", folio, {"awaiting": False})
        folio.refresh_from_db()
        close_folio(folio, user=self.manager)
        folio.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.CLOSED)
        self.assertEqual(
            self._post("finance:folio-reopen", folio, {"reason": "correction"}).status_code, 200)
        folio.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.OPEN)

    def test_refund_endpoint(self):
        from apps.finance.services import folio_balance, record_folio_settlement

        folio = self._folio()
        record_folio_settlement(folio, method="cash", amount="250.00", user=self.manager)  # overpay
        resp = self._post("finance:folio-refund", folio, {"reason": "overpayment"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(folio_balance(folio)["balance"]), "0.00")

    def test_close_folio_blocked_while_awaiting_final_charges(self):
        """§32/§38 review-fix — the direct close path also honours the awaiting
        flag (not only the stay checkout gate)."""
        from apps.common.exceptions import FolioAwaitingFinalCharges
        from apps.finance.services import (
            close_folio, record_folio_settlement, set_folio_awaiting_final_charges,
        )

        folio = self._folio()
        record_folio_settlement(folio, method="cash", amount="200.00", user=self.manager)
        set_folio_awaiting_final_charges(folio, awaiting=True, note="restaurant", user=self.manager)
        folio.refresh_from_db()
        with self.assertRaises(FolioAwaitingFinalCharges):
            close_folio(folio, user=self.manager)

    def test_current_residents_folio_summary(self):
        """§12 — the resident list carries a derived folio finance block."""
        from apps.finance.services import (
            ensure_due_room_charges, record_folio_settlement,
        )
        from apps.stays.services import CheckInService

        stay = CheckInService.execute(
            self.hotel, reservation=self.res, reservation_line=self.line,
            room=self.room, primary_guest=self.guest, companions=(), user=self.manager,
        )
        ensure_due_room_charges(stay, as_of=stay.planned_check_out_date, user=self.manager)
        r = self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        self.assertEqual(r.status_code, 200)
        row = next(x for x in r.data["results"] if x["id"] == stay.id)
        self.assertEqual(row["document_count"], 0)  # §13 — no docs on this booking
        summary = row["folio_summary"]
        self.assertIsNotNone(summary)
        self.assertEqual(summary["balance"], "200.00")  # 2 nights * 100, unpaid
        self.assertEqual(summary["payment_status"], "unpaid")

        record_folio_settlement(stay.folios.get(), method="cash", amount="200.00", user=self.manager)
        r = self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        row = next(x for x in r.data["results"] if x["id"] == stay.id)
        self.assertEqual(row["folio_summary"]["payment_status"], "paid")

    def _check_in_past_arrival(self, number):
        """A stay whose two nights are already consumed by the business date."""
        from apps.stays.services import CheckInService

        room = make_room(self.hotel, self.rtype, number=number)
        res, line = make_reservation(
            self.hotel, self.rtype, room=room,
            ci=D1 - timedelta(days=2), co=D1,  # nights D1-2, D1-1 (both due at D1)
        )
        return CheckInService.execute(
            self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name=f"G{number}"),
            companions=(), user=self.manager,
        )

    def test_ensure_room_charges_endpoint_posts_due_nights(self):
        """Owner correction — check-in posts the already-due nights, and the
        ensure endpoint is an idempotent safety net that returns the summary."""
        stay = self._check_in_past_arrival("909")
        # Both past nights were due at check-in -> already posted (200).
        r = self.client.post(
            reverse("stays:stay-ensure-room-charges", args=[stay.id]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["balance"], "200.00")
        # Idempotent: calling again does not double-post.
        r2 = self.client.post(
            reverse("stays:stay-ensure-room-charges", args=[stay.id]), **HDR(self.hotel)
        )
        self.assertEqual(r2.data["balance"], "200.00")

    def test_folio_summary_has_no_n_plus_one(self):
        """§12 review-fix — adding residents does not add per-card folio queries."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._check_in_past_arrival("701")
        with CaptureQueriesContext(connection) as q1:
            self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        self._check_in_past_arrival("702")
        with CaptureQueriesContext(connection) as q2:
            self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        # Prefetch + a once-per-response permission check => constant query count.
        self.assertEqual(len(q1.captured_queries), len(q2.captured_queries))
