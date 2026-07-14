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
from apps.guests.models import Guest
from apps.rbac.services import grant_permission
from apps.reservations.availability import AvailabilityService
from apps.reservations.models import (
    Reservation,
    ReservationDocument,
    ReservationRoomLine,
    ReservationSource,
    ReservationStatus,
)
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.stays.models import Stay, StayStatus
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

    def test_overview_website_source_count(self):
        """`website` counts public-website reservations across ALL statuses,
        strictly hotel-scoped (a second hotel's website bookings are excluded)."""

        def _mk(hotel, source, status):
            return Reservation.objects.create(
                hotel=hotel,
                reservation_number=f"R{Reservation.objects.count() + 1:05d}",
                status=status,
                source=source,
                check_in_date=D1,
                check_out_date=D2,
                primary_guest_name="G",
                hold_expires_at=(
                    _future() if status == ReservationStatus.HELD else None
                ),
            )

        # Hotel A: 3 public-website reservations spanning different statuses
        # (proves the count ignores status filters) + 1 non-website booking.
        _mk(self.hotel, ReservationSource.PUBLIC_WEBSITE, ReservationStatus.CONFIRMED)
        _mk(self.hotel, ReservationSource.PUBLIC_WEBSITE, ReservationStatus.HELD)
        _mk(self.hotel, ReservationSource.PUBLIC_WEBSITE, ReservationStatus.CANCELLED)
        _mk(self.hotel, ReservationSource.DIRECT, ReservationStatus.CONFIRMED)

        # Hotel B: a public-website reservation that must NOT leak into hotel A.
        other = make_hotel(slug="other-web")
        _mk(other, ReservationSource.PUBLIC_WEBSITE, ReservationStatus.CONFIRMED)

        res = self.client.get(
            reverse("reservations:reservation-overview"), **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 200)
        # 3 website reservations in hotel A, regardless of status; hotel B excluded.
        self.assertEqual(res.data["website"], 3)
        # Purely additive: existing counts still reflect every hotel-A row.
        self.assertEqual(res.data["total"], 4)
        self.assertEqual(res.data["confirmed"], 2)

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

    def test_no_out_of_scope_models(self):
        # Finance arrives in Phase 8; restaurant/stock/daily-close/shifts do not.
        from django.apps import apps as django_apps

        tables = {m._meta.db_table for m in django_apps.get_models()}
        # (shifts/daily_closes became legitimate in Phase 12.)
        for forbidden in ("restaurant_orders", "stock_items", "payroll", "attendance_records"):
            self.assertNotIn(forbidden, tables)

    def test_no_checkin_checkout_endpoints(self):
        from django.urls import NoReverseMatch

        for name in ("reservations:reservation-check-in", "reservations:reservation-check-out"):
            try:
                reverse(name, args=[1])
                self.fail(f"{name} should not exist in Phase 6")
            except NoReverseMatch:
                pass


# --------------------------------------------------------------------------- #
# Phase 6.1 — Minimal room assignment                                         #
# --------------------------------------------------------------------------- #


class RoomAssignmentTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel, max_capacity=3)
        self.rooms = make_rooms(self.hotel, self.rtype, 2)  # rooms 101, 102

    def _create(self, **over):
        return self.client.post(
            reverse("reservations:reservation-list"),
            res_payload(self.rtype, **over),
            format="json",
            **HDR(self.hotel),
        )

    def _assigned_line(self, room, **extra):
        return {"room_type": self.rtype.id, "room": room.id, "quantity": 1, **extra}

    def test_assign_room_success(self):
        res = self._create(lines=[self._assigned_line(self.rooms[0])])
        self.assertEqual(res.status_code, 201)
        line = res.data["lines"][0]
        self.assertEqual(line["room"], self.rooms[0].id)
        self.assertEqual(line["room_number"], self.rooms[0].number)

    def test_room_must_match_room_type(self):
        other_type = make_type(self.hotel, code="DLX", name="Deluxe")
        other_room = make_rooms(self.hotel, other_type, 1, start=301)[0]
        res = self._create(lines=[self._assigned_line(other_room)])
        self.assertEqual(res.status_code, 400)

    def test_room_from_other_hotel_rejected(self):
        other = make_hotel(slug="o")
        ot = make_type(other)
        oroom = make_rooms(other, ot, 1)[0]
        res = self._create(lines=[{"room_type": self.rtype.id, "room": oroom.id, "quantity": 1}])
        self.assertEqual(res.status_code, 400)

    def test_inactive_room_not_assignable(self):
        self.rooms[0].is_active = False
        self.rooms[0].save()
        res = self._create(lines=[self._assigned_line(self.rooms[0])])
        self.assertEqual(res.status_code, 400)

    def test_maintenance_room_not_assignable(self):
        self.rooms[0].status = RoomStatus.MAINTENANCE
        self.rooms[0].save()
        res = self._create(lines=[self._assigned_line(self.rooms[0])])
        self.assertEqual(res.status_code, 400)

    def test_out_of_service_and_archived_not_assignable(self):
        for st in (RoomStatus.OUT_OF_SERVICE, RoomStatus.ARCHIVED):
            self.rooms[0].status = st
            self.rooms[0].save()
            res = self._create(lines=[self._assigned_line(self.rooms[0])])
            self.assertEqual(res.status_code, 400, st)

    def test_assigned_room_requires_quantity_one(self):
        res = self._create(lines=[{"room_type": self.rtype.id, "room": self.rooms[0].id, "quantity": 2}])
        self.assertEqual(res.status_code, 400)

    def test_same_room_overlap_blocked(self):
        self.assertEqual(self._create(lines=[self._assigned_line(self.rooms[0])]).status_code, 201)
        res = self._create(lines=[self._assigned_line(self.rooms[0])])
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "room_assignment_conflict")

    def test_back_to_back_same_room_allowed(self):
        self.assertEqual(self._create(lines=[self._assigned_line(self.rooms[0])]).status_code, 201)
        res = self._create(
            check_in_date=D2.isoformat(),
            check_out_date=D3.isoformat(),
            lines=[self._assigned_line(self.rooms[0])],
        )
        self.assertEqual(res.status_code, 201)

    def test_duplicate_same_room_in_request_rejected(self):
        res = self._create(
            lines=[self._assigned_line(self.rooms[0]), self._assigned_line(self.rooms[0])]
        )
        self.assertEqual(res.status_code, 409)

    def test_assigned_room_reduces_availability(self):
        self._create(lines=[self._assigned_line(self.rooms[0])])
        a = AvailabilityService.availability_for_type(self.hotel, self.rtype, D1, D2)
        self.assertEqual(a.reserved_quantity, 1)
        self.assertEqual(a.available_quantity, 1)

    def test_mixed_assigned_and_unassigned_availability(self):
        # 2 rooms: assign room 101 + 1 unassigned -> both consumed; a 3rd fails.
        res = self._create(
            lines=[
                self._assigned_line(self.rooms[0]),
                {"room_type": self.rtype.id, "quantity": 1},
            ],
        )
        self.assertEqual(res.status_code, 201)
        a = AvailabilityService.availability_for_type(self.hotel, self.rtype, D1, D2)
        self.assertEqual(a.available_quantity, 0)
        # Another overlapping request (assigned or unassigned) must fail.
        self.assertEqual(self._create(lines=[self._assigned_line(self.rooms[1])]).status_code, 409)
        self.assertEqual(self._create(lines=[{"room_type": self.rtype.id, "quantity": 1}]).status_code, 409)

    def test_cancel_frees_assigned_room(self):
        r = self._create(lines=[self._assigned_line(self.rooms[0])])
        rid = r.data["id"]
        # Same room overlapping now blocked.
        self.assertEqual(self._create(lines=[self._assigned_line(self.rooms[0])]).status_code, 409)
        self.client.post(
            reverse("reservations:reservation-cancel", args=[rid]),
            {"reason": "x"}, format="json", **HDR(self.hotel),
        )
        # After cancel, the room is free again.
        self.assertEqual(self._create(lines=[self._assigned_line(self.rooms[0])]).status_code, 201)

    def test_staff_needs_assign_room_permission(self):
        staff = add_member(self.hotel, "s@x.com", perms=["reservations.view", "reservations.create"])
        self.client.force_authenticate(staff)
        res = self._create(lines=[self._assigned_line(self.rooms[0])])
        self.assertEqual(res.status_code, 403)

    def test_staff_with_assign_room_permission_can_assign(self):
        staff = add_member(
            self.hotel, "s2@x.com",
            perms=["reservations.view", "reservations.create", "reservations.assign_room"],
        )
        self.client.force_authenticate(staff)
        res = self._create(lines=[self._assigned_line(self.rooms[0])])
        self.assertEqual(res.status_code, 201)

    def test_unassigned_booking_still_works(self):
        # Phase 6 behaviour is unchanged when no room is assigned.
        res = self._create(lines=[{"room_type": self.rtype.id, "quantity": 2}])
        self.assertEqual(res.status_code, 201)


# --- List view filters (reservations section reorg) ---------------------------


class ListViewFilterTests(APITestCase):
    """READ-ONLY list filters: source, statuses CSV, created_today,
    upcoming (business-date aware), room, and room-number search."""

    def setUp(self):
        from apps.shifts.services import get_business_date

        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)
        self.rooms = make_rooms(self.hotel, self.rtype, 2)
        self.today = get_business_date(self.hotel)

        def res(number, *, status, source="direct", check_in=None, room=None):
            r = Reservation.objects.create(
                hotel=self.hotel,
                reservation_number=number,
                status=status,
                source=source,
                check_in_date=check_in or D1,
                check_out_date=(check_in or D1) + timedelta(days=2),
                primary_guest_name=f"Guest {number}",
            )
            ReservationRoomLine.objects.create(
                hotel=self.hotel,
                reservation=r,
                room_type=self.rtype,
                room=room,
                quantity=1,
            )
            return r

        self.r_site = res("R-SITE", status="held", source="public_website")
        self.r_confirmed = res(
            "R-CONF", status="confirmed", room=self.rooms[0]
        )
        self.r_cancelled = res("R-CAN", status="cancelled")
        self.r_expired = res("R-EXP", status="expired")
        # Arrival ON the business date — NOT "upcoming" (strictly after).
        self.r_today_arrival = res(
            "R-TODAY", status="confirmed", check_in=self.today
        )

    def _numbers(self, query=""):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(
            reverse("reservations:reservation-list") + query, **HDR(self.hotel)
        )
        self.assertEqual(resp.status_code, 200)
        return {row["reservation_number"] for row in resp.data["results"]}

    def test_source_filter(self):
        self.assertEqual(self._numbers("?source=public_website"), {"R-SITE"})

    def test_statuses_csv_filter(self):
        self.assertEqual(
            self._numbers("?statuses=cancelled,expired"), {"R-CAN", "R-EXP"}
        )

    def test_statuses_ignores_invalid_values(self):
        # Bogus entries are dropped; valid ones still apply.
        self.assertEqual(
            self._numbers("?statuses=bogus,cancelled"), {"R-CAN"}
        )

    def test_created_today_matches_fresh_rows(self):
        # Everything above was created "now" — all rows are in today's window.
        self.assertEqual(len(self._numbers("?created_today=true")), 5)

    def test_upcoming_is_strictly_after_business_date(self):
        numbers = self._numbers("?upcoming=true")
        self.assertIn("R-SITE", numbers)  # far-future D1
        self.assertNotIn("R-TODAY", numbers)  # arrives ON the business date

    def test_room_filter_and_room_number_search(self):
        room_id = self.rooms[0].id
        self.assertEqual(self._numbers(f"?room={room_id}"), {"R-CONF"})
        self.assertEqual(
            self._numbers(f"?search={self.rooms[0].number}"), {"R-CONF"}
        )


class OverviewBusinessDateTests(APITestCase):
    """The overview exposes the hotel business date (immediate-wizard input)."""

    def test_overview_returns_business_date(self):
        from apps.shifts.services import get_business_date

        hotel = make_hotel()
        manager = add_member(hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(manager)
        resp = self.client.get(
            reverse("reservations:reservation-overview"), **HDR(hotel)
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["business_date"], str(get_business_date(hotel)))


# --- Final closure round -------------------------------------------------- #


class PostCheckInGuardTests(APITestCase):
    """With an in-house stay the STAY is the source of truth: reservation
    dates/rooms are frozen and cancel is refused (clear domain error)."""

    def setUp(self):
        from django.utils import timezone as dj_tz

        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)
        self.rooms = make_rooms(self.hotel, self.rtype, 2)
        self.res = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-INH",
            status=ReservationStatus.CONFIRMED,
            booking_kind="future",
            check_in_date=D1,
            check_out_date=D2,
            primary_guest_name="In House",
        )
        self.line = ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=self.res,
            room_type=self.rtype,
            room=self.rooms[0],
            quantity=1,
        )
        guest = Guest.objects.create(hotel=self.hotel, full_name="In House")
        self.stay = Stay.objects.create(
            hotel=self.hotel,
            reservation=self.res,
            reservation_line=self.line,
            room=self.rooms[0],
            primary_guest=guest,
            planned_check_in_date=D1,
            planned_check_out_date=D2,
            actual_check_in_at=dj_tz.now(),
        )
        self.client.force_authenticate(self.manager)

    def _patch(self, body):
        return self.client.patch(
            reverse("reservations:reservation-detail", args=[self.res.id]),
            body,
            format="json",
            **HDR(self.hotel),
        )

    def test_date_edit_refused_with_clear_code(self):
        resp = self._patch({"check_out_date": D3.isoformat()})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "reservation_has_active_stay")

    def test_room_line_edit_refused(self):
        resp = self._patch(
            {"lines": [{"room_type": self.rtype.id, "room": self.rooms[1].id, "quantity": 1}]}
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "reservation_has_active_stay")

    def test_cancel_refused(self):
        resp = self.client.post(
            reverse("reservations:reservation-cancel", args=[self.res.id]),
            {"reason": "should not work"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "reservation_has_active_stay")
        self.res.refresh_from_db()
        self.assertEqual(self.res.status, ReservationStatus.CONFIRMED)

    def test_safe_fields_still_editable(self):
        resp = self._patch({"notes": "late arrival", "special_requests": "quiet room"})
        self.assertEqual(resp.status_code, 200)
        self.res.refresh_from_db()
        self.assertEqual(self.res.notes, "late arrival")

    def test_stay_untouched_by_guard(self):
        self._patch({"check_out_date": D3.isoformat()})
        self.stay.refresh_from_db()
        self.assertEqual(self.stay.planned_check_out_date, D2)
        self.assertEqual(self.stay.room_id, self.rooms[0].id)

    def test_edit_still_free_before_check_in(self):
        other = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-FREE",
            status=ReservationStatus.CONFIRMED,
            booking_kind="future",
            check_in_date=D2,
            check_out_date=D3,
            primary_guest_name="Free",
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=other,
            room_type=self.rtype,
            quantity=1,
        )
        resp = self.client.patch(
            reverse("reservations:reservation-detail", args=[other.id]),
            {"check_out_date": (D3 + timedelta(days=1)).isoformat()},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200)

    def test_serializer_exposes_in_house_flag(self):
        resp = self.client.get(
            reverse("reservations:reservation-detail", args=[self.res.id]),
            **HDR(self.hotel),
        )
        self.assertTrue(resp.data["has_in_house_stay"])


class PublicCancelVisibilityTests(APITestCase):
    """A public cancel request records an internal activity and is
    filterable in the reservations list while still pending."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.rtype = make_type(self.hotel)
        make_rooms(self.hotel, self.rtype, 1)
        self.res = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-PUB",
            status=ReservationStatus.HELD,
            booking_kind="future",
            source="public_website",
            check_in_date=D1,
            check_out_date=D2,
            primary_guest_name="Site Guest",
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel, reservation=self.res, room_type=self.rtype, quantity=1
        )

    def test_request_records_internal_activity_only(self):
        from apps.notifications.models import ActivityEvent
        from apps.public_site.services import request_public_cancellation

        request_public_cancellation(self.res, reason="plans changed")
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="reservation.public_cancel_requested"
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("R-PUB", event.title)
        self.assertIn("Site Guest", event.message)
        # Idempotent: a second request does not duplicate the activity.
        request_public_cancellation(self.res, reason="again")
        self.assertEqual(
            ActivityEvent.objects.filter(
                hotel=self.hotel,
                event_type="reservation.public_cancel_requested",
            ).count(),
            1,
        )

    def test_pending_filter_and_clearing_after_processing(self):
        from apps.public_site.services import request_public_cancellation
        from apps.reservations.services import cancel_reservation

        request_public_cancellation(self.res, reason="plans changed")
        self.client.force_authenticate(self.manager)
        url = reverse("reservations:reservation-list") + "?cancel_requested=true"
        numbers = {
            r["reservation_number"]
            for r in self.client.get(url, **HDR(self.hotel)).data["results"]
        }
        self.assertEqual(numbers, {"R-PUB"})
        # Accepting the request (cancelling) clears it from the pending view.
        cancel_reservation(self.res, reason="guest asked via website", user=self.manager)
        numbers = {
            r["reservation_number"]
            for r in self.client.get(url, **HDR(self.hotel)).data["results"]
        }
        self.assertEqual(numbers, set())


# --- Reservations UI rework: additive read-only display fields ------------- #


class DisplayFieldTests(APITestCase):
    """Purely additive read fields for the reworked reservations UI:
    ``created_by_name`` on the reservation, and ``floor_name``/``floor_number``
    on each room line (sourced from the SPECIFIC assigned room's floor)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel, max_capacity=3)
        # A floor with an explicit name AND number, to prove both are surfaced.
        self.floor = Floor.objects.create(
            hotel=self.hotel, name="First Floor", number="1"
        )
        self.rooms = make_rooms(self.hotel, self.rtype, 1, floor=self.floor)

    def _res(self, *, created_by, number="R-DISP"):
        return Reservation.objects.create(
            hotel=self.hotel,
            reservation_number=number,
            status=ReservationStatus.CONFIRMED,
            check_in_date=D1,
            check_out_date=D2,
            primary_guest_name="Guest",
            created_by=created_by,
        )

    def _detail(self, res):
        resp = self.client.get(
            reverse("reservations:reservation-detail", args=[res.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data

    def test_created_by_name_uses_full_name(self):
        # add_member sets full_name="Member".
        data = self._detail(self._res(created_by=self.manager))
        self.assertEqual(data["created_by_name"], "Member")
        # The existing email field is unchanged (purely additive).
        self.assertEqual(data["created_by"], self.manager.email)

    def test_created_by_name_falls_back_to_email(self):
        no_name = User.objects.create_user(
            email="noname@x.com", password="StrongPass!234", full_name=""
        )
        data = self._detail(self._res(created_by=no_name, number="R-NONAME"))
        self.assertEqual(data["created_by_name"], "noname@x.com")

    def test_created_by_name_null_without_creator(self):
        data = self._detail(self._res(created_by=None, number="R-NOCREATOR"))
        self.assertIsNone(data["created_by_name"])

    def test_line_floor_fields_from_assigned_room_and_null_when_unassigned(self):
        res = self._res(created_by=self.manager)
        ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=res,
            room_type=self.rtype,
            room=self.rooms[0],
            quantity=1,
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=res,
            room_type=self.rtype,
            room=None,
            quantity=1,
        )
        lines = {line["room"]: line for line in self._detail(res)["lines"]}

        assigned = lines[self.rooms[0].id]
        self.assertEqual(assigned["floor_name"], "First Floor")
        self.assertEqual(assigned["floor_number"], "1")

        unassigned = lines[None]
        self.assertIsNone(unassigned["floor_name"])
        self.assertIsNone(unassigned["floor_number"])


# --------------------------------------------------------------------------- #
# RESERVATIONS-FORM-UX-CORRECTION — deposit / financial summary / derived      #
# read fields / sensitive masking (§26/§27/§31/§33/§37/§45)                    #
# --------------------------------------------------------------------------- #


def make_stay(hotel, reservation, line, room, *, status=StayStatus.IN_HOUSE):
    """Create a Stay off a reservation for the guard/derived-field tests.

    A CHECKED_OUT stay leaves the reservation CONFIRMED (departed guest) and is
    exactly the Finance-F1 case: the booking has a stay yet is not in-house.
    """
    guest = Guest.objects.create(hotel=hotel, full_name="Stay Guest")
    now = timezone.now()
    return Stay.objects.create(
        hotel=hotel,
        reservation=reservation,
        reservation_line=line,
        room=room,
        primary_guest=guest,
        status=status,
        planned_check_in_date=reservation.check_in_date,
        planned_check_out_date=reservation.check_out_date,
        actual_check_in_at=now,
        actual_check_out_at=(now if status == StayStatus.CHECKED_OUT else None),
    )


class ReservationDepositTests(APITestCase):
    """§27 pre-arrival DEPOSIT endpoint + Finance-F1 any-stay guard.

    A deposit is a PRE-arrival concept: it records money on the reservation's ONE
    folio (reused at check-in, single ledger) and is refused once ANY stay exists
    — in-house OR already checked-out.
    """

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "mgr@x.com", kind=MembershipType.MANAGER
        )
        # base_rate 100 × 2 nights (D1→D2) = 200 → priced reservation.
        self.rtype = make_type(self.hotel, max_capacity=3, base_rate="100.00")
        self.rooms = make_rooms(self.hotel, self.rtype, 2)
        self.res, self.line = self._reservation()

    def _reservation(self, *, number="R-DEP", status=ReservationStatus.CONFIRMED):
        res = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number=number,
            status=status,
            booking_kind="future",
            check_in_date=D1,
            check_out_date=D2,
            primary_guest_name="Deposit Guest",
        )
        line = ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=res,
            room_type=self.rtype,
            room=self.rooms[0],
            quantity=1,
        )
        return res, line

    def _deposit(self, res, body, *, user=None):
        self.client.force_authenticate(user or self.manager)
        return self.client.post(
            reverse("reservations:reservation-payments", args=[res.id]),
            body,
            format="json",
            **HDR(self.hotel),
        )

    def test_deposit_success_records_payment_on_reservation_folio(self):
        resp = self._deposit(self.res, {"amount": "50.00", "method": "cash"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["payment"]["amount"], "50.00")
        fin = resp.data["financial_summary"]
        self.assertEqual(fin["reservation_total"], "200.00")
        self.assertEqual(fin["paid"], "50.00")
        self.assertEqual(fin["remaining"], "150.00")
        self.assertEqual(fin["currency"], "USD")
        # ONE pre-arrival folio (stay-null) holds the deposit — no duplicate ledger.
        self.assertEqual(self.res.folios.count(), 1)
        self.assertIsNone(self.res.folios.get().stay_id)

    def test_deposit_folio_is_reused_at_check_in_no_duplicate(self):
        from apps.finance.services import ensure_stay_folio

        self.assertEqual(
            self._deposit(self.res, {"amount": "40.00", "method": "cash"}).status_code,
            201,
        )
        self.assertEqual(self.res.folios.count(), 1)
        pre_folio = self.res.folios.get()
        self.assertIsNone(pre_folio.stay_id)
        # Checking in reuses that same folio instead of opening a second ledger.
        guest = Guest.objects.create(hotel=self.hotel, full_name="Deposit Guest")
        stay = Stay.objects.create(
            hotel=self.hotel,
            reservation=self.res,
            reservation_line=self.line,
            room=self.rooms[0],
            primary_guest=guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=D1,
            planned_check_out_date=D2,
            actual_check_in_at=timezone.now(),
        )
        reused = ensure_stay_folio(stay)
        self.assertEqual(reused.id, pre_folio.id)
        self.assertEqual(self.res.folios.count(), 1)  # still ONE folio
        reused.refresh_from_db()
        self.assertEqual(reused.stay_id, stay.id)

    def test_deposit_rejects_non_positive_amount(self):
        resp = self._deposit(self.res, {"amount": "0", "method": "cash"})
        self.assertEqual(resp.status_code, 400)

    def test_deposit_rejected_when_reservation_has_in_house_stay(self):
        make_stay(self.hotel, self.res, self.line, self.rooms[0],
                  status=StayStatus.IN_HOUSE)
        resp = self._deposit(self.res, {"amount": "50.00", "method": "cash"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "reservation_has_active_stay")

    def test_deposit_rejected_when_reservation_has_checked_out_stay(self):
        # Finance-F1: a departed guest's reservation is still CONFIRMED but must
        # NOT accept a new pre-arrival deposit (would orphan an open folio).
        make_stay(self.hotel, self.res, self.line, self.rooms[0],
                  status=StayStatus.CHECKED_OUT)
        resp = self._deposit(self.res, {"amount": "50.00", "method": "cash"})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "reservation_has_active_stay")

    def test_deposit_requires_payment_create_permission(self):
        # reservations.view alone is never enough to record money (§42).
        viewer = add_member(self.hotel, "dep-view@x.com", perms=["reservations.view"])
        denied = self._deposit(
            self.res, {"amount": "10.00", "method": "cash"}, user=viewer
        )
        self.assertEqual(denied.status_code, 403)
        payer = add_member(
            self.hotel, "dep-pay@x.com", perms=["finance.payment_create"]
        )
        ok = self._deposit(
            self.res, {"amount": "10.00", "method": "cash"}, user=payer
        )
        self.assertEqual(ok.status_code, 201)

    def test_foreign_manual_rate_requires_exchange_rate_override(self):
        body = {
            "method": "cash",
            "currency": "EUR",
            "original_amount": "20.00",
            "exchange_rate": "1.10",
            "rate_basis": "base_per_payment",
        }
        payer = add_member(
            self.hotel, "fx@x.com", perms=["finance.payment_create"]
        )
        denied = self._deposit(self.res, body, user=payer)
        self.assertEqual(denied.status_code, 403)
        # Granting exchange_rate.override clears the FX permission gate; the
        # request no longer 403s (it moves past permission to currency handling).
        over = add_member(
            self.hotel,
            "fx2@x.com",
            perms=["finance.payment_create", "exchange_rate.override"],
        )
        granted = self._deposit(self.res, body, user=over)
        self.assertNotEqual(granted.status_code, 403)


class ReservationFinancialSummaryTests(APITestCase):
    """§26/§31/§35 derived financial summary — total = rate×nights, paid = Σ
    posted payments, remaining = total−paid; money gated by ``finance.view`` and
    tenant-scoped."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "mgr@x.com", kind=MembershipType.MANAGER
        )
        self.rtype = make_type(self.hotel, base_rate="100.00")
        self.rooms = make_rooms(self.hotel, self.rtype, 1)
        self.res = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-FIN",
            status=ReservationStatus.CONFIRMED,
            booking_kind="future",
            check_in_date=D1,
            check_out_date=D2,  # 2 nights
            primary_guest_name="Fin Guest",
        )
        self.line = ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=self.res,
            room_type=self.rtype,
            room=self.rooms[0],
            quantity=1,
        )

    def _summary(self, res, user, hotel=None):
        self.client.force_authenticate(user)
        return self.client.get(
            reverse("reservations:reservation-financial-summary", args=[res.id]),
            **HDR(hotel or self.hotel),
        )

    def test_totals_derived_from_rate_and_posted_payments(self):
        from apps.finance.services import record_reservation_payment

        record_reservation_payment(
            self.res, amount="50.00", method="cash", user=self.manager
        )
        resp = self._summary(self.res, self.manager)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["can_view_money"])
        self.assertEqual(resp.data["reservation_total"], "200.00")
        self.assertEqual(resp.data["paid"], "50.00")
        self.assertEqual(resp.data["remaining"], "150.00")
        self.assertEqual(resp.data["currency"], "USD")
        self.assertEqual(resp.data["nights"], 2)

    def test_money_masked_without_finance_view(self):
        staff = add_member(self.hotel, "noview@x.com", perms=["reservations.view"])
        resp = self._summary(self.res, staff)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["can_view_money"])
        self.assertIsNone(resp.data["reservation_total"])
        self.assertIsNone(resp.data["paid"])
        self.assertIsNone(resp.data["remaining"])
        self.assertEqual(resp.data["payments"], [])
        # Non-sensitive shape still present.
        self.assertEqual(resp.data["currency"], "USD")
        self.assertEqual(resp.data["nights"], 2)

    def test_summary_is_tenant_scoped(self):
        other = make_hotel(slug="other-fin")
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        resp = self._summary(self.res, om, hotel=other)
        self.assertEqual(resp.status_code, 404)


class DerivedStayAndDocumentFieldTests(APITestCase):
    """§25/§37 derived read fields on the reservation serializer:
    ``stay_status`` (latest stay's status, or null) and ``document_count`` (a
    non-sensitive count computed from the prefetched ``documents`` relation)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "mgr@x.com", kind=MembershipType.MANAGER
        )
        self.client.force_authenticate(self.manager)
        self.rtype = make_type(self.hotel)
        self.rooms = make_rooms(self.hotel, self.rtype, 2)

    def _res(self, number):
        res = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number=number,
            status=ReservationStatus.CONFIRMED,
            booking_kind="future",
            check_in_date=D1,
            check_out_date=D2,
            primary_guest_name="Guest",
        )
        line = ReservationRoomLine.objects.create(
            hotel=self.hotel,
            reservation=res,
            room_type=self.rtype,
            room=self.rooms[0],
            quantity=1,
        )
        return res, line

    def _detail(self, res):
        resp = self.client.get(
            reverse("reservations:reservation-detail", args=[res.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data

    def test_stay_status_null_and_zero_documents_by_default(self):
        res, _ = self._res("R-NONE")
        data = self._detail(res)
        self.assertIsNone(data["stay_status"])
        self.assertEqual(data["document_count"], 0)

    def test_stay_status_in_house(self):
        res, line = self._res("R-INH")
        make_stay(self.hotel, res, line, self.rooms[0], status=StayStatus.IN_HOUSE)
        self.assertEqual(self._detail(res)["stay_status"], "in_house")

    def test_stay_status_checked_out(self):
        res, line = self._res("R-OUT")
        make_stay(self.hotel, res, line, self.rooms[0],
                  status=StayStatus.CHECKED_OUT)
        self.assertEqual(self._detail(res)["stay_status"], "checked_out")

    def test_document_count_reflects_documents_on_detail_and_list(self):
        res, _ = self._res("R-DOC")
        ReservationDocument.objects.create(
            hotel=self.hotel, reservation=res, doc_type="passport", number="A1"
        )
        ReservationDocument.objects.create(
            hotel=self.hotel, reservation=res, doc_type="national_id", number="B2"
        )
        self.assertEqual(self._detail(res)["document_count"], 2)
        resp = self.client.get(
            reverse("reservations:reservation-list"), **HDR(self.hotel)
        )
        row = next(
            r for r in resp.data["results"] if r["reservation_number"] == "R-DOC"
        )
        self.assertEqual(row["document_count"], 2)

    def test_document_count_uses_prefetch_no_extra_query(self):
        # Once ``documents`` is prefetched (as the list/detail querysets do),
        # ``len(obj.documents.all())`` — the exact mechanism of the serializer's
        # ``document_count`` — issues ZERO extra queries per reservation (no N+1).
        res, _ = self._res("R-PF")
        for i in range(3):
            ReservationDocument.objects.create(
                hotel=self.hotel, reservation=res, doc_type="other", number=f"N{i}"
            )
        prefetched = list(
            Reservation.objects.filter(hotel=self.hotel).prefetch_related("documents")
        )
        with self.assertNumQueries(0):
            counts = [len(r.documents.all()) for r in prefetched]
        self.assertEqual(counts, [3])


class SensitiveMaskingTests(APITestCase):
    """§36/§39 (sec-F2): the primary guest's father/mother names + DoB are
    sensitive — REDACTED to null (and national ID masked) for callers without
    ``guests.view_sensitive_data`` — masked SERVER-SIDE, not just hidden in UI."""

    def setUp(self):
        self.hotel = make_hotel()
        self.rtype = make_type(self.hotel)
        make_rooms(self.hotel, self.rtype, 1)
        self.res = Reservation.objects.create(
            hotel=self.hotel,
            reservation_number="R-SENS",
            status=ReservationStatus.CONFIRMED,
            booking_kind="future",
            check_in_date=D1,
            check_out_date=D2,
            primary_guest_name="Sensitive Guest",
            primary_guest_father_name="Father Name",
            primary_guest_mother_name="Mother Name",
            primary_guest_national_id="1234567890",
            primary_guest_date_of_birth=date(1990, 5, 1),
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel, reservation=self.res, room_type=self.rtype, quantity=1
        )

    def _detail(self, user):
        self.client.force_authenticate(user)
        resp = self.client.get(
            reverse("reservations:reservation-detail", args=[self.res.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data

    def test_masked_without_view_sensitive_permission(self):
        staff = add_member(self.hotel, "plain@x.com", perms=["reservations.view"])
        data = self._detail(staff)
        self.assertIsNone(data["primary_guest_father_name"])
        self.assertIsNone(data["primary_guest_mother_name"])
        self.assertIsNone(data["primary_guest_date_of_birth"])
        self.assertIn("•", data["primary_guest_national_id"])

    def test_visible_with_view_sensitive_permission(self):
        staff = add_member(
            self.hotel,
            "sens@x.com",
            perms=["reservations.view", "guests.view_sensitive_data"],
        )
        data = self._detail(staff)
        self.assertEqual(data["primary_guest_father_name"], "Father Name")
        self.assertEqual(data["primary_guest_mother_name"], "Mother Name")
        self.assertEqual(data["primary_guest_date_of_birth"], "1990-05-01")
        self.assertEqual(data["primary_guest_national_id"], "1234567890")
