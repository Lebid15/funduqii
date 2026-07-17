"""Tests for stays / front desk (Phase 7 + final closure): access/permissions,
check-in rules (quantity cap, arrival-date guard), check-out (folio gate,
early departure), extend/shorten/room-move, occupancy derivation,
arrivals/departures on the hotel business date, and regression."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest import mock

from django.test import TransactionTestCase
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
    # Mirror production ``create_reservation``: freeze the AGREED nightly rate +
    # the hotel default currency on the line at booking time (NULL when unpriced).
    base = rtype.base_rate
    agreed = Decimal(base).quantize(Decimal("0.01")) if base is not None else None
    if agreed is not None and agreed <= 0:
        agreed = None
    currency = (
        getattr(getattr(hotel, "settings", None), "default_currency", "") or ""
    ) or "USD"
    line = ReservationRoomLine.objects.create(
        hotel=hotel, reservation=res, room_type=rtype, room=room, quantity=qty,
        agreed_nightly_rate=agreed, agreed_rate_currency=currency,
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

    def test_extend_rejects_non_positive_override_rate(self):
        """FIX 3 — a zero/negative override rate is rejected at the API boundary
        (serializer min_value), never deferred to billing."""
        new_end = str(D1 + timedelta(days=5))
        for bad in ("-10.00", "0.00"):
            r = self._post(
                "stay-extend",
                {"new_check_out_date": new_end, "nightly_rate": bad, "reason": "x"},
            )
            self.assertEqual(r.status_code, 400, bad)

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

    def test_unpriced_room_blocks_posting(self):
        # STAYS rate-integrity remediation: a NULL-rate (unpriced) booking period is
        # the agreed price MISSING, NOT a free night — a due night RAISES and posts
        # nothing (so checkout / daily close surface it), never settles zero.
        from apps.common.exceptions import MissingAgreedNightlyRate
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges

        rtype2 = make_type(self.hotel, code="UNP")  # no base_rate
        room2 = make_room(self.hotel, rtype2, number="102")
        res2, line2 = make_reservation(self.hotel, rtype2, room=room2)
        stay = self._check_in(res2, line2, room2, make_guest(self.hotel, name="G2"))
        folio = stay.folios.get()
        with self.assertRaises(MissingAgreedNightlyRate):
            ensure_due_room_charges(stay, as_of=D2, user=self.manager)
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

    def test_late_arrival_excludes_pre_arrival_nights(self):
        """FIX-1 — a LATE arrival is billed only from the actual arrival date on:
        nights before the guest physically checked in (unoccupied) are never
        posted, even though they fall inside the planned window."""
        from datetime import datetime

        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        # Planned check-in is D1; the guest actually arrives one day LATER (D1+1).
        # Build an aware datetime whose hotel-local date (UTC here) is D1+1.
        arrival = datetime.combine(
            D1 + timedelta(days=1),
            datetime.min.time().replace(hour=12),
            tzinfo=dt_timezone.utc,
        )
        stay.actual_check_in_at = arrival
        stay.save(update_fields=["actual_check_in_at"])

        posted = ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        # Only the single night from the actual arrival (D1+1) is billed.
        self.assertEqual(posted, 1)
        folio = stay.folios.get()
        nights = set(
            folio.charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).values_list("room_night", flat=True)
        )
        self.assertEqual(nights, {D1 + timedelta(days=1)})
        self.assertNotIn(D1, nights)  # the pre-arrival night is NOT billed

    def test_legacy_aggregated_charge_prevents_double_billing(self):
        """FIX-2 — if the folio already holds a legacy aggregated ROOM charge
        (whole stay on one line, no room_night), per-night posting bails out with
        0 so the room is never double-billed."""
        from apps.finance.models import ChargeType
        from apps.finance.services import add_charge, ensure_due_room_charges

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        folio = stay.folios.get()
        # Legacy-style aggregated room charge: the whole stay on ONE line with no
        # room_night (room_night stays NULL).
        add_charge(
            folio,
            charge_type=ChargeType.ROOM,
            description="Room (legacy aggregate)",
            quantity=2,
            unit_amount="100.00",
            source="stay_room",
            user=self.manager,
        )
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 1)
        posted = ensure_due_room_charges(
            stay, as_of=stay.planned_check_out_date, user=self.manager
        )
        self.assertEqual(posted, 0)  # nothing posted — the legacy line already bills
        # No per-night (room_night set) charge was added.
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 1)
        self.assertEqual(
            folio.charges.filter(
                type=ChargeType.ROOM, room_night__isnull=False
            ).count(),
            0,
        )

    def test_safety_net_posts_via_real_business_date(self):
        """FIX-5 — the safety net posts consumed nights via the REAL business date
        (NO as_of): a guest who genuinely arrived 2 days ago owes both nights that
        the hotel clock has already passed, proving the real-business-date path."""
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges, folio_balance

        room2 = make_room(self.hotel, self.rtype, number="777")
        res2, line2 = make_reservation(
            self.hotel, self.rtype, room=room2,
            ci=D1 - timedelta(days=2), co=D1,  # nights D1-2, D1-1
        )
        guest2 = make_guest(self.hotel, name="Past Guest")
        stay = self._check_in(res2, line2, room2, guest2)
        # The guest actually arrived 2 days ago: FIX-1's window opens at D1-2, so
        # both nights are genuinely consumed by today's business date.
        stay.actual_check_in_at = timezone.now() - timedelta(days=2)
        stay.save(update_fields=["actual_check_in_at"])

        # No as_of: ensure must use the REAL business date (today) to decide which
        # nights are due — proving the safety-net path without an as_of override.
        posted = ensure_due_room_charges(stay, user=self.manager)
        self.assertEqual(posted, 2)
        folio = stay.folios.get()
        nights = set(
            folio.charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).values_list("room_night", flat=True)
        )
        self.assertEqual(
            nights, {D1 - timedelta(days=2), D1 - timedelta(days=1)}
        )
        self.assertEqual(str(folio_balance(folio)["balance"]), "200.00")

    def test_invalid_hotel_timezone_falls_back_safely(self):
        """FIX-1 robustness — a hotel carrying an INVALID timezone string (the
        field has no validators) must NOT break room-charge posting: the arrival
        derivation falls back to the planned check-in instead of raising
        ZoneInfoNotFoundError, so check-in/-out never fail for that hotel."""
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges
        from apps.hotels.models import HotelSettings

        stay = self._check_in(self.res, self.line, self.room, self.guest)
        # Poison the hotel timezone AFTER a clean check-in.
        HotelSettings.objects.update_or_create(
            hotel=self.hotel, defaults={"timezone": "Not/AZone"}
        )
        # Must NOT raise: arrival_date falls back to planned check-in (D1), so both
        # nights (D1, D1+1) are due as of D2.
        posted = ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(posted, 2)
        folio = stay.folios.get()
        nights = set(
            folio.charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).values_list("room_night", flat=True)
        )
        self.assertEqual(nights, {D1, D1 + timedelta(days=1)})


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
        """A stay whose two nights are genuinely consumed: the guest actually
        ARRIVED two days ago (``actual_check_in_at`` back-dated), so under FIX-1
        the billing window starts at D1-2 and nights D1-2, D1-1 are real consumed
        nights before today's business date."""
        from apps.stays.services import CheckInService

        room = make_room(self.hotel, self.rtype, number=number)
        res, line = make_reservation(
            self.hotel, self.rtype, room=room,
            ci=D1 - timedelta(days=2), co=D1,  # nights D1-2, D1-1 (both due at D1)
        )
        stay = CheckInService.execute(
            self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name=f"G{number}"),
            companions=(), user=self.manager,
        )
        # Realistic: the guest physically arrived 2 days ago, so FIX-1's window
        # opens at D1-2 (not today) and both nights are genuinely consumed.
        stay.actual_check_in_at = timezone.now() - timedelta(days=2)
        stay.save(update_fields=["actual_check_in_at"])
        return stay

    def test_ensure_room_charges_endpoint_posts_due_nights(self):
        """Owner correction — the two genuinely-consumed nights (arrival 2 days
        ago) are posted via the real business date, and the ensure endpoint is an
        idempotent safety net that returns the summary."""
        stay = self._check_in_past_arrival("909")
        # Both consumed nights are due at today's business date -> posted (200).
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


# --------------------------------------------------------------------------- #
# STAYS FINAL HARDENING (PR #43) — helpers                                      #
# --------------------------------------------------------------------------- #


def _priced_type(hotel, *, code="STD", rate="100.00"):
    """A room type WITH a base rate (so nights are billable)."""
    return RoomType.objects.create(
        hotel=hotel, name="Standard", code=code,
        base_capacity=2, max_capacity=3, base_rate=rate,
    )


def _check_in(hotel, manager, rtype, *, number, ci=D1, co=D2, guest_name="G"):
    """Check a fresh reservation into a fresh room and return the Stay."""
    from apps.stays.services import CheckInService

    room = make_room(hotel, rtype, number=number)
    res, line = make_reservation(hotel, rtype, room=room, ci=ci, co=co)
    return CheckInService.execute(
        hotel, reservation=res, reservation_line=line, room=room,
        primary_guest=make_guest(hotel, name=guest_name),
        companions=(), user=manager,
    )


def _set_arrival(stay, arrival_date):
    """Pin the actual arrival to NOON UTC on ``arrival_date`` so FIX-1's billing
    window opens deterministically regardless of the server timezone (the hotel
    tz defaults to UTC in these tests)."""
    stay.actual_check_in_at = datetime.combine(
        arrival_date, datetime.min.time().replace(hour=12), tzinfo=dt_timezone.utc
    )
    stay.save(update_fields=["actual_check_in_at"])


class StayRatePeriodBillingTests(APITestCase):
    """STAYS rate-integrity round — the AGREED nightly rate is captured at BOOKING
    on the reservation line and materialised into a ``StayRatePeriod`` at check-in.
    Every night bills from the period that covers it; a later ``RoomType.base_rate``
    change never alters the bill, and there is NO live-catalog fallback."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "snap@x.com", kind=MembershipType.MANAGER)

    def test_agreed_rate_and_currency_captured_at_booking(self):
        """create_reservation freezes the agreed rate + hotel currency on the line;
        a later catalog change never rewrites the snapshot."""
        from apps.reservations.services import create_reservation

        rtype = _priced_type(self.hotel, code="BKG", rate="100.00")
        make_room(self.hotel, rtype, number="401")  # availability for the book
        res = create_reservation(
            self.hotel,
            lines=[{"room_type": rtype, "quantity": 1}],
            status=ReservationStatus.CONFIRMED,
            user=self.manager,
            check_in_date=D1,
            check_out_date=D2,
            primary_guest_name="Booker",
        )
        line = res.lines.get()
        self.assertEqual(line.agreed_nightly_rate, Decimal("100.00"))
        self.assertEqual(line.agreed_rate_currency, "USD")  # hotel default captured
        # Catalog change AFTER booking must NOT alter the frozen snapshot.
        RoomType.objects.filter(pk=rtype.pk).update(base_rate=Decimal("150.00"))
        line.refresh_from_db()
        self.assertEqual(line.agreed_nightly_rate, Decimal("100.00"))

    def test_original_period_created_at_check_in(self):
        rtype = _priced_type(self.hotel, code="CAP", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="300")
        period = stay.rate_periods.get()
        self.assertEqual(period.nightly_rate, Decimal("100.00"))
        self.assertEqual(period.currency, "USD")
        self.assertEqual(period.source, "booking")
        self.assertEqual(period.start_date, stay.planned_check_in_date)
        self.assertEqual(period.end_date, stay.planned_check_out_date)

    def test_booking_price_beats_change_between_booking_and_check_in(self):
        """The agreed price is frozen at BOOKING: a catalog change between booking
        and check-in bills the AGREED price, never the changed one."""
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges, folio_balance
        from apps.stays.services import CheckInService

        rtype = _priced_type(self.hotel, code="SNP", rate="100.00")
        room = make_room(self.hotel, rtype, number="301")
        res, line = make_reservation(self.hotel, rtype, room=room, ci=D1, co=D2)
        # Price changes AFTER the booking but BEFORE the guest arrives.
        RoomType.objects.filter(pk=rtype.pk).update(base_rate=Decimal("150.00"))
        stay = CheckInService.execute(
            self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="G"), companions=(),
            user=self.manager,
        )
        posted = ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(posted, 2)
        folio = stay.folios.get()
        for c in folio.charges.filter(type=ChargeType.ROOM):
            self.assertEqual(c.total_amount, Decimal("100.00"))  # AGREED, not 150
        self.assertEqual(str(folio_balance(folio)["balance"]), "200.00")

    def test_no_live_fallback_after_check_in(self):
        """A catalog change AFTER check-in never changes the bill — no fallback."""
        from apps.finance.services import ensure_due_room_charges, folio_balance

        rtype = _priced_type(self.hotel, code="NLF", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="302")
        RoomType.objects.filter(pk=rtype.pk).update(base_rate=Decimal("250.00"))
        posted = ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(posted, 2)
        folio = stay.folios.get()
        self.assertEqual(str(folio_balance(folio)["balance"]), "200.00")  # 2*100

    def test_posted_nights_immutable_across_rate_change(self):
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges

        rtype = _priced_type(self.hotel, code="UNC", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="303")
        ensure_due_room_charges(stay, as_of=D1 + timedelta(days=1), user=self.manager)
        folio = stay.folios.get()
        first = folio.charges.get(type=ChargeType.ROOM, room_night=D1)
        self.assertEqual(first.total_amount, Decimal("100.00"))
        RoomType.objects.filter(pk=rtype.pk).update(base_rate=Decimal("250.00"))
        ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        first.refresh_from_db()
        self.assertEqual(first.total_amount, Decimal("100.00"))  # unchanged
        nights = folio.charges.filter(type=ChargeType.ROOM)
        self.assertEqual(nights.count(), 2)
        for c in nights:
            self.assertEqual(c.total_amount, Decimal("100.00"))  # both from period

    def test_late_arrival_bills_from_period(self):
        from apps.finance.services import ensure_due_room_charges, folio_balance

        rtype = _priced_type(self.hotel, code="LAT", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="304")
        _set_arrival(stay, D1 + timedelta(days=1))  # only the 2nd night consumed
        RoomType.objects.filter(pk=rtype.pk).update(base_rate=Decimal("250.00"))
        posted = ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(posted, 1)
        folio = stay.folios.get()
        self.assertEqual(str(folio_balance(folio)["balance"]), "100.00")  # period

    def test_unpriced_null_period_blocks_posting(self):
        """A booking-time UNPRICED line (agreed rate NULL) creates a NULL-rate
        booking period: NULL is the agreed price MISSING, NOT a free night, so a due
        night RAISES MissingAgreedNightlyRate and posts nothing (never zero)."""
        from apps.common.exceptions import MissingAgreedNightlyRate
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges

        rtype = make_type(self.hotel, code="UNP")  # no base_rate
        stay = _check_in(self.hotel, self.manager, rtype, number="305")
        period = stay.rate_periods.get()
        self.assertIsNone(period.nightly_rate)  # explicitly unpriced
        self.assertEqual(period.source, "booking")
        with self.assertRaises(MissingAgreedNightlyRate) as ctx:
            ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(ctx.exception.default_code, "missing_agreed_nightly_rate")
        self.assertEqual(
            stay.folios.get().charges.filter(type=ChargeType.ROOM).count(), 0
        )

    def test_missing_rate_raises_and_posts_nothing(self):
        """A DUE night with NO covering period is a data gap: it raises
        MissingAgreedNightlyRate (machine code, 4xx not 500) and posts nothing —
        so checkout / daily close surface it rather than settling short."""
        from apps.common.exceptions import MissingAgreedNightlyRate
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges, ensure_stay_folio

        rtype = _priced_type(self.hotel, code="MIS", rate="100.00")
        room = make_room(self.hotel, rtype, number="306")
        res, line = make_reservation(self.hotel, rtype, room=room, ci=D1, co=D2)
        # A stay with a DUE night but NO rate period (created directly, no check-in).
        stay = Stay.objects.create(
            hotel=self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="Gap"),
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1, planned_check_out_date=D2,
            actual_check_in_at=timezone.now(),
        )
        folio = ensure_stay_folio(stay, user=self.manager)
        with self.assertRaises(MissingAgreedNightlyRate) as ctx:
            ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(ctx.exception.default_code, "missing_agreed_nightly_rate")
        self.assertEqual(ctx.exception.status_code, 409)  # a 4xx, never a 500
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 0)

    def test_billing_is_tenant_isolated(self):
        from apps.finance.services import ensure_due_room_charges, folio_balance

        hotel_b = make_hotel(slug="snap-b")
        mgr_b = add_member(hotel_b, "snapb@x.com", kind=MembershipType.MANAGER)
        rtype_a = _priced_type(self.hotel, code="TA", rate="100.00")
        rtype_b = _priced_type(hotel_b, code="TB", rate="200.00")
        stay_a = _check_in(self.hotel, self.manager, rtype_a, number="307")
        stay_b = _check_in(hotel_b, mgr_b, rtype_b, number="307")
        # Both catalogs change after admission — neither stay is affected.
        RoomType.objects.filter(pk=rtype_a.pk).update(base_rate=Decimal("999.00"))
        RoomType.objects.filter(pk=rtype_b.pk).update(base_rate=Decimal("999.00"))
        ensure_due_room_charges(stay_a, as_of=D2, user=self.manager)
        ensure_due_room_charges(stay_b, as_of=D2, user=mgr_b)
        folio_a = stay_a.folios.get()
        folio_b = stay_b.folios.get()
        self.assertEqual(str(folio_balance(folio_a)["balance"]), "200.00")  # 2*100
        self.assertEqual(str(folio_balance(folio_b)["balance"]), "400.00")  # 2*200
        self.assertEqual(folio_a.hotel_id, self.hotel.id)
        self.assertEqual(folio_b.hotel_id, hotel_b.id)
        # No cross-tenant charge leakage.
        self.assertFalse(folio_a.charges.exclude(hotel=self.hotel).exists())
        self.assertFalse(folio_b.charges.exclude(hotel=hotel_b).exists())

    def test_rate_currency_mismatch_refused(self):
        """FIX 2 — a rate period whose currency differs from the folio currency is
        refused (no silent wrong-currency posting); the room charge posts nothing."""
        from apps.common.exceptions import InvalidFinanceOperation
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_due_room_charges, ensure_stay_folio
        from apps.stays.models import StayRatePeriod

        rtype = _priced_type(self.hotel, code="CUR", rate="100.00")
        room = make_room(self.hotel, rtype, number="340")
        res, line = make_reservation(self.hotel, rtype, room=room, ci=D1, co=D2)
        stay = Stay.objects.create(
            hotel=self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="Cur"),
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1, planned_check_out_date=D2,
            actual_check_in_at=timezone.now(),
        )
        folio = ensure_stay_folio(stay, user=self.manager)  # folio currency USD
        StayRatePeriod.objects.create(
            hotel=self.hotel, stay=stay, start_date=D1, end_date=D2,
            nightly_rate=Decimal("100.00"), currency="EUR", source="booking",
        )
        with self.assertRaises(InvalidFinanceOperation) as ctx:
            ensure_due_room_charges(stay, as_of=D2, user=self.manager)
        self.assertEqual(ctx.exception.detail["reason"], "rate_currency_mismatch")
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 0)


class StayExtensionPricingTests(APITestCase):
    """STAYS rate-integrity round — an extension adds a NEW rate period. Default
    inherits the latest period rate (no special permission); an explicit rate that
    differs is an audited OVERRIDE gated on ``stays.rate_override`` + a reason."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "ext@x.com", kind=MembershipType.MANAGER)

    def test_default_extension_inherits_latest_rate(self):
        from apps.finance.services import ensure_due_room_charges, folio_balance
        from apps.stays.services import ExtendStayService

        rtype = _priced_type(self.hotel, code="EX1", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="320")  # D1..D2
        ExtendStayService.execute(
            stay, new_check_out_date=D2 + timedelta(days=1), user=self.manager
        )
        stay.refresh_from_db()
        periods = list(stay.rate_periods.order_by("start_date"))
        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[1].source, "extension")
        self.assertEqual(periods[1].nightly_rate, Decimal("100.00"))
        posted = ensure_due_room_charges(
            stay, as_of=D2 + timedelta(days=1), user=self.manager
        )
        self.assertEqual(posted, 3)
        self.assertEqual(
            str(folio_balance(stay.folios.get())["balance"]), "300.00"  # 3*100
        )

    def test_override_prices_added_nights_and_audits(self):
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges, folio_balance
        from apps.stays.services import ExtendStayService

        rtype = _priced_type(self.hotel, code="EX2", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="321")  # D1..D2
        ExtendStayService.execute(
            stay,
            new_check_out_date=D2 + timedelta(days=1),
            nightly_rate=Decimal("120.00"),
            reason="peak season",
            user=self.manager,
        )
        stay.refresh_from_db()
        added = stay.rate_periods.get(start_date=D2)
        self.assertEqual(added.source, "override")
        self.assertEqual(added.nightly_rate, Decimal("120.00"))
        self.assertEqual(added.approved_by, self.manager)
        self.assertIsNotNone(added.approved_at)
        self.assertEqual(added.override_reason, "peak season")
        # Original nights bill 100, the added night bills 120.
        posted = ensure_due_room_charges(
            stay, as_of=D2 + timedelta(days=1), user=self.manager
        )
        self.assertEqual(posted, 3)
        folio = stay.folios.get()
        self.assertEqual(str(folio_balance(folio)["balance"]), "320.00")  # 100+100+120
        # A re-run neither changes nor duplicates any charge.
        again = ensure_due_room_charges(
            stay, as_of=D2 + timedelta(days=1), user=self.manager
        )
        self.assertEqual(again, 0)
        self.assertEqual(
            folio.charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).count(),
            3,
        )

    def test_override_requires_permission(self):
        from apps.common.exceptions import PermissionDenied
        from apps.stays.services import ExtendStayService

        rtype = _priced_type(self.hotel, code="EX3", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="322")
        # A user who may extend but does NOT hold stays.rate_override.
        clerk = add_member(self.hotel, "clerk@x.com", perms=["stays.extend"])
        with self.assertRaises(PermissionDenied):
            ExtendStayService.execute(
                stay,
                new_check_out_date=D2 + timedelta(days=1),
                nightly_rate=Decimal("120.00"),
                reason="peak season",
                user=clerk,
            )

    def test_finance_charge_create_alone_cannot_override(self):
        """FIX B — the OVERRIDE gate is ``stays.rate_override`` (NOT
        ``finance.charge_create``): holding finance.charge_create WITHOUT
        rate_override is rejected for an extension override."""
        from apps.common.exceptions import PermissionDenied
        from apps.stays.services import ExtendStayService

        rtype = _priced_type(self.hotel, code="EX6", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="325")
        actor = add_member(
            self.hotel, "fc-only@x.com",
            perms=["stays.extend", "finance.charge_create"],  # NOT rate_override
        )
        with self.assertRaises(PermissionDenied):
            ExtendStayService.execute(
                stay,
                new_check_out_date=D2 + timedelta(days=1),
                nightly_rate=Decimal("120.00"),
                reason="peak season",
                user=actor,
            )

    def test_override_requires_reason(self):
        from apps.common.exceptions import InvalidStayChange
        from apps.stays.services import ExtendStayService

        rtype = _priced_type(self.hotel, code="EX4", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="323")
        with self.assertRaises(InvalidStayChange):
            ExtendStayService.execute(
                stay,
                new_check_out_date=D2 + timedelta(days=1),
                nightly_rate=Decimal("120.00"),
                reason="",
                user=self.manager,
            )

    def test_default_extension_needs_no_finance_permission(self):
        from apps.stays.services import ExtendStayService

        rtype = _priced_type(self.hotel, code="EX5", rate="100.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="324")
        clerk = add_member(self.hotel, "clerk2@x.com", perms=["stays.extend"])
        # No rate provided => default extension, no special permission required.
        ExtendStayService.execute(
            stay, new_check_out_date=D2 + timedelta(days=1), user=clerk
        )
        stay.refresh_from_db()
        added = stay.rate_periods.get(start_date=D2)
        self.assertEqual(added.source, "extension")
        self.assertEqual(added.nightly_rate, Decimal("100.00"))

    def test_shorten_then_extend_no_overlap_and_correct_billing(self):
        """FIX 1 — shortening trims the rate periods, so a later extend cannot
        overlap a still-long period and silently bill the OLD rate for re-added
        nights (which would mask the audited override)."""
        from apps.finance.services import ensure_due_room_charges, folio_balance
        from apps.stays.services import ExtendStayService, ShortenStayService

        rtype = _priced_type(self.hotel, code="SEX", rate="100.00")
        stay = _check_in(
            self.hotel, self.manager, rtype, number="330",
            ci=D1, co=D1 + timedelta(days=4),  # original [D1, D5) @ 100
        )
        _set_arrival(stay, D1)
        # Shorten [D1,D5) -> [D1,D3): the original period is trimmed to end at D3.
        ShortenStayService.execute(
            stay, new_check_out_date=D1 + timedelta(days=2), user=self.manager
        )
        # Extend [D1,D3) -> [D1,D6) at an OVERRIDE 150 for the re-added nights.
        ExtendStayService.execute(
            stay,
            new_check_out_date=D1 + timedelta(days=5),  # D6
            nightly_rate=Decimal("150.00"),
            reason="rebooked longer",
            user=self.manager,
        )
        stay.refresh_from_db()
        periods = list(stay.rate_periods.order_by("start_date"))
        # Exactly two DISJOINT periods remain (no overlap).
        self.assertEqual(len(periods), 2)
        self.assertEqual(
            (periods[0].start_date, periods[0].end_date, periods[0].nightly_rate),
            (D1, D1 + timedelta(days=2), Decimal("100.00")),
        )
        self.assertEqual(
            (periods[1].start_date, periods[1].end_date, periods[1].nightly_rate),
            (D1 + timedelta(days=2), D1 + timedelta(days=5), Decimal("150.00")),
        )
        self.assertLessEqual(periods[0].end_date, periods[1].start_date)  # disjoint
        # Billing: D1,D1+1 @100 ; D1+2,D1+3,D1+4 @150 — the override is NOT masked.
        posted = ensure_due_room_charges(
            stay, as_of=D1 + timedelta(days=5), user=self.manager
        )
        self.assertEqual(posted, 5)
        folio = stay.folios.get()
        self.assertEqual(str(folio_balance(folio)["balance"]), "650.00")  # 200 + 450
        # Idempotent re-run: no duplicate, no change.
        self.assertEqual(
            ensure_due_room_charges(
                stay, as_of=D1 + timedelta(days=5), user=self.manager
            ),
            0,
        )


class RoomAccountChargeGuardTests(APITestCase):
    """ITEM 7 — a non-night charge always has ``room_night`` NULL and never
    collides on the room-night unique index; ``post_room_account_charge`` now
    requires an explicit ``charge_type``."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "rag@x.com", kind=MembershipType.MANAGER)
        self.rtype = _priced_type(self.hotel)
        self.stay = _check_in(self.hotel, self.manager, self.rtype, number="401")

    def test_non_night_charge_null_room_night_and_source_reuse_ok(self):
        from apps.finance.models import ChargeType
        from apps.finance.services import (
            ROOM_NIGHT_SOURCE, add_charge, ensure_stay_folio,
        )

        folio = ensure_stay_folio(self.stay, user=self.manager)
        c1 = add_charge(
            folio, charge_type=ChargeType.SERVICE, description="minibar",
            quantity=1, unit_amount="10.00", source=ROOM_NIGHT_SOURCE, user=self.manager,
        )
        self.assertIsNone(c1.room_night)  # non-night charge => room_night NULL
        # Reusing the SAME source on a second non-night charge does NOT trip the
        # (folio, room_night) unique index — it only constrains room_night NOT NULL.
        c2 = add_charge(
            folio, charge_type=ChargeType.SERVICE, description="minibar2",
            quantity=1, unit_amount="10.00", source=ROOM_NIGHT_SOURCE, user=self.manager,
        )
        self.assertIsNone(c2.room_night)
        self.assertEqual(
            folio.charges.filter(
                source=ROOM_NIGHT_SOURCE, room_night__isnull=True
            ).count(),
            2,
        )

    def test_post_room_account_charge_requires_charge_type(self):
        from apps.finance.models import ChargeType
        from apps.finance.services import ensure_stay_folio, post_room_account_charge

        folio = ensure_stay_folio(self.stay, user=self.manager)
        with self.assertRaises(TypeError):
            post_room_account_charge(
                folio, description="x", quantity=1, unit_amount="5.00",
                user=self.manager,
            )
        # With an explicit type it posts and never sets room_night.
        charge = post_room_account_charge(
            folio, description="x", quantity=1, unit_amount="5.00",
            charge_type=ChargeType.SERVICE, user=self.manager,
        )
        self.assertIsNone(charge.room_night)


class OverstayBillingTests(APITestCase):
    """ITEM 1 — overstay nights are NEVER auto-billed past the planned check-out;
    an overstay shows in ``needs_attention``; an Extend makes the newly-in-window
    night due; a conflicting later booking blocks the Extend."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "ovs@x.com", kind=MembershipType.MANAGER)
        self.rtype = _priced_type(self.hotel)

    def _overstay(self, number):
        """An in-house stay whose planned window (D1-3 .. D1-1) has fully elapsed
        by today's business date (D1): a genuine overstay."""
        stay = _check_in(
            self.hotel, self.manager, self.rtype, number=number,
            ci=D1 - timedelta(days=3), co=D1 - timedelta(days=1),
            guest_name=f"OS{number}",
        )
        _set_arrival(stay, D1 - timedelta(days=3))
        return stay

    def test_overstay_bills_only_up_to_planned_check_out(self):
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges

        stay = self._overstay("501")
        posted = ensure_due_room_charges(stay, user=self.manager)  # real business date
        self.assertEqual(posted, 2)  # nights D1-3, D1-2 only
        folio = stay.folios.get()
        nights = set(
            folio.charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).values_list("room_night", flat=True)
        )
        self.assertEqual(nights, {D1 - timedelta(days=3), D1 - timedelta(days=2)})
        # NOT one night on/after the planned check-out was billed.
        self.assertFalse(any(n >= stay.planned_check_out_date for n in nights))

    def test_overstay_counted_in_needs_attention(self):
        from apps.stays.services import stays_overview

        # Assert the overstay's SPECIFIC contribution (a delta of exactly one),
        # not merely ">= 1": a single genuine overstay must raise needs_attention
        # by exactly one over the pre-existing baseline.
        before = stays_overview(self.hotel)["needs_attention"]
        self._overstay("502")
        after = stays_overview(self.hotel)["needs_attention"]
        self.assertEqual(after - before, 1)

    def test_extend_makes_newly_in_window_night_due(self):
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import ensure_due_room_charges
        from apps.stays.services import ExtendStayService

        stay = self._overstay("503")
        # Bill the two genuinely consumed nights first.
        self.assertEqual(ensure_due_room_charges(stay, user=self.manager), 2)
        # Extend past today: the former check-out night (D1-1) is now inside the
        # window and already before today's business date, so it becomes due.
        ExtendStayService.execute(
            stay, new_check_out_date=D1 + timedelta(days=1), user=self.manager
        )
        stay.refresh_from_db()
        posted = ensure_due_room_charges(stay, user=self.manager)
        self.assertEqual(posted, 1)
        folio = stay.folios.get()
        nights = set(
            folio.charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).values_list("room_night", flat=True)
        )
        self.assertIn(D1 - timedelta(days=1), nights)

    def test_extend_rejects_conflicting_later_booking(self):
        from apps.common.exceptions import RoomAssignmentConflict
        from apps.stays.services import ExtendStayService

        stay = _check_in(
            self.hotel, self.manager, self.rtype, number="504",
            ci=D1, co=D1 + timedelta(days=2),
        )
        # A back-to-back booking pinned to the SAME room blocks the extension.
        make_reservation(
            self.hotel, self.rtype, room=stay.room,
            ci=D1 + timedelta(days=2), co=D1 + timedelta(days=4),
        )
        with self.assertRaises(RoomAssignmentConflict):
            ExtendStayService.execute(
                stay, new_check_out_date=D1 + timedelta(days=3), user=self.manager
            )


class DailyCloseRoomChargeTests(APITestCase):
    """ITEM 2 — the daily close posts every due room night BEFORE building its
    snapshot; it is idempotent, fail-safe (a posting failure rolls the whole close
    back), and does not scale queries per stay."""

    def _make_hotel(self, slug):
        from apps.hotels.models import HotelSettings

        hotel = make_hotel(slug=slug)
        manager = add_member(hotel, f"dc-{slug}@x.com", kind=MembershipType.MANAGER)
        HotelSettings.objects.update_or_create(
            hotel=hotel,
            defaults={
                "default_currency": "USD", "timezone": "UTC", "business_date": D1,
            },
        )
        return hotel, manager, _priced_type(hotel, code="DC")

    def _consumed_stay(self, hotel, manager, rtype, number, *, nights_ago=2):
        """An in-house stay with ``nights_ago`` nights consumed by business date D1."""
        ci = D1 - timedelta(days=nights_ago)
        stay = _check_in(
            hotel, manager, rtype, number=number, ci=ci, co=D1,
            guest_name=f"C{number}",
        )
        _set_arrival(stay, ci)
        return stay

    def test_close_posts_due_nights_before_snapshot(self):
        from apps.finance.models import ChargeType, PostingStatus
        from apps.finance.services import folio_balance
        from apps.shifts.services import close_business_day

        hotel, manager, rtype = self._make_hotel("dc1")
        stay = self._consumed_stay(hotel, manager, rtype, "601")
        folio = stay.folios.get()
        # Arrival-day check-in posted nothing yet.
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 0)
        close_business_day(hotel, D1, user=manager)
        posted = folio.charges.filter(type=ChargeType.ROOM, status=PostingStatus.POSTED)
        self.assertEqual(posted.count(), 2)  # both consumed nights posted BY the close
        self.assertEqual(str(folio_balance(folio)["balance"]), "200.00")

    def test_close_is_idempotent(self):
        from apps.finance.models import ChargeType
        from apps.shifts.services import close_business_day

        hotel, manager, rtype = self._make_hotel("dc2")
        stay = self._consumed_stay(hotel, manager, rtype, "602")
        close_business_day(hotel, D1, user=manager)  # posts 2, rolls to D2
        # The stay is still in-house (now overstaying); closing D2 must not
        # double-post the two already-billed nights.
        close_business_day(hotel, D1 + timedelta(days=1), user=manager)
        self.assertEqual(
            stay.folios.get().charges.filter(type=ChargeType.ROOM).count(), 2
        )

    def test_close_rolls_back_entirely_when_a_stay_fails(self):
        from apps.finance import services as fin
        from apps.finance.models import ChargeType, PostingStatus
        from apps.hotels.models import HotelSettings
        from apps.shifts.models import DailyClose, DailyCloseStatus
        from apps.shifts.services import close_business_day

        hotel, manager, rtype = self._make_hotel("dc3")
        stay_a = self._consumed_stay(hotel, manager, rtype, "603")
        stay_b = self._consumed_stay(hotel, manager, rtype, "604")
        real_ensure = fin.ensure_due_room_charges

        def failing(stay, **kw):
            if stay.id == stay_b.id:
                raise RuntimeError("controlled failure")
            return real_ensure(stay, **kw)

        with mock.patch.object(fin, "ensure_due_room_charges", side_effect=failing):
            with self.assertRaises(RuntimeError):
                close_business_day(hotel, D1, user=manager)

        # Fail-safe: no CLOSED close, the business date did NOT roll, and stay A's
        # charges (posted before B failed) rolled back with the whole close.
        self.assertFalse(
            DailyClose.objects.filter(
                hotel=hotel, business_date=D1, status=DailyCloseStatus.CLOSED
            ).exists()
        )
        self.assertEqual(HotelSettings.objects.get(hotel=hotel).business_date, D1)
        self.assertEqual(
            stay_a.folios.get().charges.filter(
                type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).count(),
            0,
        )

    def test_post_due_does_not_scale_queries_per_stay(self):
        """No N+1 on active stays (owner requirement). FIX-2 reads the business
        date ONCE (passed through / one lock, forwarded as ``as_of``) and joins
        ``hotel__settings``, so the redundant PER-STAY business-date lock and
        timezone read are gone.

        Proven two ways:
          (a) the OPTIMISED per-stay marginal is a CONSTANT — equal across 1/2/3
              stays, i.e. queries scale linearly with no super-linear fan-out;
          (b) with-vs-without the fix: the OLD path (no ``as_of``, no
              ``hotel__settings`` join) issues STRICTLY MORE queries per stay —
              exactly the two redundant reads the fix removed — directly measuring
              what changed rather than trusting a loose absolute bound."""
        from django.db import connection, transaction
        from django.test.utils import CaptureQueriesContext

        from apps.finance.services import (
            ensure_due_room_charges,
            post_due_room_charges_for_hotel,
        )
        from apps.stays.models import Stay, StayStatus

        def _seed(n_stays, slug):
            hotel, mgr, rtype = self._make_hotel(slug)
            for i in range(n_stays):
                self._consumed_stay(hotel, mgr, rtype, f"{slug}{i}", nights_ago=1)
            return hotel, mgr

        def optimized_cost(n_stays, slug):
            hotel, mgr = _seed(n_stays, slug)
            with CaptureQueriesContext(connection) as ctx:
                post_due_room_charges_for_hotel(
                    hotel, business_date=D1, user=mgr
                )
            return len(ctx.captured_queries)

        def unoptimized_cost(n_stays, slug):
            # The OLD per-stay path: iterate WITHOUT ``as_of`` and WITHOUT the
            # ``hotel__settings`` join, so each stay re-locks HotelSettings for the
            # business date AND re-reads ``hotel.settings`` for the timezone. Same
            # single-transaction shape as post_due so only the two reads differ.
            hotel, mgr = _seed(n_stays, slug)
            control_qs = (
                Stay.objects.filter(hotel=hotel, status=StayStatus.IN_HOUSE)
                .select_related(
                    "hotel", "room", "room__room_type", "reservation",
                    "reservation_line", "reservation_line__room_type",
                )  # deliberately NO "hotel__settings"
                .order_by("id")
            )
            with CaptureQueriesContext(connection) as ctx:
                with transaction.atomic():
                    for stay in control_qs:
                        ensure_due_room_charges(stay, user=mgr)  # no as_of
            return len(ctx.captured_queries)

        o1, o2, o3 = (
            optimized_cost(1, "dcqA"),
            optimized_cost(2, "dcqB"),
            optimized_cost(3, "dcqC"),
        )
        opt_marginal = o2 - o1
        # (a) constant marginal ⇒ linear scaling, no super-linear per-stay fan-out.
        self.assertEqual(opt_marginal, o3 - o2, (o1, o2, o3))

        # (b) with vs without the fix: the unoptimised path costs strictly more
        # per stay — the two redundant reads (business-date lock + settings tz).
        u2, u3 = unoptimized_cost(2, "dcqD"), unoptimized_cost(3, "dcqE")
        unopt_marginal = u3 - u2
        self.assertGreater(unopt_marginal, opt_marginal, (opt_marginal, unopt_marginal))
        self.assertGreaterEqual(unopt_marginal - opt_marginal, 2)


class FinancialDetailRBACTests(APITestCase):
    """ITEM 4 — a stay's folio/insurance detail is MONETARY-gated on
    ``finance.view``. A viewer with ``stays.view`` / ``stays.check_out`` but
    WITHOUT ``finance.view`` receives abstract OPERATIONAL states only — never a
    balance, currency, insurance amount, settlement detail or ``payment_status``.
    The backend stays the final arbiter of checkout readiness: the clearance flag
    flips as money is settled WITHOUT ever exposing the amount. Tenant scoping is
    unchanged (a stay from another hotel is 404)."""

    # Monetary/sensitive keys that must be ABSENT for a non-finance viewer in the
    # checkout-dialog folio-summary payload (endpoint + ensure-room-charges).
    # STAYS Item 10 — the folio list itself (``open_folios``) and the folio
    # ``folio_number`` are internal financial identifiers, so they are gone too.
    ENDPOINT_MONEY_KEYS = (
        "balance", "total_charges", "total_payments",
        "insurances", "insurance_pending", "payment_status",
        "open_folios", "folio_number",
        # STAYS owner item 6 — the current nightly rate is finance-only too.
        "current_nightly_rate", "current_rate_currency",
    )
    # …and in the §12 resident-card block.
    CARD_MONEY_KEYS = (
        "balance", "total_charges", "total_payments", "currency",
        "payment_status", "folio_number", "awaiting_final_charges",
        "current_nightly_rate", "current_rate_currency",
    )

    def setUp(self):
        from apps.finance.services import ensure_due_room_charges

        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "rbac-mgr@x.com", kind=MembershipType.MANAGER
        )
        self.rtype = _priced_type(self.hotel)  # base_rate 100 -> billable nights
        # ONE in-house stay with a genuine, non-zero balance (2 nights * 100).
        self.stay = _check_in(self.hotel, self.manager, self.rtype, number="401")
        ensure_due_room_charges(
            self.stay, as_of=self.stay.planned_check_out_date, user=self.manager
        )
        # Members, each with a single, specific permission set. The finance
        # viewer also holds ``stays.view`` because the read endpoints are gated on
        # it — ``finance.view`` alone never opens a stays read route.
        self.viewer = add_member(self.hotel, "view@x.com", perms=["stays.view"])
        self.checker = add_member(
            self.hotel, "chk@x.com", perms=["stays.check_out"]
        )
        self.finance_viewer = add_member(
            self.hotel, "fin@x.com", perms=["stays.view", "finance.view"]
        )

    # ---- helpers ----------------------------------------------------------
    def _folio_summary(self, user, stay_id=None):
        self.client.force_authenticate(user)
        return self.client.get(
            reverse("stays:stay-folio-summary", args=[stay_id or self.stay.id]),
            **HDR(self.hotel),
        )

    def _current_row(self, user, stay=None):
        self.client.force_authenticate(user)
        r = self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        assert r.status_code == 200, r.status_code
        sid = (stay or self.stay).id
        return next(x for x in r.data["results"] if x["id"] == sid)

    def _assert_no_money(self, data, keys):
        for k in keys:
            self.assertNotIn(k, data, f"monetary key '{k}' leaked to a non-finance viewer")

    # ---- view-only (stays.view) -------------------------------------------
    def test_view_only_endpoint_is_abstract_and_money_free(self):
        r = self._folio_summary(self.viewer)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["financial_details_visible"])
        self.assertFalse(r.data["financial_clearance_complete"])  # balance 200
        self.assertTrue(r.data["requires_financial_action"])
        self.assertFalse(r.data["can_check_out"])
        self._assert_no_money(r.data, self.ENDPOINT_MONEY_KEYS)
        # STAYS Item 10 — a non-finance viewer gets NO folio list at all: the
        # ``open_folios`` skeleton (which leaked folio ``id`` + ``folio_number``)
        # is removed. Only the abstract states + the awaiting bool remain.
        self.assertNotIn("open_folios", r.data)
        self.assertNotIn("folio_number", r.data)
        self.assertTrue(r.data["has_folio"])  # existence flag is still honest
        self.assertIn("awaiting_final_charges", r.data)

    def test_view_only_current_residents_card_is_abstract(self):
        summary = self._current_row(self.viewer)["folio_summary"]
        self.assertIsNotNone(summary)
        # Abstract clearance flags + the FIX 2 operational rate-coverage block
        # (dates/flags, NOT money) — no monetary keys.
        self.assertEqual(
            set(summary),
            {
                "financial_details_visible",
                "financial_clearance_complete",
                "requires_financial_action",
                "requires_rate_remediation",
                "missing_rate_ranges",
                "remediation_allowed",
                "requires_extension_first",
            },
        )
        self.assertFalse(summary["financial_details_visible"])
        self.assertTrue(summary["requires_financial_action"])
        self._assert_no_money(summary, self.CARD_MONEY_KEYS)

    # ---- check-out-only (stays.check_out) ---------------------------------
    def test_check_out_only_member_never_sees_money(self):
        # stays.view gating is UNCHANGED: check_out alone cannot READ the folio
        # summary or the resident list (both are gated on stays.view)…
        self.client.force_authenticate(self.checker)
        self.assertEqual(
            self.client.get(
                reverse("stays:stay-folio-summary", args=[self.stay.id]),
                **HDR(self.hotel),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("stays:stay-current"), **HDR(self.hotel)
            ).status_code,
            403,
        )
        # …but the checkout-dialog opener it IS allowed to call
        # (ensure-room-charges, gated on stays.check_out) returns the SAME
        # money-free operational summary.
        r = self.client.post(
            reverse("stays:stay-ensure-room-charges", args=[self.stay.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["financial_details_visible"])
        self.assertTrue(r.data["requires_financial_action"])
        self._assert_no_money(r.data, self.ENDPOINT_MONEY_KEYS)

    # ---- finance.view + manager -------------------------------------------
    def test_finance_viewer_sees_full_monetary_detail(self):
        r = self._folio_summary(self.finance_viewer)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["financial_details_visible"])
        self.assertEqual(r.data["balance"], "200.00")
        self.assertIn("insurances", r.data)
        self.assertIn("insurance_pending", r.data)
        self.assertEqual(r.data["open_folios"][0]["balance"], "200.00")
        self.assertIn("currency", r.data["open_folios"][0])
        # §12 card also carries the monetary block for a finance viewer.
        summary = self._current_row(self.finance_viewer)["folio_summary"]
        self.assertTrue(summary["financial_details_visible"])
        self.assertEqual(summary["balance"], "200.00")
        self.assertEqual(summary["payment_status"], "unpaid")

    def test_manager_sees_full_monetary_detail(self):
        r = self._folio_summary(self.manager)
        self.assertTrue(r.data["financial_details_visible"])
        self.assertEqual(r.data["balance"], "200.00")
        summary = self._current_row(self.manager)["folio_summary"]
        self.assertTrue(summary["financial_details_visible"])
        self.assertEqual(summary["balance"], "200.00")

    # ---- owner item 6: current nightly rate (finance-view only) -----------
    def test_finance_viewer_sees_current_nightly_rate(self):
        from apps.stays.services import latest_rate_period

        # The setUp stay's only (booking) period is priced at 100 in USD.
        self.assertEqual(latest_rate_period(self.stay).nightly_rate, Decimal("100.00"))
        r = self._folio_summary(self.finance_viewer)
        self.assertEqual(r.data["current_nightly_rate"], "100.00")
        self.assertEqual(r.data["current_rate_currency"], "USD")
        card = self._current_row(self.finance_viewer)["folio_summary"]
        self.assertEqual(card["current_nightly_rate"], "100.00")
        self.assertEqual(card["current_rate_currency"], "USD")

    def test_current_rate_reflects_latest_extension_period(self):
        from apps.stays.services import ExtendStayService

        # Extend at a NEW override rate; the current rate is the LATEST period's —
        # exactly what a further extension would default from.
        ExtendStayService.execute(
            self.stay,
            new_check_out_date=self.stay.planned_check_out_date + timedelta(days=1),
            nightly_rate=Decimal("175.00"),
            reason="peak season",
            user=self.manager,
        )
        r = self._folio_summary(self.finance_viewer)
        self.assertEqual(r.data["current_nightly_rate"], "175.00")

    def test_non_finance_viewer_never_sees_current_rate(self):
        r = self._folio_summary(self.viewer)
        self.assertFalse(r.data["financial_details_visible"])
        self._assert_no_money(
            r.data, ("current_nightly_rate", "current_rate_currency")
        )
        card = self._current_row(self.viewer)["folio_summary"]
        self._assert_no_money(
            card, ("current_nightly_rate", "current_rate_currency")
        )

    # ---- clearance flips on settlement, amount stays hidden ---------------
    def test_clearance_flips_after_settlement_for_non_finance_viewer(self):
        from apps.finance.services import record_folio_settlement

        before = self._folio_summary(self.viewer)
        self.assertTrue(before.data["requires_financial_action"])
        self._assert_no_money(before.data, self.ENDPOINT_MONEY_KEYS)
        # Settle the balance to zero via the finance service. The amount is 200,
        # but the non-finance viewer must never see it — only the flag flips.
        record_folio_settlement(
            self.stay.folios.get(), method="cash", amount="200.00",
            user=self.manager,
        )
        after = self._folio_summary(self.viewer)
        self.assertTrue(after.data["financial_clearance_complete"])
        self.assertFalse(after.data["requires_financial_action"])
        self.assertTrue(after.data["can_check_out"])
        self.assertFalse(after.data["financial_details_visible"])
        self._assert_no_money(after.data, self.ENDPOINT_MONEY_KEYS)
        # The resident card flips too — still money-free.
        card = self._current_row(self.viewer)["folio_summary"]
        self.assertTrue(card["financial_clearance_complete"])
        self._assert_no_money(card, self.CARD_MONEY_KEYS)

    def test_held_insurance_blocks_clearance_without_exposing_amount(self):
        from apps.finance.services import record_folio_settlement, record_insurance

        # Settle the room balance so ONLY the held insurance stands between the
        # guest and clearance.
        record_folio_settlement(
            self.stay.folios.get(), method="cash", amount="200.00",
            user=self.manager,
        )
        record_insurance(
            hotel=self.hotel, amount="150.00", stay=self.stay, user=self.manager
        )
        r = self._folio_summary(self.viewer)
        self.assertFalse(r.data["financial_clearance_complete"])  # insurance held
        self.assertTrue(r.data["requires_financial_action"])
        self.assertFalse(r.data["can_check_out"])
        # No insurance amount OR existence leaks for a non-finance viewer.
        self._assert_no_money(r.data, self.ENDPOINT_MONEY_KEYS)
        # A finance viewer DOES see the held insurance and its amount.
        fr = self._folio_summary(self.finance_viewer)
        self.assertTrue(fr.data["insurance_pending"])
        self.assertEqual(fr.data["insurances"][0]["held_amount"], "150.00")

    # ---- FIX-3: §12 resident card clearance accounts for held insurance ----
    def test_held_stay_insurance_blocks_card_clearance_non_finance_viewer(self):
        from apps.finance.services import record_folio_settlement, record_insurance

        # Settle the room balance so ONLY held insurance stands between the guest
        # and clearance; a STAY-linked insurance is caught by the card prefetch.
        record_folio_settlement(
            self.stay.folios.get(), method="cash", amount="200.00",
            user=self.manager,
        )
        record_insurance(
            hotel=self.hotel, amount="150.00", stay=self.stay, user=self.manager
        )
        card = self._current_row(self.viewer)["folio_summary"]
        self.assertFalse(card["financial_clearance_complete"])
        self.assertTrue(card["requires_financial_action"])
        self._assert_no_money(card, self.CARD_MONEY_KEYS)

    def test_reservation_level_insurance_blocks_card_clearance(self):
        from apps.finance.services import record_folio_settlement, record_insurance

        record_folio_settlement(
            self.stay.folios.get(), method="cash", amount="200.00",
            user=self.manager,
        )
        # Insurance held against the RESERVATION (stay=None) — the card's bounded
        # prefetch must catch it via the reservation branch, matching the checkout
        # gate (so the card never claims clearance the service would refuse).
        record_insurance(
            hotel=self.hotel, amount="80.00",
            reservation=self.stay.reservation, stay=None, user=self.manager,
        )
        card = self._current_row(self.viewer)["folio_summary"]
        self.assertFalse(card["financial_clearance_complete"])
        self.assertTrue(card["requires_financial_action"])
        self._assert_no_money(card, self.CARD_MONEY_KEYS)

    # ---- tenant isolation -------------------------------------------------
    def test_stay_from_another_hotel_is_404(self):
        other = make_hotel(slug="rbac-other")
        other_mgr = add_member(
            other, "other-mgr@x.com", kind=MembershipType.MANAGER
        )
        other_rtype = _priced_type(other, code="OTH")
        other_stay = _check_in(other, other_mgr, other_rtype, number="901")
        # Neither a non-finance viewer nor a finance viewer of THIS hotel can
        # resolve a stay id from another hotel — permission never crosses tenants.
        self.assertEqual(
            self._folio_summary(self.viewer, other_stay.id).status_code, 404
        )
        self.assertEqual(
            self._folio_summary(self.finance_viewer, other_stay.id).status_code, 404
        )


class ReservationInsuranceClearanceTests(APITestCase):
    """FIX-1 — the checkout-dialog folio summary MUST use the same held-insurance
    query as ``CheckOutService`` (``held_insurance_qs``), so RESERVATION-level
    insurance (``stay`` NULL) blocks ``can_check_out`` instead of the endpoint
    saying "ready" while the service raises ``InsuranceNotSettled``."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "resins@x.com", kind=MembershipType.MANAGER
        )
        # UNPRICED room type -> zero room balance, so ONLY the insurance can block.
        self.rtype = make_type(self.hotel, code="RIN")
        self.room = make_room(self.hotel, self.rtype, number="710")
        self.res, self.line = make_reservation(
            self.hotel, self.rtype, room=self.room
        )

    def _stay(self):
        from apps.stays.services import CheckInService

        return CheckInService.execute(
            self.hotel, reservation=self.res, reservation_line=self.line,
            room=self.room, primary_guest=make_guest(self.hotel),
            companions=(), user=self.manager,
        )

    def _summary(self, stay):
        self.client.force_authenticate(self.manager)
        return self.client.get(
            reverse("stays:stay-folio-summary", args=[stay.id]), **HDR(self.hotel)
        )

    def test_reservation_insurance_blocks_summary_and_matches_service(self):
        from apps.common.exceptions import InsuranceNotSettled
        from apps.finance.services import record_insurance
        from apps.stays.services import CheckOutService

        stay = self._stay()
        # Insurance taken at BOOKING against the reservation, stay not yet linked.
        record_insurance(
            hotel=self.hotel, amount="120.00", reservation=self.res, stay=None,
            user=self.manager,
        )
        # Zero folio balance (unpriced room) — the OLD stay=stay-only endpoint
        # query would have said "ready"; the shared query must NOT.
        r = self._summary(stay)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["financial_clearance_complete"])
        self.assertFalse(r.data["can_check_out"])
        # The endpoint's verdict matches the service, which BLOCKS on the same set.
        with self.assertRaises(InsuranceNotSettled):
            CheckOutService.execute(
                stay, checkout_reason="early departure", user=self.manager
            )

    def test_summary_ready_once_reservation_insurance_refunded(self):
        from apps.finance.services import record_insurance, refund_insurance
        from apps.stays.services import CheckOutService

        stay = self._stay()
        ins = record_insurance(
            hotel=self.hotel, amount="120.00", reservation=self.res, stay=None,
            user=self.manager,
        )
        refund_insurance(ins, reason="no damage", user=self.manager)  # held -> 0
        r = self._summary(stay)
        self.assertTrue(r.data["financial_clearance_complete"])
        self.assertTrue(r.data["can_check_out"])
        # And the service now lets the guest depart (nothing held, zero balance).
        out = CheckOutService.execute(
            stay, checkout_reason="early departure", user=self.manager
        )
        self.assertEqual(out.status, StayStatus.CHECKED_OUT)


class StayRatePeriodBackfillTests(APITestCase):
    """STAYS rate-integrity round — the 0005 data migration materialises a
    ``StayRatePeriod`` for pre-existing IN_HOUSE stays ONLY from a RELIABLE agreed
    source (``reservation_line.agreed_nightly_rate``). It NEVER fabricates a rate:
    a stay with no reliable source gets NO period (an honest 'needs attention'
    gap). Idempotent (get_or_create on (stay, start_date))."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "bf@x.com", kind=MembershipType.MANAGER)

    def _run_backfill(self):
        from importlib import import_module
        from types import SimpleNamespace

        from django.apps import apps as global_apps
        from django.db import connection

        mod = import_module("apps.stays.migrations.0005_drop_stay_nightly_rate")
        # The data step only needs ``schema_editor.connection.alias`` — pass a thin
        # shim so no DDL/transaction is opened inside the test's own transaction.
        mod.create_periods_from_agreed_rate(
            global_apps, SimpleNamespace(connection=connection)
        )

    def test_backfill_creates_period_from_reliable_agreed_rate(self):
        rtype = _priced_type(self.hotel, code="BF1", rate="130.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="810")
        # Simulate a stay admitted BEFORE the rate-period table existed.
        stay.rate_periods.all().delete()
        self._run_backfill()
        period = stay.rate_periods.get()
        self.assertEqual(period.nightly_rate, Decimal("130.00"))
        self.assertEqual(period.source, "booking")
        self.assertEqual(period.start_date, stay.planned_check_in_date)

    def test_backfill_creates_no_period_without_reliable_source(self):
        rtype = make_type(self.hotel, code="BF2")  # unpriced -> agreed rate NULL
        stay = _check_in(self.hotel, self.manager, rtype, number="811")
        stay.rate_periods.all().delete()
        self._run_backfill()
        # No fabricated rate: the honest gap is left to surface as needs-attention.
        self.assertEqual(stay.rate_periods.count(), 0)

    def test_backfill_is_idempotent(self):
        rtype = _priced_type(self.hotel, code="BF3", rate="130.00")
        stay = _check_in(self.hotel, self.manager, rtype, number="812")
        stay.rate_periods.all().delete()
        self._run_backfill()
        self._run_backfill()  # a second run must not duplicate
        self.assertEqual(stay.rate_periods.count(), 1)


class ImmediateCheckInFolioRBACTests(APITestCase):
    """STAYS Item 11 — the immediate-check-in RESULT exposes folio identifiers /
    currency / balance ONLY to a viewer holding ``finance.view``. A front-desk user
    with reservations.create + stays.check_in but WITHOUT finance.view gets
    ``folio: null`` (no id/number/currency/balance leak), never a placeholder."""

    def setUp(self):
        self.hotel = make_hotel()
        self.rtype = _priced_type(self.hotel, code="IMR", rate="100.00")
        self.room = make_room(self.hotel, self.rtype, number="330")

    def _payload(self):
        return {
            "reservation": {
                "check_in_date": D1.isoformat(),
                "check_out_date": D2.isoformat(),
                "primary_guest_name": "Imm Guest",
                "adults": 1,
                "children": 0,
                "lines": [
                    {"room_type": self.rtype.id, "quantity": 1, "room": self.room.id}
                ],
            },
            "room": self.room.id,
        }

    def _post(self, user):
        self.client.force_authenticate(user)
        return self.client.post(
            reverse("stays:stay-immediate-check-in"),
            self._payload(), format="json", **HDR(self.hotel),
        )

    def test_non_finance_user_gets_no_folio_detail(self):
        clerk = add_member(
            self.hotel, "imr-clerk@x.com",
            perms=["reservations.create", "stays.check_in"],
        )
        r = self._post(clerk)
        self.assertEqual(r.status_code, 201, r.data)
        # The stay + reservation are returned; the folio detail is withheld.
        self.assertIsNotNone(r.data["stay"])
        self.assertIsNone(r.data["folio"])  # no id/number/currency/balance leak

    def test_finance_user_gets_folio_detail(self):
        fin = add_member(
            self.hotel, "imr-fin@x.com",
            perms=["reservations.create", "stays.check_in", "finance.view"],
        )
        r = self._post(fin)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNotNone(r.data["folio"])
        self.assertIn("folio_number", r.data["folio"])
        self.assertIn("balance", r.data["folio"])


class ImmediateCheckInDraftPinTests(APITestCase):
    """Round 3 §7.3 — the reserved number is PINNED end-to-end through the IMMEDIATE
    check-in path. Reserve a number (an OPEN ``ReservationDraft`` keyed by an
    idempotency_key), then immediate-check-in with that SAME idempotency_key nested
    in the reservation body (exactly as the front desk sends it). The created
    reservation must carry the EXACT reserved number and the draft must be CONSUMED.

    This is the round's key coverage gap: it proves the reserve → immediate-check-in
    pin/consume handshake works, not just the plain create path."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "immdraft@x.com", kind=MembershipType.MANAGER
        )
        self.rtype = _priced_type(self.hotel, code="IPD", rate="100.00")
        self.room = make_room(self.hotel, self.rtype, number="440")
        self.client.force_authenticate(self.manager)

    def _reserve_number(self, key):
        return self.client.post(
            reverse("reservations:reservation-reserve-number"),
            {"idempotency_key": key},
            format="json",
            **HDR(self.hotel),
        )

    def _immediate_check_in(self, key):
        return self.client.post(
            reverse("stays:stay-immediate-check-in"),
            {
                "reservation": {
                    "check_in_date": D1.isoformat(),
                    "check_out_date": D2.isoformat(),
                    "primary_guest_name": "Pinned Guest",
                    "adults": 1,
                    "children": 0,
                    # The FE nests the reserved key inside the reservation body.
                    "idempotency_key": key,
                    "lines": [
                        {
                            "room_type": self.rtype.id,
                            "quantity": 1,
                            "room": self.room.id,
                        }
                    ],
                },
                "room": self.room.id,
            },
            format="json",
            **HDR(self.hotel),
        )

    def test_immediate_check_in_pins_reserved_number_and_consumes_draft(self):
        from apps.reservations.models import (
            ReservationDraft,
            ReservationDraftStatus,
        )

        reserved = self._reserve_number("imm-k1")
        self.assertEqual(reserved.status_code, 201, reserved.data)
        reserved_number = reserved.data["reservation_number"]
        draft_id = reserved.data["draft_id"]

        result = self._immediate_check_in("imm-k1")
        self.assertEqual(result.status_code, 201, result.data)
        # (a) the created reservation carries the EXACT reserved number.
        self.assertEqual(
            result.data["reservation"]["reservation_number"], reserved_number
        )
        # (b) the draft is now CONSUMED (its number was pinned, never re-allocated).
        draft = ReservationDraft.objects.get(id=draft_id)
        self.assertEqual(draft.status, ReservationDraftStatus.CONSUMED)
        # Exactly one reservation exists and it is the pinned one (no fresh number
        # was allocated alongside the reserved draft).
        self.assertEqual(
            Reservation.objects.filter(
                hotel=self.hotel, reservation_number=reserved_number
            ).count(),
            1,
        )

    def _immediate_check_in_with_deposit(self, key):
        return self.client.post(
            reverse("stays:stay-immediate-check-in"),
            {
                "reservation": {
                    "check_in_date": D1.isoformat(),
                    "check_out_date": D2.isoformat(),
                    "primary_guest_name": "Idem Guest",
                    "adults": 1,
                    "children": 0,
                    "idempotency_key": key,
                    "lines": [
                        {"room_type": self.rtype.id, "quantity": 1, "room": self.room.id}
                    ],
                },
                "room": self.room.id,
                "deposit": {"amount": "50.00", "method": "cash"},
            },
            format="json",
            **HDR(self.hotel),
        )

    def test_immediate_check_in_idempotent_no_duplicate_side_effects(self):
        """S6 remediation — a REPLAYED immediate check-in (same idempotency key, e.g.
        a lost-201 retry) returns the SAME reservation and creates NO second Stay,
        Folio, or deposit Payment — no operational/financial duplication."""
        from apps.finance.models import Folio, Payment
        from apps.guests.models import Guest
        from apps.reservations.models import ReservationDraft, ReservationDraftStatus
        from apps.stays.models import Stay

        reserved = self._reserve_number("imm-idem")
        self.assertEqual(reserved.status_code, 201, reserved.data)
        reserved_number = reserved.data["reservation_number"]
        draft_id = reserved.data["draft_id"]

        first = self._immediate_check_in_with_deposit("imm-idem")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(
            first.data["reservation"]["reservation_number"], reserved_number
        )

        # Replay with the SAME key (simulates a retry after a lost response).
        second = self._immediate_check_in_with_deposit("imm-idem")
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(
            second.data["reservation"]["reservation_number"], reserved_number
        )

        # Exactly ONE of everything — no duplicate booking / stay / folio / payment.
        res = Reservation.objects.get(hotel=self.hotel)
        self.assertEqual(res.reservation_number, reserved_number)
        self.assertEqual(Reservation.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Stay.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(
            Folio.objects.filter(hotel=self.hotel, reservation=res).count(), 1
        )
        folio = Folio.objects.get(hotel=self.hotel, reservation=res)
        self.assertEqual(Payment.objects.filter(folio=folio).count(), 1)
        # No duplicate/orphan Guest leaked by the replay (the guest is created only
        # on the fresh-booking path, after the idempotency gate).
        self.assertEqual(Guest.objects.filter(hotel=self.hotel).count(), 1)
        draft = ReservationDraft.objects.get(id=draft_id)
        self.assertEqual(draft.status, ReservationDraftStatus.CONSUMED)
        self.assertEqual(draft.reservation_id, res.id)

    # ---- S6 remediation: complete-fingerprint immediate-check-in coverage -----
    def _immediate_custom(self, key, *, deposit=None, reservation_over=None):
        body = {
            "reservation": {
                "check_in_date": D1.isoformat(),
                "check_out_date": D2.isoformat(),
                "primary_guest_name": "Idem Guest",
                "adults": 1,
                "children": 0,
                "idempotency_key": key,
                "lines": [
                    {"room_type": self.rtype.id, "quantity": 1, "room": self.room.id}
                ],
            },
            "room": self.room.id,
        }
        if reservation_over:
            body["reservation"].update(reservation_over)
        if deposit is not None:
            body["deposit"] = deposit
        return self.client.post(
            reverse("stays:stay-immediate-check-in"),
            body,
            format="json",
            **HDR(self.hotel),
        )

    def _effect_counts(self):
        from apps.finance.models import Folio, Payment
        from apps.guests.models import Guest
        from apps.stays.models import Stay

        return (
            Reservation.objects.filter(hotel=self.hotel).count(),
            Stay.objects.filter(hotel=self.hotel).count(),
            Folio.objects.filter(hotel=self.hotel).count(),
            Payment.objects.filter(folio__hotel=self.hotel).count(),
            Guest.objects.filter(hotel=self.hotel).count(),
        )

    def test_immediate_different_deposit_amount_rejected(self):
        self._reserve_number("dep-amt")
        first = self._immediate_custom("dep-amt", deposit={"amount": "50.00", "method": "cash"})
        self.assertEqual(first.status_code, 201, first.data)
        second = self._immediate_custom("dep-amt", deposit={"amount": "500.00", "method": "cash"})
        self.assertEqual(second.status_code, 409, second.data)
        self.assertEqual(self._effect_counts(), (1, 1, 1, 1, 1))

    def test_immediate_different_deposit_method_rejected(self):
        self._reserve_number("dep-method")
        first = self._immediate_custom("dep-method", deposit={"amount": "50.00", "method": "cash"})
        self.assertEqual(first.status_code, 201, first.data)
        second = self._immediate_custom("dep-method", deposit={"amount": "50.00", "method": "card"})
        self.assertEqual(second.status_code, 409, second.data)
        self.assertEqual(self._effect_counts(), (1, 1, 1, 1, 1))

    def test_immediate_different_deposit_currency_rejected(self):
        self._reserve_number("dep-cur")
        first = self._immediate_custom(
            "dep-cur", deposit={"amount": "50.00", "currency": "USD", "method": "cash"}
        )
        self.assertEqual(first.status_code, 201, first.data)
        second = self._immediate_custom(
            "dep-cur",
            deposit={
                "amount": "50.00", "currency": "EUR", "method": "cash",
                "exchange_rate": "1.10", "original_amount": "45.45",
            },
        )
        self.assertEqual(second.status_code, 409, second.data)
        self.assertEqual(self._effect_counts(), (1, 1, 1, 1, 1))

    def test_immediate_key_reuse_across_operations_conflict(self):
        # The key is first used for a PLAIN reservation create; reusing it for an
        # immediate check-in is a DIFFERENT operation scope -> 409, no side effects.
        create = self.client.post(
            reverse("reservations:reservation-list"),
            {
                "check_in_date": D1.isoformat(),
                "check_out_date": D2.isoformat(),
                "primary_guest_name": "Cross Guest",
                "status": "confirmed",
                "idempotency_key": "cross-op",
                "lines": [{"room_type": self.rtype.id, "quantity": 1}],
            },
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(create.status_code, 201, create.data)
        conflict = self._immediate_custom("cross-op", deposit={"amount": "50.00", "method": "cash"})
        self.assertEqual(conflict.status_code, 409, conflict.data)
        from apps.stays.models import Stay

        self.assertEqual(Reservation.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Stay.objects.filter(hotel=self.hotel).count(), 0)

    def test_immediate_json_order_independent_replay(self):
        self._reserve_number("json-order")
        first = self._immediate_custom("json-order", deposit={"amount": "50.00", "method": "cash"})
        self.assertEqual(first.status_code, 201, first.data)
        number = first.data["reservation"]["reservation_number"]
        # SAME logical payload, DIFFERENT key ordering everywhere — the canonical
        # fingerprint must match, so this is a replay (same reservation), not a 409.
        reordered = {
            "room": self.room.id,
            "deposit": {"method": "cash", "amount": "50.00"},
            "reservation": {
                "lines": [
                    {"quantity": 1, "room": self.room.id, "room_type": self.rtype.id}
                ],
                "idempotency_key": "json-order",
                "children": 0,
                "adults": 1,
                "primary_guest_name": "Idem Guest",
                "check_out_date": D2.isoformat(),
                "check_in_date": D1.isoformat(),
            },
        }
        second = self.client.post(
            reverse("stays:stay-immediate-check-in"),
            reordered,
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(second.data["reservation"]["reservation_number"], number)
        self.assertEqual(self._effect_counts(), (1, 1, 1, 1, 1))

    def test_immediate_replay_after_folio_closed(self):
        from apps.finance.models import Folio, FolioStatus

        self._reserve_number("folio-closed")
        first = self._immediate_custom("folio-closed", deposit={"amount": "50.00", "method": "cash"})
        self.assertEqual(first.status_code, 201, first.data)
        res = Reservation.objects.get(hotel=self.hotel)
        folio = Folio.objects.get(hotel=self.hotel, reservation=res)
        # Simulate check-out closing the folio between the original call and the retry.
        Folio.objects.filter(pk=folio.pk).update(status=FolioStatus.CLOSED)
        second = self._immediate_custom("folio-closed", deposit={"amount": "50.00", "method": "cash"})
        self.assertEqual(second.status_code, 201, second.data)
        # Same reservation; the CLOSED folio is returned (not None, not re-opened).
        self.assertEqual(second.data["reservation"]["reservation_number"], res.reservation_number)
        self.assertIsNotNone(second.data["folio"])
        self.assertEqual(second.data["folio"]["status"], FolioStatus.CLOSED)
        folio.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.CLOSED)
        self.assertEqual(self._effect_counts(), (1, 1, 1, 1, 1))


class ImmediateCheckInIdempotencyConcurrencyTests(TransactionTestCase):
    """S6 remediation — a TRUE two-connection concurrent immediate check-in with the
    same idempotency key produces exactly ONE of everything (Reservation / Stay /
    Folio / Payment / Guest) and no 500. PostgreSQL-only (real row locks)."""

    def setUp(self):
        self.hotel = make_hotel(slug="imm-conc")
        self.manager = add_member(
            self.hotel, "imm-conc@x.com", kind=MembershipType.MANAGER
        )
        self.rtype = _priced_type(self.hotel, code="ICC", rate="100.00")
        self.room = make_room(self.hotel, self.rtype, number="501")
        # A second room of the type so the NO-DRAFT loser's type-availability check
        # passes and it reaches the creation_idempotency_key backstop (then replays)
        # rather than failing on inventory. (The WITH-draft loser replays earlier.)
        self.room2 = make_room(self.hotel, self.rtype, number="502")

    def _worker(self, barrier, results, index, key):
        from django.db import connections

        from apps.stays.orchestration import execute_immediate_check_in

        try:
            barrier.wait(timeout=15)
            result = execute_immediate_check_in(
                self.hotel,
                lines=[{"room_type": self.rtype, "quantity": 1, "room": self.room}],
                room=self.room,
                deposit={"amount": "50.00", "method": "cash"},
                check_in_date=D1,
                check_out_date=D2,
                primary_guest_name="Conc Guest",
                adults=1,
                children=0,
                idempotency_key=key,
                user=self.manager,
            )
            results[index] = result["reservation"].reservation_number
        except Exception as exc:  # noqa: BLE001 - a leaked error must be visible
            results[index] = f"unexpected:{type(exc).__name__}:{exc}"
        finally:
            connections["default"].close()

    def test_concurrent_immediate_check_in_no_duplicates(self):
        import threading

        from django.db import connection, transaction

        from apps.finance.models import Folio, Payment
        from apps.guests.models import Guest
        from apps.reservations.services import reserve_reservation_number

        if connection.vendor != "postgresql":
            self.skipTest(
                "True two-connection immediate check-in concurrency needs PostgreSQL "
                "row locks; skipped on SQLite to avoid a false green."
            )

        with transaction.atomic():
            reserve_reservation_number(
                self.hotel, idempotency_key="icc", user=self.manager
            )

        barrier = threading.Barrier(2)
        results = [None, None]
        threads = [
            threading.Thread(target=self._worker, args=(barrier, results, i, "icc"))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for t in threads:
            self.assertFalse(t.is_alive(), "an immediate-check-in worker timed out")
        for r in results:
            self.assertFalse(
                str(r).startswith("unexpected:"),
                f"an unexpected error escaped a worker: {r}",
            )
        self.assertEqual(results[0], results[1])  # both see the SAME reservation
        self.assertEqual(Reservation.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Stay.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Folio.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Payment.objects.filter(folio__hotel=self.hotel).count(), 1)
        self.assertEqual(Guest.objects.filter(hotel=self.hotel).count(), 1)

    def test_concurrent_immediate_check_in_no_draft_is_safe(self):
        """The NO-DRAFT immediate-check-in path (no pre-reserved draft → no early
        draft-lock serialization). Under a true concurrent same-key race pinning the
        SAME room, the path is NOT cleanly replayable: room overlap is enforced at
        availability BEFORE the creation-key backstop. The owner-adopted outcome is a
        SAFE REJECTION — exactly ONE check-in succeeds fully, the other fails with a
        clear DOMAIN conflict (room/availability), with ZERO partial effects (still
        one of everything), never a duplicate booking and never a 500/IntegrityError
        leak. (The real front-desk flow always reserves a draft first, which replays
        cleanly — see test_concurrent_immediate_check_in_no_duplicates.)"""
        import threading

        from django.db import connection

        from apps.finance.models import Folio, Payment
        from apps.guests.models import Guest
        from apps.reservations.models import ReservationDraft

        if connection.vendor != "postgresql":
            self.skipTest(
                "True two-connection immediate check-in concurrency needs PostgreSQL "
                "row locks; skipped on SQLite to avoid a false green."
            )

        # Deliberately NO reserve_reservation_number -> no draft for this key.
        self.assertEqual(
            ReservationDraft.objects.filter(
                hotel=self.hotel, idempotency_key="icc-nd"
            ).count(),
            0,
        )

        barrier = threading.Barrier(2)
        results = [None, None]
        threads = [
            threading.Thread(target=self._worker, args=(barrier, results, i, "icc-nd"))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for t in threads:
            self.assertFalse(t.is_alive(), "a no-draft immediate-check-in worker timed out")

        successes = [r for r in results if not str(r).startswith("unexpected:")]
        rejections = [r for r in results if str(r).startswith("unexpected:")]
        # Exactly one succeeds; exactly one is safely rejected.
        self.assertEqual(len(successes), 1, results)
        self.assertEqual(len(rejections), 1, results)
        # The rejection is a clean DOMAIN conflict, NOT a server error / integrity leak.
        self.assertTrue(
            any(
                name in rejections[0]
                for name in (
                    "RoomAssignmentConflict",
                    "NoAvailability",
                    "IdempotencyKeyConflict",
                )
            ),
            rejections[0],
        )
        self.assertNotIn("IntegrityError", rejections[0])
        # ZERO partial effects from the rejected worker — exactly one of everything.
        self.assertEqual(Reservation.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Stay.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Folio.objects.filter(hotel=self.hotel).count(), 1)
        self.assertEqual(Payment.objects.filter(folio__hotel=self.hotel).count(), 1)
        self.assertEqual(Guest.objects.filter(hotel=self.hotel).count(), 1)


class GapStayBlockFlowTests(APITestCase):
    """FIX 4 — the missing-rate block is REAL end-to-end: a stay with a DUE night
    and NO covering rate period blocks check-out (folio stays OPEN) and rolls back
    the daily-close room posting entirely (nothing settles short)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "gap@x.com", kind=MembershipType.MANAGER)

    def _gap_stay(self, number, *, guest="Gap"):
        """An in-house stay whose window (D1-2 .. D1) elapsed by today (D1), with a
        DUE night but NO rate period — a genuine data gap."""
        rtype = _priced_type(self.hotel, code=f"G{number}", rate="100.00")
        room = make_room(self.hotel, rtype, number=number)
        res, line = make_reservation(
            self.hotel, rtype, room=room, ci=D1 - timedelta(days=2), co=D1
        )
        stay = Stay.objects.create(
            hotel=self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name=guest),
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1 - timedelta(days=2), planned_check_out_date=D1,
            actual_check_in_at=timezone.now(),
        )
        _set_arrival(stay, D1 - timedelta(days=2))
        return stay

    def test_checkout_blocked_and_folio_stays_open(self):
        from apps.common.exceptions import MissingAgreedNightlyRate
        from apps.finance.models import FolioStatus
        from apps.finance.services import ensure_stay_folio
        from apps.stays.services import CheckOutService

        stay = self._gap_stay("360")
        folio = ensure_stay_folio(stay, user=self.manager)  # OPEN, no rate period
        with self.assertRaises(MissingAgreedNightlyRate):
            CheckOutService.execute(stay, user=self.manager)
        # The block is real: nothing settled — folio OPEN, stay still IN_HOUSE.
        folio.refresh_from_db()
        stay.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.OPEN)
        self.assertEqual(stay.status, StayStatus.IN_HOUSE)

    def test_daily_close_room_posting_rolls_back_entirely(self):
        from apps.common.exceptions import MissingAgreedNightlyRate
        from apps.finance.models import ChargeType, FolioCharge, PostingStatus
        from apps.finance.services import (
            ensure_stay_folio, post_due_room_charges_for_hotel,
        )

        # A HEALTHY overstay (has a rate period, due nights) AND a GAP stay in the
        # SAME hotel. The healthy one would post if the pass were not atomic.
        rtype = _priced_type(self.hotel, code="OKS", rate="100.00")
        healthy = _check_in(
            self.hotel, self.manager, rtype, number="361",
            ci=D1 - timedelta(days=2), co=D1,
        )
        _set_arrival(healthy, D1 - timedelta(days=2))
        ensure_stay_folio(self._gap_stay("362"), user=self.manager)
        with self.assertRaises(MissingAgreedNightlyRate):
            post_due_room_charges_for_hotel(self.hotel)
        # Atomic: the healthy stay's nights were rolled back too — nothing posted,
        # so the daily close cannot settle short (it would fail and not close).
        self.assertEqual(
            FolioCharge.objects.filter(
                hotel=self.hotel, type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).count(),
            0,
        )


class NullRatePeriodBlockTests(APITestCase):
    """STAYS item 2 — a NULL-rate (unpriced) COVERING period is the agreed price
    MISSING, not a free night: it blocks posting/checkout/daily close, surfaces as
    needs-rate-remediation, and never creates a zero/short charge."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "np@x.com", kind=MembershipType.MANAGER)

    def _unpriced_overstay(self, number):
        # In-house stay whose window elapsed by today, with a NULL-rate booking
        # period (unpriced room type) — a due night with no positive rate. Arrival
        # is set AFTER check-in so the check-in-day post sees no due night.
        rtype = make_type(self.hotel, code=f"N{number}")  # no base_rate -> NULL
        stay = _check_in(
            self.hotel, self.manager, rtype, number=number,
            ci=D1 - timedelta(days=2), co=D1,
        )
        _set_arrival(stay, D1 - timedelta(days=2))
        return stay

    def test_null_period_blocks_checkout_folio_open(self):
        from apps.common.exceptions import MissingAgreedNightlyRate
        from apps.finance.models import ChargeType, FolioStatus
        from apps.stays.services import CheckOutService

        stay = self._unpriced_overstay("370")
        folio = stay.folios.get()
        with self.assertRaises(MissingAgreedNightlyRate):
            CheckOutService.execute(stay, user=self.manager)
        folio.refresh_from_db()
        stay.refresh_from_db()
        self.assertEqual(folio.status, FolioStatus.OPEN)
        self.assertEqual(stay.status, StayStatus.IN_HOUSE)
        self.assertEqual(folio.charges.filter(type=ChargeType.ROOM).count(), 0)

    def test_null_period_blocks_daily_close(self):
        from apps.common.exceptions import MissingAgreedNightlyRate
        from apps.finance.models import ChargeType, FolioCharge, PostingStatus
        from apps.finance.services import post_due_room_charges_for_hotel

        self._unpriced_overstay("371")
        with self.assertRaises(MissingAgreedNightlyRate):
            post_due_room_charges_for_hotel(self.hotel)
        self.assertEqual(
            FolioCharge.objects.filter(
                hotel=self.hotel, type=ChargeType.ROOM, status=PostingStatus.POSTED
            ).count(),
            0,
        )

    def test_null_period_surfaces_as_needs_rate_remediation(self):
        from apps.stays.rate_periods import stay_requires_rate_remediation

        stay = self._unpriced_overstay("372")
        self.assertTrue(stay_requires_rate_remediation(stay))
        # Operational flag exposed on the serializer (NOT finance-gated).
        self.client.force_authenticate(self.manager)
        r = self.client.get(
            reverse("stays:stay-detail", args=[stay.id]), **HDR(self.hotel)
        )
        self.assertTrue(r.data["requires_rate_remediation"])


class CentralRatePeriodServiceTests(APITestCase):
    """STAYS item 8/7 — the central rate-period service validates rate + currency
    and rejects overlaps (all StayRatePeriod writes route through it)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "crp@x.com", kind=MembershipType.MANAGER)
        self.rtype = _priced_type(self.hotel, code="CRP", rate="100.00")
        # Booking period [D1, D2) @ 100 USD.
        self.stay = _check_in(self.hotel, self.manager, self.rtype, number="380")

    def test_overlapping_period_different_start_rejected(self):
        from apps.common.exceptions import RatePeriodOverlap
        from apps.stays.models import StayRatePeriodSource
        from apps.stays.rate_periods import create_rate_period

        with self.assertRaises(RatePeriodOverlap):
            create_rate_period(
                self.stay,
                start_date=D1 + timedelta(days=1),  # inside [D1, D2)
                end_date=D2 + timedelta(days=1),
                nightly_rate=Decimal("120.00"),
                currency="USD",
                source=StayRatePeriodSource.OVERRIDE,
            )

    def test_empty_currency_priced_period_rejected(self):
        from apps.common.exceptions import InvalidFinanceOperation
        from apps.stays.models import StayRatePeriodSource
        from apps.stays.rate_periods import create_rate_period

        with self.assertRaises(InvalidFinanceOperation):
            create_rate_period(
                self.stay, start_date=D2, end_date=D2 + timedelta(days=1),
                nightly_rate=Decimal("120.00"), currency="",  # priced but empty
                source=StayRatePeriodSource.EXTENSION,
            )

    def test_mismatched_currency_priced_period_rejected(self):
        from apps.common.exceptions import InvalidFinanceOperation
        from apps.stays.models import StayRatePeriodSource
        from apps.stays.rate_periods import create_rate_period

        with self.assertRaises(InvalidFinanceOperation):
            create_rate_period(
                self.stay, start_date=D2, end_date=D2 + timedelta(days=1),
                nightly_rate=Decimal("120.00"), currency="EUR",  # != folio USD
                source=StayRatePeriodSource.EXTENSION,
            )

    def test_priced_booking_empty_currency_rejected(self):
        # FIX E + FIX 1 — a PRICED line with EMPTY captured currency is rejected at
        # check-in (no silent folio-currency fallback). The FIX 1 folio-currency
        # resolver (``_stay_folio_currency`` in ``ensure_stay_folio``) blocks first
        # with ``FolioCurrencyMismatch`` reason ``missing_line_currency``.
        from apps.common.exceptions import FolioCurrencyMismatch
        from apps.reservations.models import ReservationRoomLine
        from apps.stays.services import CheckInService

        rtype = _priced_type(self.hotel, code="FE", rate="100.00")
        room = make_room(self.hotel, rtype, number="900")
        res, line = make_reservation(self.hotel, rtype, room=room)
        # Simulate a legacy PRICED line whose captured currency is EMPTY.
        ReservationRoomLine.objects.filter(pk=line.pk).update(agreed_rate_currency="")
        line.refresh_from_db()
        with self.assertRaises(FolioCurrencyMismatch) as ctx:
            CheckInService.execute(
                self.hotel, reservation=res, reservation_line=line, room=room,
                primary_guest=make_guest(self.hotel, name="FE"), companions=(),
                user=self.manager,
            )
        self.assertEqual(ctx.exception.detail["reason"], "missing_line_currency")

    def test_conflicting_data_same_start_rejected(self):
        # FIX C — a second write at the SAME start_date with DIFFERENT data is a
        # conflict (not a silent no-op). The booking period is [D1, D2) @ 100.
        from apps.common.exceptions import RatePeriodConflict
        from apps.stays.models import StayRatePeriodSource
        from apps.stays.rate_periods import create_rate_period

        with self.assertRaises(RatePeriodConflict):
            create_rate_period(
                self.stay, start_date=D1, end_date=D2,
                nightly_rate=Decimal("175.00"), currency="USD",  # differs from 100
                source=StayRatePeriodSource.BOOKING,
            )

    def test_identical_re_request_is_idempotent(self):
        # FIX C — an IDENTICAL re-request returns the existing period, created=False.
        from apps.stays.models import StayRatePeriodSource
        from apps.stays.rate_periods import create_rate_period

        existing = self.stay.rate_periods.get()
        period, created = create_rate_period(
            self.stay, start_date=D1, end_date=D2,
            nightly_rate=Decimal("100.00"), currency="USD",
            source=StayRatePeriodSource.BOOKING,
        )
        self.assertEqual(period.id, existing.id)
        self.assertFalse(created)


class StayRateRemediationTests(APITestCase):
    """STAYS item 3 — the audited legacy rate-remediation service + endpoint."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "rr@x.com", kind=MembershipType.MANAGER)

    def _gap_stay(self, number):
        from apps.finance.services import ensure_stay_folio

        rtype = _priced_type(self.hotel, code=f"R{number}", rate="100.00")
        room = make_room(self.hotel, rtype, number=number)
        res, line = make_reservation(
            self.hotel, rtype, room=room, ci=D1 - timedelta(days=2), co=D1
        )
        stay = Stay.objects.create(
            hotel=self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="Rem"),
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1 - timedelta(days=2), planned_check_out_date=D1,
            actual_check_in_at=timezone.now(),
        )
        _set_arrival(stay, D1 - timedelta(days=2))
        ensure_stay_folio(stay, user=self.manager)
        return stay

    def _body(self, **over):
        body = {
            "start_date": str(D1 - timedelta(days=2)),
            "end_date": str(D1),
            "nightly_rate": "100.00",
            "currency": "USD",
            "reason": "legacy import gap",
        }
        body.update(over)
        return body

    def _remediate(self, stay, user, **over):
        self.client.force_authenticate(user)
        return self.client.post(
            reverse("stays:stay-remediate-rate", args=[stay.id]),
            self._body(**over), format="json", **HDR(self.hotel),
        )

    def test_requires_permission(self):
        stay = self._gap_stay("390")
        clerk = add_member(self.hotel, "rr-clerk@x.com", perms=["stays.view"])
        self.assertEqual(self._remediate(stay, clerk).status_code, 403)

    def test_requires_reason(self):
        stay = self._gap_stay("391")
        actor = add_member(self.hotel, "rr-act@x.com", perms=["stays.rate_override"])
        self.assertEqual(self._remediate(stay, actor, reason="").status_code, 400)

    def test_creates_period_and_enables_billing(self):
        from apps.finance.services import ensure_due_room_charges, folio_balance

        stay = self._gap_stay("392")
        r = self._remediate(stay, self.manager)
        self.assertEqual(r.status_code, 200, r.data)
        period = stay.rate_periods.get()
        self.assertEqual(period.source, "legacy_remediation")
        self.assertEqual(period.nightly_rate, Decimal("100.00"))
        self.assertEqual(period.approved_by, self.manager)
        self.assertTrue(period.override_reason)
        posted = ensure_due_room_charges(stay, as_of=D1, user=self.manager)
        self.assertEqual(posted, 2)  # both due nights now billable
        self.assertEqual(str(folio_balance(stay.folios.get())["balance"]), "200.00")

    def test_rejects_already_posted_night(self):
        from apps.common.exceptions import RatePeriodCoversPostedNight
        from apps.finance.models import ChargeType
        from apps.finance.services import ROOM_NIGHT_SOURCE, add_charge
        from apps.stays.rate_periods import remediate_stay_rate

        stay = self._gap_stay("393")
        folio = stay.folios.get()
        add_charge(
            folio, charge_type=ChargeType.ROOM, description="n", quantity=1,
            unit_amount="100.00", source=ROOM_NIGHT_SOURCE,
            room_night=D1 - timedelta(days=2), user=self.manager,
        )
        with self.assertRaises(RatePeriodCoversPostedNight):
            remediate_stay_rate(
                stay, start_date=D1 - timedelta(days=2), end_date=D1,
                nightly_rate=Decimal("100.00"), currency="USD", reason="x",
                user=self.manager,
            )

    def test_is_idempotent_and_audits_once(self):
        # FIX D — two IDENTICAL remediations create ONE period and emit exactly ONE
        # ``stay.rate_remediated`` audit event (no duplicate on the idempotent retry).
        from apps.notifications.models import ActivityEvent

        stay = self._gap_stay("394")
        self.assertEqual(self._remediate(stay, self.manager).status_code, 200)
        self.assertEqual(self._remediate(stay, self.manager).status_code, 200)
        self.assertEqual(stay.rate_periods.count(), 1)
        self.assertEqual(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="stay.rate_remediated"
            ).count(),
            1,
        )

    def test_conflicting_re_remediation_rejected(self):
        # FIX C — re-remediating the SAME window with a DIFFERENT rate is a 409
        # conflict, never a silent no-op that drops the new value.
        stay = self._gap_stay("396")
        self.assertEqual(self._remediate(stay, self.manager).status_code, 200)
        r = self._remediate(stay, self.manager, nightly_rate="180.00")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "rate_period_conflict")
        # The original period is untouched.
        self.assertEqual(stay.rate_periods.get().nightly_rate, Decimal("100.00"))

    def test_finance_charge_create_alone_cannot_remediate(self):
        # FIX B — legacy remediation is gated on stays.rate_override, NOT
        # finance.charge_create.
        stay = self._gap_stay("397")
        actor = add_member(
            self.hotel, "rr-fc@x.com", perms=["stays.view", "finance.charge_create"]
        )
        self.assertEqual(self._remediate(stay, actor).status_code, 403)

    def test_tenant_scoped(self):
        stay = self._gap_stay("395")
        other = make_hotel(slug="rr-other")
        outsider = add_member(other, "rr-out@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(outsider)
        r = self.client.post(
            reverse("stays:stay-remediate-rate", args=[stay.id]),
            self._body(), format="json", **HDR(other),
        )
        self.assertIn(r.status_code, (403, 404))


class CheckMissingStayRatesCommandTests(APITestCase):
    """STAYS item 4 — the read-only pre-release audit command."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "cmd@x.com", kind=MembershipType.MANAGER)

    def test_exit_nonzero_when_a_stay_has_a_gap(self):
        from django.core.management import call_command

        # A NULL-rate overstay = a due night with no positive rate.
        rtype = make_type(self.hotel, code="CMDN")
        stay = _check_in(
            self.hotel, self.manager, rtype, number="360",
            ci=D1 - timedelta(days=2), co=D1,
        )
        _set_arrival(stay, D1 - timedelta(days=2))
        with self.assertRaises(SystemExit) as ctx:
            call_command("check_missing_stay_rates")
        self.assertEqual(ctx.exception.code, 1)

    def test_exit_zero_when_all_covered(self):
        from django.core.management import call_command

        rtype = _priced_type(self.hotel, code="CMDP", rate="100.00")
        stay = _check_in(
            self.hotel, self.manager, rtype, number="361",
            ci=D1 - timedelta(days=2), co=D1,
        )
        _set_arrival(stay, D1 - timedelta(days=2))
        # A priced booking period covers every due night -> clean exit (no raise).
        call_command("check_missing_stay_rates")


def _hotel_with_currency(slug, code):
    from apps.hotels.models import HotelSettings

    hotel = make_hotel(slug=slug)
    HotelSettings.objects.create(hotel=hotel, default_currency=code, timezone="UTC")
    return hotel


class StayFolioCurrencyTests(APITestCase):
    """FIX 1 — the stay's folio adopts the BOOKING's agreed currency, NOT the
    hotel's CURRENT default; a conflicting/missing agreed currency or an existing
    folio in a different currency BLOCKS check-in (no auto-FX, no silent change)."""

    def setUp(self):
        self.hotel = _hotel_with_currency("fc", "EUR")
        self.manager = add_member(self.hotel, "fc@x.com", kind=MembershipType.MANAGER)

    def _set_default(self, code):
        from apps.hotels.models import HotelSettings

        HotelSettings.objects.filter(hotel=self.hotel).update(default_currency=code)

    def test_folio_adopts_booking_currency_not_current_default(self):
        from apps.stays.services import CheckInService

        rtype = _priced_type(self.hotel, code="BC", rate="100.00")
        room = make_room(self.hotel, rtype, number="500")
        res, line = make_reservation(self.hotel, rtype, room=room)  # booked in EUR
        self.assertEqual(line.agreed_rate_currency, "EUR")
        self._set_default("USD")  # the hotel changes its default AFTER booking
        stay = CheckInService.execute(
            self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="BC"), companions=(),
            user=self.manager,
        )
        # The folio + booking period both carry the BOOKING currency (EUR), not USD.
        self.assertEqual(stay.folios.get().currency, "EUR")
        self.assertEqual(stay.rate_periods.get().currency, "EUR")

    def test_conflicting_line_currencies_block_check_in(self):
        from apps.common.exceptions import FolioCurrencyMismatch
        from apps.reservations.models import ReservationRoomLine
        from apps.stays.services import CheckInService

        rtype = _priced_type(self.hotel, code="CF", rate="100.00")
        room = make_room(self.hotel, rtype, number="501")
        room2 = make_room(self.hotel, rtype, number="502")
        res, line = make_reservation(self.hotel, rtype, room=room)  # EUR
        ReservationRoomLine.objects.create(
            hotel=self.hotel, reservation=res, room_type=rtype, room=room2,
            quantity=1, agreed_nightly_rate=Decimal("100.00"),
            agreed_rate_currency="USD",  # a DIFFERENT agreed currency
        )
        with self.assertRaises(FolioCurrencyMismatch) as ctx:
            CheckInService.execute(
                self.hotel, reservation=res, reservation_line=line, room=room,
                primary_guest=make_guest(self.hotel, name="CF"), companions=(),
                user=self.manager,
            )
        self.assertEqual(ctx.exception.detail["reason"], "conflicting_line_currencies")
        self.assertFalse(res.folios.exists())  # blocked -> no folio

    def test_existing_folio_different_currency_blocks(self):
        from apps.common.exceptions import FolioCurrencyMismatch
        from apps.finance.models import Folio, FolioStatus
        from apps.finance.services import ensure_stay_folio

        rtype = _priced_type(self.hotel, code="EX", rate="100.00")
        room = make_room(self.hotel, rtype, number="503")
        res, line = make_reservation(self.hotel, rtype, room=room)  # EUR agreed
        stay = Stay.objects.create(
            hotel=self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="EX"),
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1, planned_check_out_date=D2,
            actual_check_in_at=timezone.now(),
        )
        folio = Folio.objects.create(
            hotel=self.hotel, stay=stay, guest=stay.primary_guest,
            customer_name="EX", folio_number="F-EX-1", currency="USD",
            status=FolioStatus.OPEN,
        )
        with self.assertRaises(FolioCurrencyMismatch) as ctx:
            ensure_stay_folio(stay, user=self.manager)
        self.assertEqual(ctx.exception.detail["reason"], "existing_folio_currency")
        folio.refresh_from_db()
        self.assertEqual(folio.currency, "USD")  # never silently changed

    def test_unpriced_stay_uses_hotel_default(self):
        # An UNPRICED stay has no agreed currency -> hotel default (keeps walk-in
        # check-in working; remediated later).
        rtype = make_type(self.hotel, code="UP")  # no base_rate
        stay = _check_in(self.hotel, self.manager, rtype, number="505")
        self.assertEqual(stay.folios.get().currency, "EUR")  # hotel default

    def test_immediate_check_in_folio_uses_booking_currency(self):
        from apps.stays.orchestration import execute_immediate_check_in

        rtype = _priced_type(self.hotel, code="IM", rate="100.00")
        room = make_room(self.hotel, rtype, number="504")
        result = execute_immediate_check_in(
            self.hotel,
            lines=[{"room_type": rtype, "quantity": 1, "room": room}],
            room=room, room_assignment_mode="manual", user=self.manager,
            check_in_date=D1, check_out_date=D2,
            source="walk_in", primary_guest_name="IM Guest",
        )
        self.assertEqual(result["folio"].currency, "EUR")

    def test_currency_resolution_is_tenant_isolated(self):
        from apps.stays.services import CheckInService

        other = _hotel_with_currency("fc-other", "USD")
        omgr = add_member(other, "fco@x.com", kind=MembershipType.MANAGER)
        ortype = _priced_type(other, code="OT", rate="100.00")
        oroom = make_room(other, ortype, number="601")
        ores, oline = make_reservation(other, ortype, room=oroom)  # USD
        rtype = _priced_type(self.hotel, code="TA", rate="100.00")
        room = make_room(self.hotel, rtype, number="602")
        res, line = make_reservation(self.hotel, rtype, room=room)  # EUR
        stay_a = CheckInService.execute(
            self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="A"), companions=(),
            user=self.manager,
        )
        stay_b = CheckInService.execute(
            other, reservation=ores, reservation_line=oline, room=oroom,
            primary_guest=make_guest(other, name="B"), companions=(), user=omgr,
        )
        self.assertEqual(stay_a.folios.get().currency, "EUR")
        self.assertEqual(stay_b.folios.get().currency, "USD")


class RateCoverageSummaryTests(APITestCase):
    """FIX 2 — the OPERATIONAL rate-coverage summary: contiguous
    ``missing_rate_ranges`` + remediation_allowed / requires_extension_first; an
    overstay range cannot be remediated directly (extend first)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "rc2@x.com", kind=MembershipType.MANAGER)

    def _stay(self, number, *, ci, co, periods):
        from apps.finance.services import ensure_stay_folio
        from apps.stays.models import StayRatePeriod

        rtype = _priced_type(self.hotel, code=f"C{number}", rate="100.00")
        room = make_room(self.hotel, rtype, number=number)
        res, line = make_reservation(self.hotel, rtype, room=room, ci=ci, co=co)
        stay = Stay.objects.create(
            hotel=self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name=f"C{number}"),
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=ci, planned_check_out_date=co,
            actual_check_in_at=timezone.now(),
        )
        _set_arrival(stay, ci)
        for s, e, rate in periods:
            StayRatePeriod.objects.create(
                hotel=self.hotel, stay=stay, start_date=s, end_date=e,
                nightly_rate=rate, currency="USD", source="booking",
            )
        ensure_stay_folio(stay, user=self.manager)
        return stay

    def test_whole_stay_gap(self):
        from apps.stays.rate_periods import rate_coverage_state

        stay = self._stay("610", ci=D1, co=D1 + timedelta(days=2), periods=[])
        state = rate_coverage_state(stay, business_date=D1 + timedelta(days=2))
        self.assertEqual(
            state["missing_rate_ranges"],
            [{"start_date": D1, "end_date": D1 + timedelta(days=2)}],
        )
        self.assertTrue(state["requires_rate_remediation"])
        self.assertTrue(state["remediation_allowed"])
        self.assertFalse(state["requires_extension_first"])

    def test_partial_gap_mid_stay(self):
        from apps.stays.rate_periods import rate_coverage_state

        stay = self._stay(
            "611", ci=D1, co=D1 + timedelta(days=3),
            periods=[
                (D1, D1 + timedelta(days=1), Decimal("100.00")),
                (D1 + timedelta(days=2), D1 + timedelta(days=3), Decimal("100.00")),
            ],
        )
        state = rate_coverage_state(stay, business_date=D1 + timedelta(days=3))
        self.assertEqual(
            state["missing_rate_ranges"],
            [{"start_date": D1 + timedelta(days=1), "end_date": D1 + timedelta(days=2)}],
        )
        self.assertTrue(state["remediation_allowed"])
        self.assertFalse(state["requires_extension_first"])

    def test_multiple_gaps(self):
        from apps.stays.rate_periods import rate_coverage_state

        stay = self._stay(
            "612", ci=D1, co=D1 + timedelta(days=4),
            periods=[(D1 + timedelta(days=1), D1 + timedelta(days=2), Decimal("100.00"))],
        )
        state = rate_coverage_state(stay, business_date=D1 + timedelta(days=4))
        self.assertEqual(
            state["missing_rate_ranges"],
            [
                {"start_date": D1, "end_date": D1 + timedelta(days=1)},
                {"start_date": D1 + timedelta(days=2), "end_date": D1 + timedelta(days=4)},
            ],
        )

    def test_overstay_gap_requires_extension_first(self):
        from apps.common.exceptions import RateRemediationRequiresExtension
        from apps.stays.rate_periods import rate_coverage_state, remediate_stay_rate

        # Priced fully in-plan [D1, D2); guest OVERSTAYS to D4 with no extension.
        stay = self._stay(
            "613", ci=D1, co=D2, periods=[(D1, D2, Decimal("100.00"))]
        )
        state = rate_coverage_state(stay, business_date=D2 + timedelta(days=2))
        self.assertTrue(state["requires_extension_first"])
        self.assertFalse(state["remediation_allowed"])
        self.assertEqual(
            state["missing_rate_ranges"],
            [{"start_date": D2, "end_date": D2 + timedelta(days=2)}],
        )
        # Remediating the overstay range directly is refused — extend first.
        with self.assertRaises(RateRemediationRequiresExtension):
            remediate_stay_rate(
                stay, start_date=D2, end_date=D2 + timedelta(days=2),
                nightly_rate=Decimal("100.00"), currency="USD", reason="x",
                user=self.manager,
            )

    def test_remediate_one_gap_leaves_the_other(self):
        from apps.stays.rate_periods import (
            rate_coverage_state, remediate_stay_rate,
        )

        stay = self._stay(
            "614", ci=D1, co=D1 + timedelta(days=4),
            periods=[(D1 + timedelta(days=1), D1 + timedelta(days=2), Decimal("100.00"))],
        )
        # Fill the FIRST gap [D1, D1+1) only.
        remediate_stay_rate(
            stay, start_date=D1, end_date=D1 + timedelta(days=1),
            nightly_rate=Decimal("100.00"), currency="USD", reason="gap1",
            user=self.manager,
        )
        state = rate_coverage_state(stay, business_date=D1 + timedelta(days=4))
        self.assertTrue(state["requires_rate_remediation"])  # the 2nd gap remains
        self.assertEqual(
            state["missing_rate_ranges"],
            [{"start_date": D1 + timedelta(days=2), "end_date": D1 + timedelta(days=4)}],
        )

    def test_summary_endpoint_exposes_ranges_to_non_finance(self):
        # The operational block is present for a non-finance viewer (dates/flags).
        # Past window so the DUE nights are already consumed by today's business date.
        stay = self._stay(
            "615", ci=D1 - timedelta(days=2), co=D1, periods=[]
        )
        viewer = add_member(self.hotel, "rc2-view@x.com", perms=["stays.view"])
        self.client.force_authenticate(viewer)
        r = self.client.get(
            reverse("stays:stay-folio-summary", args=[stay.id]), **HDR(self.hotel)
        )
        self.assertFalse(r.data["financial_details_visible"])
        self.assertTrue(r.data["requires_rate_remediation"])
        self.assertTrue(len(r.data["missing_rate_ranges"]) >= 1)
        self.assertIn("start_date", r.data["missing_rate_ranges"][0])
        self.assertTrue(r.data["remediation_allowed"])


class CheckoutErrorSanitizationTests(APITestCase):
    """FIX 3 — money-linked checkout / immediate-check-in errors are sanitized for a
    viewer WITHOUT finance.view (no folio id/number, balance, amount, or currency);
    a finance viewer keeps the detail."""

    def setUp(self):
        from apps.finance.services import ensure_due_room_charges

        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "san-mgr@x.com", kind=MembershipType.MANAGER)
        self.rtype = _priced_type(self.hotel, code="SAN", rate="100.00")
        self.stay = _check_in(self.hotel, self.manager, self.rtype, number="600")
        ensure_due_room_charges(
            self.stay, as_of=self.stay.planned_check_out_date, user=self.manager
        )
        self.checker = add_member(self.hotel, "san-chk@x.com", perms=["stays.check_out"])
        self.finance = add_member(
            self.hotel, "san-fin@x.com", perms=["stays.check_out", "finance.view"]
        )

    def _checkout(self, user):
        # A reason is supplied so the EARLY-departure guard passes and the checkout
        # reaches the outstanding-balance (money-linked) blocker.
        self.client.force_authenticate(user)
        return self.client.post(
            reverse("stays:stay-check-out", args=[self.stay.id]),
            {"checkout_reason": "leaving"}, format="json", **HDR(self.hotel),
        )

    def test_non_finance_checkout_error_is_sanitized(self):
        r = self._checkout(self.checker)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_balance_outstanding")
        details = r.data.get("details", {})
        for leaked in ("folio", "folio_number", "balance", "amount", "currency", "held"):
            self.assertNotIn(leaked, details)
        self.assertFalse(details.get("financial_details_visible"))
        self.assertTrue(details.get("requires_financial_action"))
        self.assertFalse(details.get("can_check_out"))

    def test_finance_checkout_error_keeps_detail(self):
        r = self._checkout(self.finance)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_balance_outstanding")
        self.assertIn("balance", r.data["details"])
        self.assertIn("folio_number", r.data["details"])

    def test_posting_currency_mismatch_sanitized_for_non_finance(self):
        # The posting-time currency guard raises a GENERIC InvalidFinanceOperation
        # carrying ``folio_currency``/``rate_currency``. On checkout it must ALSO be
        # sanitized for a non-finance viewer (money-linked KEY detection), while a
        # finance viewer keeps the detail.
        from apps.finance.services import ensure_stay_folio
        from apps.stays.models import StayRatePeriod

        rtype = _priced_type(self.hotel, code="MM", rate="100.00")
        room = make_room(self.hotel, rtype, number="620")
        res, line = make_reservation(
            self.hotel, rtype, room=room, ci=D1 - timedelta(days=2), co=D1
        )
        stay = Stay.objects.create(
            hotel=self.hotel, reservation=res, reservation_line=line, room=room,
            primary_guest=make_guest(self.hotel, name="MM"),
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1 - timedelta(days=2), planned_check_out_date=D1,
            actual_check_in_at=timezone.now(),
        )
        _set_arrival(stay, D1 - timedelta(days=2))
        ensure_stay_folio(stay, user=self.manager)  # USD folio (line is USD)
        # Force a MISMATCHING EUR rate period (a data mismatch the guard catches).
        StayRatePeriod.objects.create(
            hotel=self.hotel, stay=stay, start_date=D1 - timedelta(days=2), end_date=D1,
            nightly_rate=Decimal("100.00"), currency="EUR", source="booking",
        )

        self.client.force_authenticate(self.checker)  # no finance.view
        r = self.client.post(
            reverse("stays:stay-check-out", args=[stay.id]),
            {"checkout_reason": "leaving"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)  # InvalidFinanceOperation
        self.assertEqual(r.data["code"], "invalid_finance_operation")
        details = r.data.get("details", {})
        for leaked in (
            "folio_currency", "rate_currency", "room_night", "balance", "amount",
        ):
            self.assertNotIn(leaked, details)
        self.assertFalse(details.get("financial_details_visible"))
        self.assertTrue(details.get("requires_financial_action"))

        # A finance viewer still sees the full detail (currency codes included).
        self.client.force_authenticate(self.finance)
        r2 = self.client.post(
            reverse("stays:stay-check-out", args=[stay.id]),
            {"checkout_reason": "leaving"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r2.status_code, 400)
        self.assertIn("folio_currency", r2.data["details"])

    def test_run_finance_gated_helper_sanitizes(self):
        # The SAME helper wraps the immediate-check-in path — covers it too.
        from types import SimpleNamespace

        from apps.common.exceptions import FolioBalanceOutstanding
        from apps.stays.views import _run_finance_gated

        def boom():
            raise FolioBalanceOutstanding(
                {"folio": 1, "folio_number": "F1", "balance": "200.00"}
            )

        req_nf = SimpleNamespace(user=self.checker, hotel=self.hotel)
        with self.assertRaises(FolioBalanceOutstanding) as ctx:
            _run_finance_gated(req_nf, boom)
        # The rendered payload uses ``_sanitized_details`` (raw booleans, no money).
        d = ctx.exception._sanitized_details
        for leaked in ("folio", "folio_number", "balance", "amount", "currency"):
            self.assertNotIn(leaked, d)
        self.assertIs(d["financial_details_visible"], False)
        self.assertIs(d["requires_financial_action"], True)
        self.assertIs(d["can_check_out"], False)

        req_f = SimpleNamespace(user=self.finance, hotel=self.hotel)
        with self.assertRaises(FolioBalanceOutstanding) as ctx2:
            _run_finance_gated(req_f, boom)
        # Finance viewer: original detail preserved, NOT sanitized.
        self.assertIsNone(getattr(ctx2.exception, "_sanitized_details", None))
        self.assertIn("balance", ctx2.exception.detail)
