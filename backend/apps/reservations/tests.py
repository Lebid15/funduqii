"""Tests for reservations & the availability engine (Phase 6).

Covers authorization + tenant isolation, the availability engine (inventory
math, blocking statuses, held expiry, date overlap vs back-to-back, capacity,
self-exclusion on edit), the reservation lifecycle (create/confirm/cancel/hold,
no hard delete, status logs, overbooking prevention), and regressions.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.rbac.services import grant_permission
from apps.reservations.availability import AvailabilityService
from apps.reservations.models import (
    Reservation,
    ReservationRoomLine,
    ReservationStatus,
    ReservationStatusLog,
)
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

# Fixed far-future dates so tests never depend on "today".
D1 = date(2030, 1, 10)
D2 = date(2030, 1, 12)
D3 = date(2030, 1, 14)


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


def make_type(hotel, code="STD", **kw):
    return RoomType.objects.create(
        hotel=hotel,
        name=kw.pop("name", "Standard"),
        code=code,
        base_capacity=kw.pop("base_capacity", 2),
        max_capacity=kw.pop("max_capacity", 3),
        **kw,
    )


def make_rooms(hotel, rtype, count, *, floor=None, start=101, **kw):
    floor = floor or Floor.objects.create(hotel=hotel, name="Ground")
    rooms = []
    for i in range(count):
        rooms.append(
            Room.objects.create(
                hotel=hotel,
                floor=floor,
                room_type=rtype,
                number=str(start + i),
                **kw,
            )
        )
    return rooms


def res_payload(rtype, **over):
    body = {
        "check_in_date": D1.isoformat(),
        "check_out_date": D2.isoformat(),
        "primary_guest_name": "John Guest",
        "adults": 2,
        "children": 0,
        "status": "confirmed",
        "lines": [{"room_type": rtype.id, "quantity": 1}],
    }
    body.update(over)
    return body


# --------------------------------------------------------------------------- #
# Access / permissions                                                         #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)
        make_rooms(self.hotel, self.rtype, 2)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(self.hotel)
            ).status_code,
            401,
        )

    def test_user_without_membership_denied(self):
        outsider = User.objects.create_user(
            email="o@x.com", password="StrongPass!234", full_name="O"
        )
        self.client.force_authenticate(outsider)
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_cannot_access_other_hotel(self):
        other = make_hotel(slug="other")
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(other)
            ).status_code,
            403,
        )

    def test_platform_owner_not_auto_member(self):
        owner = User.objects.create_platform_owner(
            email="owner@x.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_manager_can_view_and_create(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(self.hotel)
            ).status_code,
            200,
        )
        res = self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype),
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)

    def test_staff_view_permission(self):
        staff = add_member(self.hotel, "s@x.com", perms=["reservations.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(self.hotel)
            ).status_code,
            200,
        )

    def test_staff_without_permission_denied(self):
        staff = add_member(self.hotel, "s2@x.com")
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_staff_create_needs_create_permission(self):
        staff = add_member(self.hotel, "s3@x.com", perms=["reservations.view"])
        self.client.force_authenticate(staff)
        res = self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype),
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 403)

    def test_staff_with_create_can_create(self):
        staff = add_member(
            self.hotel, "s4@x.com", perms=["reservations.view", "reservations.create"]
        )
        self.client.force_authenticate(staff)
        res = self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype),
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201)

    def test_staff_confirm_cancel_permissions(self):
        creator = add_member(
            self.hotel, "c@x.com", perms=["reservations.create"]
        )
        self.client.force_authenticate(creator)
        r = self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype, status="held", hold_expires_at=_future()),
            format="json",
            **HDR(self.hotel),
        )
        rid = r.data["id"]

        viewer = add_member(self.hotel, "v@x.com", perms=["reservations.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(
            self.client.post(
                reverse("reservations:reservation-confirm", args=[rid]),
                {},
                format="json",
                **HDR(self.hotel),
            ).status_code,
            403,
        )

        confirmer = add_member(self.hotel, "cf@x.com", perms=["reservations.confirm"])
        self.client.force_authenticate(confirmer)
        self.assertEqual(
            self.client.post(
                reverse("reservations:reservation-confirm", args=[rid]),
                {},
                format="json",
                **HDR(self.hotel),
            ).status_code,
            200,
        )

    def test_availability_permission(self):
        staff = add_member(self.hotel, "av@x.com", perms=["availability.view"])
        self.client.force_authenticate(staff)
        res = self.client.get(
            reverse("reservations:availability"),
            {"check_in_date": D1, "check_out_date": D2},
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)

    def test_availability_denied_without_permission(self):
        staff = add_member(self.hotel, "av2@x.com", perms=["reservations.view"])
        self.client.force_authenticate(staff)
        res = self.client.get(
            reverse("reservations:availability"),
            {"check_in_date": D1, "check_out_date": D2},
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 403)

    def test_suspended_hotel_read_only(self):
        self.client.force_authenticate(self.manager)
        # A reservation to cancel later.
        r = self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype),
            format="json",
            **HDR(self.hotel),
        )
        rid = r.data["id"]
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        # View still allowed.
        self.assertEqual(
            self.client.get(
                reverse("reservations:reservation-list"), **HDR(self.hotel)
            ).status_code,
            200,
        )
        # Writes blocked.
        create = self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype, lines=[{"room_type": self.rtype.id, "quantity": 1}]),
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(create.status_code, 403)
        self.assertEqual(create.data["code"], "hotel_suspended")
        cancel = self.client.post(
            reverse("reservations:reservation-cancel", args=[rid]),
            {"reason": "x"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(cancel.status_code, 403)


# --------------------------------------------------------------------------- #
# Availability engine (unit + API)                                             #
# --------------------------------------------------------------------------- #


def _future(minutes=60):
    return (timezone.now() + timedelta(minutes=minutes)).isoformat()


class AvailabilityTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.rtype = make_type(self.hotel, max_capacity=3)
        self.rooms = make_rooms(self.hotel, self.rtype, 3)  # 3 bookable rooms

    def _avail(self, **over):
        return AvailabilityService.availability_for_type(
            self.hotel, self.rtype, over.get("ci", D1), over.get("co", D2)
        )

    def test_empty_inventory_all_available(self):
        a = self._avail()
        self.assertEqual(a.total_rooms, 3)
        self.assertEqual(a.available_quantity, 3)
        self.assertTrue(a.can_book)

    def test_excludes_inactive_rooms(self):
        self.rooms[0].is_active = False
        self.rooms[0].save()
        self.assertEqual(self._avail().available_quantity, 2)

    def test_excludes_inactive_floor(self):
        floor = self.rooms[0].floor
        floor.is_active = False
        floor.save()
        self.assertEqual(self._avail().available_quantity, 0)

    def test_excludes_inactive_room_type(self):
        self.rtype.is_active = False
        self.rtype.save()
        a = self._avail()
        self.assertEqual(a.available_quantity, 0)
        self.assertEqual(a.blocked_rooms, 3)

    def test_excludes_maintenance_and_oos_and_archived(self):
        self.rooms[0].status = RoomStatus.MAINTENANCE
        self.rooms[0].save()
        self.rooms[1].status = RoomStatus.OUT_OF_SERVICE
        self.rooms[1].save()
        self.assertEqual(self._avail().available_quantity, 1)

    def test_includes_dirty_and_cleaning(self):
        self.rooms[0].status = RoomStatus.DIRTY
        self.rooms[0].save()
        self.rooms[1].status = RoomStatus.CLEANING
        self.rooms[1].save()
        self.assertEqual(self._avail().available_quantity, 3)

    def _book(self, status=ReservationStatus.CONFIRMED, qty=1, ci=D1, co=D2, hold=None):
        r = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number=f"R{Reservation.objects.count()+1:05d}",
            status=status,
            check_in_date=ci,
            check_out_date=co,
            primary_guest_name="G",
            hold_expires_at=hold,
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel, reservation=r, room_type=self.rtype, quantity=qty
        )
        return r

    def test_confirmed_reduces_availability(self):
        self._book(qty=2)
        self.assertEqual(self._avail().available_quantity, 1)

    def test_active_held_reduces_availability(self):
        self._book(status=ReservationStatus.HELD, qty=1, hold=timezone.now() + timedelta(hours=1))
        self.assertEqual(self._avail().available_quantity, 2)

    def test_expired_held_does_not_reduce(self):
        self._book(status=ReservationStatus.HELD, qty=2, hold=timezone.now() - timedelta(hours=1))
        self.assertEqual(self._avail().available_quantity, 3)

    def test_cancelled_does_not_reduce(self):
        self._book(status=ReservationStatus.CANCELLED, qty=2)
        self.assertEqual(self._avail().available_quantity, 3)

    def test_expired_status_does_not_reduce(self):
        self._book(status=ReservationStatus.EXPIRED, qty=2)
        self.assertEqual(self._avail().available_quantity, 3)

    def test_back_to_back_allowed(self):
        # Existing stay D1..D2; a new stay starting D2 does not overlap.
        self._book(qty=3, ci=D1, co=D2)
        after = AvailabilityService.availability_for_type(
            self.hotel, self.rtype, D2, D3
        )
        self.assertEqual(after.available_quantity, 3)

    def test_overlapping_reduces(self):
        self._book(qty=3, ci=D1, co=D3)
        mid = AvailabilityService.availability_for_type(
            self.hotel, self.rtype, D2, D3
        )
        self.assertEqual(mid.available_quantity, 0)

    def test_multi_quantity(self):
        self._book(qty=2)
        a = AvailabilityService.availability_for_type(
            self.hotel, self.rtype, D1, D2, requested_quantity=2
        )
        self.assertEqual(a.available_quantity, 1)
        self.assertFalse(a.can_book)

    def test_reserved_quantity_excludes_self(self):
        r = self._book(qty=3)
        reserved = AvailabilityService.reserved_quantity(
            self.hotel, self.rtype, D1, D2, exclude_reservation_id=r.id
        )
        self.assertEqual(reserved, 0)

    def test_availability_api(self):
        mgr = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        res = self.client.get(
            reverse("reservations:availability"),
            {"check_in_date": D1, "check_out_date": D2},
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        row = res.data["results"][0]
        self.assertEqual(row["available_quantity"], 3)
        self.assertTrue(row["can_book"])

    def test_availability_rejects_bad_dates(self):
        mgr = add_member(self.hotel, "m2@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        res = self.client.get(
            reverse("reservations:availability"),
            {"check_in_date": D2, "check_out_date": D1},
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 400)

    def test_calendar_api(self):
        mgr = add_member(self.hotel, "m3@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        res = self.client.get(
            reverse("reservations:availability-calendar"),
            {"check_in_date": D1, "check_out_date": D3},
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["days"]), 4)


# --------------------------------------------------------------------------- #
# Reservation lifecycle                                                        #
# --------------------------------------------------------------------------- #


class ReservationTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel, max_capacity=3)
        make_rooms(self.hotel, self.rtype, 2)

    def _create(self, **over):
        return self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype, **over),
            format="json",
            **HDR(self.hotel),
        )

    def test_create_confirmed(self):
        res = self._create()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "confirmed")
        self.assertEqual(res.data["nights"], 2)
        self.assertTrue(res.data["reservation_number"].startswith("R"))
        self.assertEqual(len(res.data["lines"]), 1)

    def test_create_held_requires_expiry(self):
        res = self._create(status="held")
        self.assertEqual(res.status_code, 400)
        ok = self._create(status="held", hold_expires_at=_future())
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(ok.data["status"], "held")

    def test_reservation_number_unique_and_independent_per_hotel(self):
        r1 = self._create()
        self.assertEqual(r1.data["reservation_number"], "R00001")
        r2 = self._create(lines=[{"room_type": self.rtype.id, "quantity": 1}])
        self.assertEqual(r2.data["reservation_number"], "R00002")
        # Another hotel starts its own sequence.
        other = make_hotel(slug="o")
        ot = make_type(other)
        make_rooms(other, ot, 1)
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(om)
        ro = self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(ot),
            format="json",
            **HDR(other),
        )
        self.assertEqual(ro.data["reservation_number"], "R00001")

    def test_multiple_lines(self):
        t2 = make_type(self.hotel, code="DLX", name="Deluxe", max_capacity=4)
        make_rooms(self.hotel, t2, 2, start=201)
        res = self._create(
            adults=2,
            lines=[
                {"room_type": self.rtype.id, "quantity": 1},
                {"room_type": t2.id, "quantity": 1},
            ],
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(res.data["lines"]), 2)

    def test_reject_invalid_dates(self):
        res = self._create(check_in_date=D2.isoformat(), check_out_date=D1.isoformat())
        self.assertEqual(res.status_code, 400)

    def test_reject_zero_quantity(self):
        res = self._create(lines=[{"room_type": self.rtype.id, "quantity": 0}])
        self.assertEqual(res.status_code, 400)

    def test_reject_inactive_room_type(self):
        self.rtype.is_active = False
        self.rtype.save()
        res = self._create()
        self.assertEqual(res.status_code, 400)

    def test_reject_room_type_from_other_hotel(self):
        other = make_hotel(slug="o")
        ot = make_type(other)
        res = self._create(lines=[{"room_type": ot.id, "quantity": 1}])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "cross_tenant_reference")

    def test_capacity_validation(self):
        # 1 room of max_capacity 3, but 5 guests requested.
        res = self._create(adults=4, children=1)
        self.assertEqual(res.status_code, 400)

    def test_overbooking_prevented(self):
        # Only 2 rooms exist; book 2, then a 3rd overlapping request fails.
        self.assertEqual(self._create(lines=[{"room_type": self.rtype.id, "quantity": 2}]).status_code, 201)
        res = self._create(lines=[{"room_type": self.rtype.id, "quantity": 1}])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "no_availability")

    def test_back_to_back_not_blocked(self):
        self.assertEqual(self._create(lines=[{"room_type": self.rtype.id, "quantity": 2}]).status_code, 201)
        res = self._create(
            check_in_date=D2.isoformat(),
            check_out_date=D3.isoformat(),
            lines=[{"room_type": self.rtype.id, "quantity": 2}],
        )
        self.assertEqual(res.status_code, 201)

    def test_confirm_held(self):
        r = self._create(status="held", hold_expires_at=_future())
        rid = r.data["id"]
        res = self.client.post(
            reverse("reservations:reservation-confirm", args=[rid]),
            {},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "confirmed")
        self.assertIsNone(res.data["hold_expires_at"])

    def test_cancel_requires_reason(self):
        r = self._create()
        rid = r.data["id"]
        no_reason = self.client.post(
            reverse("reservations:reservation-cancel", args=[rid]),
            {},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(no_reason.status_code, 400)
        ok = self.client.post(
            reverse("reservations:reservation-cancel", args=[rid]),
            {"reason": "Guest cancelled"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["status"], "cancelled")
        self.assertEqual(ok.data["cancellation_reason"], "Guest cancelled")

    def test_cancel_releases_inventory(self):
        r = self._create(lines=[{"room_type": self.rtype.id, "quantity": 2}])
        rid = r.data["id"]
        # Fully booked -> a new one fails.
        self.assertEqual(self._create(lines=[{"room_type": self.rtype.id, "quantity": 1}]).status_code, 409)
        self.client.post(
            reverse("reservations:reservation-cancel", args=[rid]),
            {"reason": "x"},
            format="json",
            **HDR(self.hotel),
        )
        # Now it succeeds.
        self.assertEqual(self._create(lines=[{"room_type": self.rtype.id, "quantity": 1}]).status_code, 201)

    def test_cancelled_cannot_be_confirmed(self):
        r = self._create(status="held", hold_expires_at=_future())
        rid = r.data["id"]
        self.client.post(
            reverse("reservations:reservation-cancel", args=[rid]),
            {"reason": "x"},
            format="json",
            **HDR(self.hotel),
        )
        res = self.client.post(
            reverse("reservations:reservation-confirm", args=[rid]),
            {},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 400)

    def test_update_rechecks_availability_excluding_self(self):
        r = self._create(lines=[{"room_type": self.rtype.id, "quantity": 2}])
        rid = r.data["id"]
        # Editing dates on the same reservation must not conflict with itself.
        res = self.client.patch(
            reverse("reservations:reservation-detail", args=[rid]),
            {"check_out_date": D3.isoformat()},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["check_out_date"], D3.isoformat())

    def test_update_blocked_by_other_reservation(self):
        self._create(lines=[{"room_type": self.rtype.id, "quantity": 2}], ci=D1)
        r2 = self._create(
            check_in_date=D2.isoformat(),
            check_out_date=D3.isoformat(),
            lines=[{"room_type": self.rtype.id, "quantity": 2}],
        )
        rid = r2.data["id"]
        # Moving r2 to overlap the first (fully-booked) window must fail.
        res = self.client.patch(
            reverse("reservations:reservation-detail", args=[rid]),
            {"check_in_date": D1.isoformat()},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 409)

    def test_status_logs_created(self):
        r = self._create(status="held", hold_expires_at=_future())
        rid = r.data["id"]
        self.client.post(
            reverse("reservations:reservation-confirm", args=[rid]),
            {},
            format="json",
            **HDR(self.hotel),
        )
        logs = self.client.get(
            reverse("reservations:reservation-logs", args=[rid]), **HDR(self.hotel)
        )
        self.assertEqual(logs.status_code, 200)
        self.assertGreaterEqual(len(logs.data), 2)  # created + confirmed

    def test_no_hard_delete(self):
        r = self._create()
        rid = r.data["id"]
        res = self.client.delete(
            reverse("reservations:reservation-detail", args=[rid]), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 405)
        self.assertTrue(Reservation.objects.filter(pk=rid).exists())

    def test_overview(self):
        self._create()
        self._create(status="held", hold_expires_at=_future(), lines=[{"room_type": self.rtype.id, "quantity": 1}])
        res = self.client.get(
            reverse("reservations:reservation-overview"), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total"], 2)
        self.assertEqual(res.data["confirmed"], 1)
        self.assertEqual(res.data["held"], 1)

    def test_list_filters(self):
        self._create()
        r2 = self._create(status="held", hold_expires_at=_future(), lines=[{"room_type": self.rtype.id, "quantity": 1}])
        base = reverse("reservations:reservation-list")
        self.assertEqual(
            self.client.get(base, {"status": "held"}, **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(
                base, {"search": r2.data["reservation_number"]}, **HDR(self.hotel)
            ).data["count"],
            1,
        )

    def test_isolation_other_hotel_cannot_read(self):
        r = self._create()
        rid = r.data["id"]
        other = make_hotel(slug="o")
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(om)
        res = self.client.get(
            reverse("reservations:reservation-detail", args=[rid]), **HDR(other)
        )
        self.assertEqual(res.status_code, 404)


# --------------------------------------------------------------------------- #
# Regression                                                                   #
# --------------------------------------------------------------------------- #


class RegressionTests(APITestCase):
    def test_health_still_works(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)

    def test_rooms_api_still_works(self):
        hotel = make_hotel()
        mgr = add_member(hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(hotel)).status_code, 200
        )

    def test_hotel_settings_still_works(self):
        hotel = make_hotel()
        mgr = add_member(hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        self.assertEqual(
            self.client.get(reverse("hotel:settings"), **HDR(hotel)).status_code, 200
        )

    def test_no_guest_money_or_checkin_models(self):
        from django.apps import apps as django_apps

        tables = {m._meta.db_table for m in django_apps.get_models()}
        for forbidden in ("guests", "payments", "invoices", "folios", "expenses"):
            self.assertNotIn(forbidden, tables)

    def test_no_checkin_checkout_endpoints(self):
        from django.urls import NoReverseMatch

        for name in ("reservations:reservation-check-in", "reservations:reservation-check-out"):
            try:
                reverse(name, args=[1])
                self.fail(f"{name} should not exist in Phase 6")
            except NoReverseMatch:
                pass
