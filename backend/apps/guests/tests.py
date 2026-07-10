"""Tests for guests (Phase 7): access/permissions, CRUD, search, validation,
tenant isolation, and the deactivate-instead-of-delete rule."""
from __future__ import annotations

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.guests.models import Guest
from apps.rbac.services import grant_permission
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731


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


def guest_body(**over):
    body = {"full_name": "Jane Traveler", "phone": "+905551112233"}
    body.update(over)
    return body


class GuestAccessTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(reverse("guests:guest-list"), **HDR(self.hotel)).status_code,
            401,
        )

    def test_cannot_access_other_hotel(self):
        other = make_hotel(slug="o")
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("guests:guest-list"), **HDR(other)).status_code, 403
        )

    def test_platform_owner_not_member_denied(self):
        owner = User.objects.create_platform_owner(
            email="o@x.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(reverse("guests:guest-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_staff_view_permission(self):
        staff = add_member(self.hotel, "s@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("guests:guest-list"), **HDR(self.hotel)).status_code,
            200,
        )

    def test_staff_without_permission_denied(self):
        staff = add_member(self.hotel, "s2@x.com")
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("guests:guest-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_staff_create_needs_permission(self):
        staff = add_member(self.hotel, "s3@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        res = self.client.post(
            reverse("guests:guest-list"), guest_body(), format="json", **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 403)

    def test_suspended_hotel_read_only(self):
        self.client.force_authenticate(self.manager)
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        self.assertEqual(
            self.client.get(reverse("guests:guest-list"), **HDR(self.hotel)).status_code,
            200,
        )
        res = self.client.post(
            reverse("guests:guest-list"), guest_body(), format="json", **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")


class GuestCrudTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def _create(self, **over):
        return self.client.post(
            reverse("guests:guest-list"), guest_body(**over), format="json", **HDR(self.hotel)
        )

    def test_create_and_update(self):
        res = self._create()
        self.assertEqual(res.status_code, 201)
        gid = res.data["id"]
        upd = self.client.patch(
            reverse("guests:guest-detail", args=[gid]),
            {"nationality": "TR"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(upd.data["nationality"], "TR")

    def test_list_scoped_by_hotel(self):
        self._create()
        other = make_hotel(slug="o")
        Guest.objects.create(hotel=other, full_name="Other Guest")
        res = self.client.get(reverse("guests:guest-list"), **HDR(self.hotel))
        self.assertEqual(res.data["count"], 1)

    def test_search_by_name_phone_document(self):
        self._create(full_name="Ali Hassan", phone="+905550001111",
                     document_type="passport", document_number="P123")
        self._create(full_name="Sara Kaya", phone="+905552223333")
        base = reverse("guests:guest-list")
        self.assertEqual(self.client.get(base, {"search": "Ali"}, **HDR(self.hotel)).data["count"], 1)
        self.assertEqual(self.client.get(base, {"search": "2223333"}, **HDR(self.hotel)).data["count"], 1)
        self.assertEqual(self.client.get(base, {"search": "P123"}, **HDR(self.hotel)).data["count"], 1)

    def test_invalid_phone_rejected(self):
        res = self._create(phone="not-a-phone!!")
        self.assertEqual(res.status_code, 400)

    def test_invalid_email_rejected(self):
        res = self._create(email="bad-email")
        self.assertEqual(res.status_code, 400)

    def test_document_unique_per_hotel(self):
        self._create(document_type="passport", document_number="X1")
        dup = self._create(full_name="Someone Else", document_type="passport", document_number="X1")
        self.assertEqual(dup.status_code, 400)

    def test_same_document_allowed_other_hotel(self):
        self._create(document_type="passport", document_number="X1")
        other = make_hotel(slug="o")
        add_member(other, "m2@x.com", kind=MembershipType.MANAGER)
        Guest.objects.create(hotel=other, full_name="Twin", document_type="passport", document_number="X1")
        self.assertEqual(Guest.objects.filter(document_number="X1").count(), 2)

    def test_delete_unreferenced_guest_hard_deletes(self):
        gid = self._create().data["id"]
        res = self.client.delete(reverse("guests:guest-detail", args=[gid]), **HDR(self.hotel))
        # Final closure: the response distinguishes deleted vs deactivated.
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"], "deleted")
        self.assertFalse(Guest.objects.filter(pk=gid).exists())


# --------------------------------------------------------------------------- #
# Final closure round                                                          #
# --------------------------------------------------------------------------- #

from datetime import timedelta

from django.utils import timezone as dj_tz

from apps.common.exceptions import GuestBlocked
from apps.guests.models import GuestBlockLog
from apps.notifications.models import ActivityEvent
from apps.reservations import services as res_services
from apps.reservations.models import ReservationStatus
from apps.rooms.models import Floor, Room, RoomType
from apps.stays.models import Stay, StayGuest, StayStatus

TODAY = dj_tz.localdate()


def make_room_env(hotel, *, numbers=("101", "102")):
    floor = Floor.objects.create(hotel=hotel, name="G", number="0")
    rtype = RoomType.objects.create(
        hotel=hotel, name="Standard", code="STD", base_capacity=2, max_capacity=3
    )
    rooms = [
        Room.objects.create(hotel=hotel, floor=floor, room_type=rtype, number=n)
        for n in numbers
    ]
    return rtype, rooms


def make_stay(hotel, guest, room, *, status=StayStatus.CHECKED_OUT,
              ci=None, co=None, reservation=None):
    ci = ci or TODAY - timedelta(days=3)
    co = co or TODAY - timedelta(days=1)
    stay = Stay.objects.create(
        hotel=hotel,
        reservation=reservation,
        room=room,
        primary_guest=guest,
        status=status,
        planned_check_in_date=ci,
        planned_check_out_date=co,
        actual_check_in_at=dj_tz.now(),
        actual_check_out_at=dj_tz.now() if status == StayStatus.CHECKED_OUT else None,
    )
    StayGuest.objects.create(hotel=hotel, stay=stay, guest=guest, role="primary")
    return stay


def make_reservation(hotel, rtype, *, phone="", doc="", number):
    return res_services.create_reservation(
        hotel,
        primary_guest_name="Res Guest",
        primary_guest_phone=phone,
        primary_guest_document_type="passport" if doc else "",
        primary_guest_document_number=doc,
        check_in_date=TODAY,
        check_out_date=TODAY + timedelta(days=2),
        lines=[{"room_type": rtype, "quantity": 1}],
        booking_kind="future",
        user=None,
        status=ReservationStatus.CONFIRMED,
    )


class GuestDirectoryTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype, (self.r101, self.r102) = make_room_env(self.hotel)

    def _directory(self, **params):
        return self.client.get(
            reverse("guests:guest-directory"), params, **HDR(self.hotel)
        )

    def test_guest_without_stay_hidden_but_picker_unbroken(self):
        Guest.objects.create(hotel=self.hotel, full_name="Booker Only")
        r = self._directory()
        self.assertEqual(r.data["count"], 0)
        # The PLAIN list (reservation/check-in pickers) still returns him.
        plain = self.client.get(reverse("guests:guest-list"), **HDR(self.hotel))
        self.assertEqual(plain.data["count"], 1)

    def test_reservation_without_stay_does_not_count(self):
        Guest.objects.create(hotel=self.hotel, full_name="Cancelled Booker")
        make_reservation(self.hotel, self.rtype, phone="+90111", number="X")
        self.assertEqual(self._directory().data["count"], 0)

    def test_past_stay_listed_as_new_with_stats(self):
        g = Guest.objects.create(hotel=self.hotel, full_name="Past Guest")
        make_stay(self.hotel, g, self.r101,
                  ci=TODAY - timedelta(days=5), co=TODAY - timedelta(days=2))
        r = self._directory()
        self.assertEqual(r.data["count"], 1)
        row = r.data["results"][0]
        self.assertEqual(row["stays_count"], 1)
        self.assertEqual(row["nights_total"], 3)
        self.assertFalse(row["is_repeat"])
        self.assertFalse(row["is_resident"])
        self.assertEqual(row["first_stay_date"], str(TODAY - timedelta(days=5)))
        self.assertEqual(row["last_stay_date"], str(TODAY - timedelta(days=5)))

    def test_in_house_guest_shows_room(self):
        g = Guest.objects.create(hotel=self.hotel, full_name="Resident")
        make_stay(self.hotel, g, self.r101, status=StayStatus.IN_HOUSE,
                  ci=TODAY, co=TODAY + timedelta(days=2))
        row = self._directory().data["results"][0]
        self.assertTrue(row["is_resident"])
        self.assertEqual(row["current_room_number"], "101")

    def test_two_real_stays_marks_repeat(self):
        g = Guest.objects.create(hotel=self.hotel, full_name="Returnee")
        make_stay(self.hotel, g, self.r101,
                  ci=TODAY - timedelta(days=10), co=TODAY - timedelta(days=8))
        make_stay(self.hotel, g, self.r102,
                  ci=TODAY - timedelta(days=3), co=TODAY - timedelta(days=1))
        row = self._directory().data["results"][0]
        self.assertEqual(row["stays_count"], 2)
        self.assertTrue(row["is_repeat"])
        self.assertEqual(row["nights_total"], 4)
        self.assertEqual(row["first_stay_date"], str(TODAY - timedelta(days=10)))
        self.assertEqual(row["last_stay_date"], str(TODAY - timedelta(days=3)))

    def test_cancelled_stays_never_count(self):
        g = Guest.objects.create(hotel=self.hotel, full_name="Cancelled Stay")
        make_stay(self.hotel, g, self.r101, status=StayStatus.CANCELLED)
        self.assertEqual(self._directory().data["count"], 0)
        g2 = Guest.objects.create(hotel=self.hotel, full_name="Mixed")
        make_stay(self.hotel, g2, self.r101, status=StayStatus.CANCELLED)
        make_stay(self.hotel, g2, self.r102)
        row = self._directory().data["results"][0]
        self.assertEqual(row["stays_count"], 1)
        self.assertFalse(row["is_repeat"])

    def test_directory_hotel_isolation(self):
        other = make_hotel(slug="o")
        _, (oroom, _unused) = make_room_env(other)
        og = Guest.objects.create(hotel=other, full_name="Foreign Guest")
        make_stay(other, og, oroom)
        self.assertEqual(self._directory().data["count"], 0)

    def test_directory_masks_document_without_sensitive_perm(self):
        g = Guest.objects.create(
            hotel=self.hotel, full_name="Doc Guest",
            document_type="passport", document_number="P123456789",
        )
        make_stay(self.hotel, g, self.r101)
        staff = add_member(self.hotel, "sv@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        row = self._directory().data["results"][0]
        self.assertEqual(row["document_number"], "••••6789")
        # Manager holds every permission -> full number.
        self.client.force_authenticate(self.manager)
        row = self._directory().data["results"][0]
        self.assertEqual(row["document_number"], "P123456789")


class GuestProfileTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype, (self.r101, self.r102) = make_room_env(self.hotel)
        self.guest = Guest.objects.create(
            hotel=self.hotel, full_name="Profile Guest", phone="+90555",
            document_type="passport", document_number="P987654321",
        )
        self.res = make_reservation(self.hotel, self.rtype, phone="+90555", number="R")
        make_stay(self.hotel, self.guest, self.r101,
                  ci=TODAY - timedelta(days=10), co=TODAY - timedelta(days=8))
        self.current = make_stay(
            self.hotel, self.guest, self.r102, status=StayStatus.IN_HOUSE,
            ci=TODAY, co=TODAY + timedelta(days=2), reservation=self.res,
        )
        from apps.finance import services as fin

        self.folio = fin.create_folio(
            self.hotel, stay=self.current, guest=self.guest
        )

    def _profile(self):
        return self.client.get(
            reverse("guests:guest-profile", args=[self.guest.id]), **HDR(self.hotel)
        )

    def test_profile_stats_history_and_links(self):
        r = self._profile()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["stays_count"], 2)
        self.assertTrue(r.data["is_repeat"])
        self.assertTrue(r.data["is_resident"])
        self.assertEqual(r.data["current"]["room_number"], "102")
        self.assertEqual(
            r.data["current"]["reservation_number"], self.res.reservation_number
        )
        self.assertEqual(r.data["current"]["folio_number"], self.folio.folio_number)
        self.assertEqual(len(r.data["stays"]), 2)
        newest = r.data["stays"][0]
        self.assertTrue(newest["is_current"])
        self.assertEqual(newest["folio_status"], "open")
        self.assertEqual(r.data["document_number"], "P987654321")  # manager

    def test_profile_is_read_only(self):
        url = reverse("guests:guest-profile", args=[self.guest.id])
        self.assertEqual(
            self.client.patch(url, {}, format="json", **HDR(self.hotel)).status_code,
            405,
        )
        self.assertEqual(self.client.delete(url, **HDR(self.hotel)).status_code, 405)

    def test_document_masked_without_sensitive_perm(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        r = self._profile()
        self.assertEqual(r.data["document_number"], "••••4321")

    def test_block_reason_visible_only_with_block_permission(self):
        from apps.guests.services import block_guest

        block_guest(self.guest, reason="damaged the room", user=self.manager)
        staff = add_member(self.hotel, "sv@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        r = self._profile()
        self.assertTrue(r.data["is_blocked"])
        self.assertIsNone(r.data["block_reason"])
        blocker = add_member(
            self.hotel, "sb@x.com", perms=["guests.view", "guests.block"]
        )
        self.client.force_authenticate(blocker)
        self.assertEqual(self._profile().data["block_reason"], "damaged the room")

    def test_profile_hotel_isolation(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        member = User.objects.get(email="om@x.com")
        self.client.force_authenticate(member)
        r = self.client.get(
            reverse("guests:guest-profile", args=[self.guest.id]), **HDR(other)
        )
        self.assertEqual(r.status_code, 404)


class GuestVipTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Maybe VIP")

    def _vip(self, value):
        return self.client.post(
            reverse("guests:guest-vip", args=[self.guest.id]),
            {"vip": value}, format="json", **HDR(self.hotel),
        )

    def test_mark_and_unmark_vip(self):
        r = self._vip(True)
        self.assertEqual(r.status_code, 200)
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.is_vip)
        self.assertIsNotNone(self.guest.vip_marked_at)
        self.assertEqual(self.guest.vip_marked_by, self.manager)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.vip_marked"
            ).exists()
        )
        self._vip(False)
        self.guest.refresh_from_db()
        self.assertFalse(self.guest.is_vip)
        self.assertIsNone(self.guest.vip_marked_at)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.vip_unmarked"
            ).exists()
        )

    def test_vip_permission_enforced(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._vip(True).status_code, 403)
        marker = add_member(self.hotel, "smv@x.com", perms=["guests.mark_vip"])
        self.client.force_authenticate(marker)
        self.assertEqual(self._vip(True).status_code, 200)

    def test_vip_flag_travels_to_stay_serializer(self):
        rtype, (room, _unused) = make_room_env(self.hotel)
        make_stay(self.hotel, self.guest, room, status=StayStatus.IN_HOUSE,
                  ci=TODAY, co=TODAY + timedelta(days=1))
        self._vip(True)
        r = self.client.get(reverse("stays:stay-current"), **HDR(self.hotel))
        self.assertTrue(r.data["results"][0]["primary_guest_is_vip"])


class GuestBlockTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(
            hotel=self.hotel, full_name="Trouble", phone="+90999",
            document_type="passport", document_number="TT111",
        )

    def _block(self, reason=None):
        body = {} if reason is None else {"reason": reason}
        return self.client.post(
            reverse("guests:guest-block", args=[self.guest.id]),
            body, format="json", **HDR(self.hotel),
        )

    def _unblock(self, note=""):
        return self.client.post(
            reverse("guests:guest-unblock", args=[self.guest.id]),
            {"note": note}, format="json", **HDR(self.hotel),
        )

    def test_block_requires_reason(self):
        self.assertEqual(self._block().status_code, 400)
        self.assertEqual(self._block("").status_code, 400)
        self.assertFalse(Guest.objects.get(pk=self.guest.pk).is_blocked)

    def test_block_and_unblock_preserve_history(self):
        r = self._block("smoking in the room")
        self.assertEqual(r.status_code, 200)
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.is_blocked)
        self.assertEqual(self.guest.block_reason, "smoking in the room")
        self.assertEqual(self.guest.blocked_by, self.manager)
        self._unblock("apologized")
        self.guest.refresh_from_db()
        self.assertFalse(self.guest.is_blocked)
        self.assertEqual(self.guest.block_reason, "")
        # The OLD reason survives in the immutable log.
        logs = list(GuestBlockLog.objects.filter(guest=self.guest).order_by("id"))
        self.assertEqual([entry.action for entry in logs], ["blocked", "unblocked"])
        self.assertEqual(logs[0].reason, "smoking in the room")
        self.assertEqual(logs[1].reason, "apologized")
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.blocked"
            ).exists()
        )
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.unblocked"
            ).exists()
        )

    def test_block_permission_enforced(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self._block("x").status_code, 403)
        blocker = add_member(self.hotel, "sb@x.com", perms=["guests.block"])
        self.client.force_authenticate(blocker)
        self.assertEqual(self._block("valid reason").status_code, 200)

    def test_block_is_hotel_scoped(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        om = User.objects.get(email="om@x.com")
        # The other hotel cannot even SEE (or block) this guest.
        self.client.force_authenticate(om)
        r = self.client.post(
            reverse("guests:guest-block", args=[self.guest.id]),
            {"reason": "x"}, format="json", **HDR(other),
        )
        self.assertEqual(r.status_code, 404)
        # A guest with the same phone in the other hotel stays unaffected.
        twin = Guest.objects.create(hotel=other, full_name="Twin", phone="+90999")
        self.assertFalse(twin.is_blocked)


class GuestBlockEffectTests(APITestCase):
    """The block guard sits in the CENTRAL services: reservations (snapshot
    match) and check-in (direct guest match)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype, (self.r101, self.r102) = make_room_env(self.hotel)
        self.guest = Guest.objects.create(
            hotel=self.hotel, full_name="Blocked Person", phone="+90777",
            document_type="passport", document_number="BB999",
        )
        from apps.guests.services import block_guest

        block_guest(self.guest, reason="fraud", user=self.manager)

    def test_reservation_by_matching_phone_refused(self):
        with self.assertRaises(GuestBlocked):
            make_reservation(self.hotel, self.rtype, phone="+90777", number="X")

    def test_reservation_by_matching_document_refused(self):
        with self.assertRaises(GuestBlocked):
            make_reservation(self.hotel, self.rtype, doc="BB999", number="X")

    def test_unrelated_snapshot_books_fine(self):
        res = make_reservation(self.hotel, self.rtype, phone="+90111", number="X")
        self.assertEqual(res.status, ReservationStatus.CONFIRMED)

    def test_check_in_of_blocked_guest_refused_without_reason_leak(self):
        res = make_reservation(self.hotel, self.rtype, phone="+90111", number="X")
        line = res.lines.first()
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id,
             "room": self.r101.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "guest_blocked")
        self.assertNotIn("fraud", str(r.data))

    def test_blocked_companion_refused(self):
        res = make_reservation(self.hotel, self.rtype, phone="+90111", number="X")
        line = res.lines.first()
        clean = Guest.objects.create(hotel=self.hotel, full_name="Clean Guest")
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id,
             "room": self.r101.id, "primary_guest": clean.id,
             "companions": [self.guest.id]},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "guest_blocked")

    def test_unblock_allows_booking_and_check_in_again(self):
        from apps.guests.services import unblock_guest

        unblock_guest(self.guest, user=self.manager)
        res = make_reservation(self.hotel, self.rtype, phone="+90777", number="X")
        line = res.lines.first()
        r = self.client.post(
            reverse("stays:stay-check-in"),
            {"reservation": res.id, "reservation_line": line.id,
             "room": self.r101.id, "primary_guest": self.guest.id},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 201)

    def test_other_hotel_same_phone_not_blocked(self):
        other = make_hotel(slug="o")
        otype, _rooms = make_room_env(other)
        res = make_reservation(other, otype, phone="+90777", number="X")
        self.assertEqual(res.status, ReservationStatus.CONFIRMED)


class GuestDeleteHardeningTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype, (self.r101, _unused) = make_room_env(self.hotel)

    def _delete(self, guest):
        return self.client.delete(
            reverse("guests:guest-detail", args=[guest.id]), **HDR(self.hotel)
        )

    def test_guest_with_stay_deactivates(self):
        g = Guest.objects.create(hotel=self.hotel, full_name="Stayed")
        make_stay(self.hotel, g, self.r101)
        r = self._delete(g)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["result"], "deactivated")
        g.refresh_from_db()
        self.assertFalse(g.is_active)
        self.assertTrue(Stay.objects.filter(hotel=self.hotel).exists())

    def test_guest_with_folio_deactivates(self):
        from apps.finance import services as fin

        g = Guest.objects.create(hotel=self.hotel, full_name="Folio Only")
        folio = fin.create_folio(self.hotel, guest=g)
        r = self._delete(g)
        self.assertEqual(r.data["result"], "deactivated")
        g.refresh_from_db()
        self.assertFalse(g.is_active)
        folio.refresh_from_db()
        self.assertEqual(folio.guest_id, g.id)  # the link survives

    def test_guest_with_lost_found_deactivates(self):
        from apps.operations.models import LostFoundItem

        g = Guest.objects.create(hotel=self.hotel, full_name="Lost Item Owner")
        LostFoundItem.objects.create(
            hotel=self.hotel, item_number="LF-1", title="Watch", guest=g
        )
        r = self._delete(g)
        self.assertEqual(r.data["result"], "deactivated")
        g.refresh_from_db()
        self.assertFalse(g.is_active)

    def test_untouched_guest_hard_deletes_with_activity(self):
        g = Guest.objects.create(hotel=self.hotel, full_name="Fresh Nobody")
        r = self._delete(g)
        self.assertEqual(r.data["result"], "deleted")
        self.assertFalse(Guest.objects.filter(pk=g.pk).exists())
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.deleted"
            ).exists()
        )

    def test_deactivation_logged(self):
        g = Guest.objects.create(hotel=self.hotel, full_name="Stayed")
        make_stay(self.hotel, g, self.r101)
        self._delete(g)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.deactivated"
            ).exists()
        )


class GuestSensitiveDataTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.guest = Guest.objects.create(
            hotel=self.hotel, full_name="Sensitive", phone="+90222",
            document_type="passport", document_number="SENS123456",
        )

    def test_plain_list_masked_without_perm_full_with_perm(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        row = self.client.get(
            reverse("guests:guest-list"), **HDR(self.hotel)
        ).data["results"][0]
        self.assertEqual(row["document_number"], "••••3456")
        sensitive = add_member(
            self.hotel, "ss@x.com",
            perms=["guests.view", "guests.view_sensitive_data"],
        )
        self.client.force_authenticate(sensitive)
        row = self.client.get(
            reverse("guests:guest-list"), **HDR(self.hotel)
        ).data["results"][0]
        self.assertEqual(row["document_number"], "SENS123456")

    def test_masked_value_rejected_on_update(self):
        self.client.force_authenticate(self.manager)
        r = self.client.patch(
            reverse("guests:guest-detail", args=[self.guest.id]),
            {"document_number": "••••3456"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.document_number, "SENS123456")

    def test_document_uniqueness_unchanged(self):
        self.client.force_authenticate(self.manager)
        r = self.client.post(
            reverse("guests:guest-list"),
            guest_body(document_type="passport", document_number="SENS123456"),
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)


class GuestActivityTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_create_and_update_are_logged(self):
        r = self.client.post(
            reverse("guests:guest-list"),
            guest_body(document_type="passport", document_number="ACT9876543"),
            format="json", **HDR(self.hotel),
        )
        gid = r.data["id"]
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.created"
            ).exists()
        )
        self.client.patch(
            reverse("guests:guest-detail", args=[gid]),
            {"full_name": "Jane Renamed", "phone": "+905550000000",
             "document_number": "ACT1111111"},
            format="json", **HDR(self.hotel),
        )
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="guest.updated"
        ).latest("id")
        self.assertIn("Jane Traveler → Jane Renamed", event.message)
        self.assertIn("+905551112233 → +905550000000", event.message)
        # Document numbers appear MASKED only.
        self.assertNotIn("ACT9876543", event.message)
        self.assertNotIn("ACT1111111", event.message)
        self.assertIn("••••", event.message)

    def test_no_full_document_anywhere_in_activity(self):
        self.client.post(
            reverse("guests:guest-list"),
            guest_body(document_type="passport", document_number="FULLSECRET99"),
            format="json", **HDR(self.hotel),
        )
        for event in ActivityEvent.objects.filter(hotel=self.hotel):
            self.assertNotIn("FULLSECRET99", event.title)
            self.assertNotIn("FULLSECRET99", event.message)


class GuestNewPermissionTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Perm Target")

    def test_new_endpoints_403_without_permission(self):
        staff = add_member(self.hotel, "sv@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.post(
                reverse("guests:guest-vip", args=[self.guest.id]),
                {"vip": True}, format="json", **HDR(self.hotel),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("guests:guest-block", args=[self.guest.id]),
                {"reason": "x"}, format="json", **HDR(self.hotel),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("guests:guest-unblock", args=[self.guest.id]),
                {}, format="json", **HDR(self.hotel),
            ).status_code,
            403,
        )

    def test_directory_and_profile_need_view(self):
        nobody = add_member(self.hotel, "sn@x.com", perms=["rooms.view"])
        self.client.force_authenticate(nobody)
        self.assertEqual(
            self.client.get(
                reverse("guests:guest-directory"), **HDR(self.hotel)
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("guests:guest-profile", args=[self.guest.id]),
                **HDR(self.hotel),
            ).status_code,
            403,
        )
