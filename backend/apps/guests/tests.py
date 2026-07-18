"""Tests for guests (Phase 7): access/permissions, CRUD, search, validation,
tenant isolation, and the deactivate-instead-of-delete rule."""
from __future__ import annotations

from django.test import SimpleTestCase
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

    def test_create_endpoint_removed_returns_405(self):
        # Decision 9: there is NO create endpoint. Even a viewer whose request
        # clears the view permission gets 405 — the API can never mint a guest.
        staff = add_member(self.hotel, "s3@x.com", perms=["guests.view"])
        self.client.force_authenticate(staff)
        res = self.client.post(
            reverse("guests:guest-list"), guest_body(), format="json", **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 405)

    def test_suspended_hotel_read_only(self):
        self.client.force_authenticate(self.manager)
        # Seed directly — creation no longer goes through the API (Decision 9).
        guest = Guest.objects.create(hotel=self.hotel, full_name="Existing")
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        # Reads keep working.
        self.assertEqual(
            self.client.get(reverse("guests:guest-list"), **HDR(self.hotel)).status_code,
            200,
        )
        # The list route has no write path anymore: a POST is 405, not a guard.
        self.assertEqual(
            self.client.post(
                reverse("guests:guest-list"), guest_body(), format="json",
                **HDR(self.hotel),
            ).status_code,
            405,
        )
        # A genuine guests WRITE (update) is refused while suspended.
        res = self.client.patch(
            reverse("guests:guest-detail", args=[guest.id]),
            {"nationality": "TR"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")


class GuestCrudTests(APITestCase):
    """Read / update / delete over the guests API. Creation is no longer an API
    concern (Decision 9) — guests are seeded directly and every write here goes
    through the UPDATE path."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def _guest(self, **over):
        body = {"full_name": "Jane Traveler", "phone": "+905551112233"}
        body.update(over)
        return Guest.objects.create(hotel=self.hotel, **body)

    def _patch(self, guest, body):
        return self.client.patch(
            reverse("guests:guest-detail", args=[guest.id]),
            body, format="json", **HDR(self.hotel),
        )

    def test_update(self):
        g = self._guest()
        upd = self._patch(g, {"nationality": "TR"})
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.data["nationality"], "TR")

    def test_list_scoped_by_hotel(self):
        self._guest()
        other = make_hotel(slug="o")
        Guest.objects.create(hotel=other, full_name="Other Guest")
        res = self.client.get(reverse("guests:guest-list"), **HDR(self.hotel))
        self.assertEqual(res.data["count"], 1)

    def test_search_by_name_phone_document(self):
        self._guest(full_name="Ali Hassan", phone="+905550001111",
                    document_type="passport", document_number="P123")
        self._guest(full_name="Sara Kaya", phone="+905552223333")
        base = reverse("guests:guest-list")
        self.assertEqual(self.client.get(base, {"search": "Ali"}, **HDR(self.hotel)).data["count"], 1)
        self.assertEqual(self.client.get(base, {"search": "2223333"}, **HDR(self.hotel)).data["count"], 1)
        # The manager holds guests.view_sensitive_data -> the document substring
        # search is available (a basic viewer's oracle is closed — see
        # GuestSearchOracleTests).
        self.assertEqual(self.client.get(base, {"search": "P123"}, **HDR(self.hotel)).data["count"], 1)

    def test_invalid_phone_rejected_on_update(self):
        g = self._guest()
        res = self._patch(g, {"phone": "not-a-phone!!"})
        self.assertEqual(res.status_code, 400)

    def test_invalid_email_rejected_on_update(self):
        g = self._guest()
        res = self._patch(g, {"email": "bad-email"})
        self.assertEqual(res.status_code, 400)

    def test_document_unique_per_hotel_on_update(self):
        # Distinct phones — the active-phone uniqueness constraint is per hotel.
        self._guest(document_type="passport", document_number="X1")
        other = self._guest(full_name="Someone Else", phone="+905559998888")
        dup = self._patch(other, {"document_type": "passport", "document_number": "X1"})
        self.assertEqual(dup.status_code, 400)

    def test_same_document_allowed_other_hotel(self):
        self._guest(document_type="passport", document_number="X1")
        other = make_hotel(slug="o")
        add_member(other, "m2@x.com", kind=MembershipType.MANAGER)
        Guest.objects.create(hotel=other, full_name="Twin", document_type="passport", document_number="X1")
        self.assertEqual(Guest.objects.filter(document_number="X1").count(), 2)

    def test_delete_unreferenced_guest_hard_deletes(self):
        g = self._guest()
        res = self.client.delete(reverse("guests:guest-detail", args=[g.id]), **HDR(self.hotel))
        # Final closure: the response distinguishes deleted vs deactivated.
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"], "deleted")
        self.assertFalse(Guest.objects.filter(pk=g.id).exists())

    def test_no_create_endpoint(self):
        # Decision 9: even a full-permission manager cannot create via the API.
        res = self.client.post(
            reverse("guests:guest-list"), guest_body(), format="json", **HDR(self.hotel)
        )
        self.assertEqual(res.status_code, 405)


# --------------------------------------------------------------------------- #
# Final closure round                                                          #
# --------------------------------------------------------------------------- #

from datetime import date, timedelta

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
        make_reservation(self.hotel, self.rtype, phone="+905559990000", number="X")
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
            hotel=self.hotel, full_name="Profile Guest", phone="+905550005555",
            document_type="passport", document_number="P987654321",
        )
        self.res = make_reservation(self.hotel, self.rtype, phone="+905550005555", number="R")
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
            hotel=self.hotel, full_name="Blocked Person", phone="+905551112233",
            document_type="passport", document_number="BB999",
        )
        from apps.guests.services import block_guest

        block_guest(self.guest, reason="fraud", user=self.manager)

    def test_reservation_by_matching_phone_refused(self):
        with self.assertRaises(GuestBlocked):
            make_reservation(self.hotel, self.rtype, phone="+905551112233", number="X")

    def test_reservation_by_matching_document_refused(self):
        with self.assertRaises(GuestBlocked):
            make_reservation(self.hotel, self.rtype, doc="BB999", number="X")

    def test_unrelated_snapshot_books_fine(self):
        res = make_reservation(self.hotel, self.rtype, phone="+905559990000", number="X")
        self.assertEqual(res.status, ReservationStatus.CONFIRMED)

    def test_check_in_of_blocked_guest_refused_without_reason_leak(self):
        res = make_reservation(self.hotel, self.rtype, phone="+905559990000", number="X")
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
        res = make_reservation(self.hotel, self.rtype, phone="+905559990000", number="X")
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
        res = make_reservation(self.hotel, self.rtype, phone="+905551112233", number="X")
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
        res = make_reservation(other, otype, phone="+905551112233", number="X")
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
        other = Guest.objects.create(hotel=self.hotel, full_name="Other")
        r = self.client.patch(
            reverse("guests:guest-detail", args=[other.id]),
            {"document_type": "passport", "document_number": "SENS123456"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)


class GuestActivityTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_update_is_logged(self):
        # Creation no longer flows through the API (Decision 9); seed directly,
        # then prove the UPDATE is logged with the document numbers MASKED.
        g = Guest.objects.create(
            hotel=self.hotel, full_name="Jane Traveler", phone="+905551112233",
            document_type="passport", document_number="ACT9876543",
        )
        self.client.patch(
            reverse("guests:guest-detail", args=[g.id]),
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

    def test_national_id_change_is_logged_masked(self):
        # SEC-F1 / U-06: a national_id edit MUST be audited (it is a first-class
        # identity field), but MASKED — the activity log is readable without
        # guests.view_sensitive_data, so the raw identifier must never appear.
        g = Guest.objects.create(
            hotel=self.hotel, full_name="Idris Traveler",
            national_id="NIDOLD9999",
        )
        self.client.patch(
            reverse("guests:guest-detail", args=[g.id]),
            {"national_id": "NIDNEW8888"},
            format="json", **HDR(self.hotel),
        )
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="guest.updated"
        ).latest("id")
        # The change IS recorded ...
        self.assertIn("national_id:", event.message)
        # ... but only MASKED (last four); no raw identifier leaks.
        self.assertNotIn("NIDOLD9999", event.message)
        self.assertNotIn("NIDNEW8888", event.message)
        self.assertIn("••••9999", event.message)
        self.assertIn("••••8888", event.message)

    def test_national_id_unchanged_is_not_logged(self):
        # A PATCH that does not touch national_id records no national_id change.
        g = Guest.objects.create(
            hotel=self.hotel, full_name="Stable Id", national_id="NIDSTAY1234",
        )
        self.client.patch(
            reverse("guests:guest-detail", args=[g.id]),
            {"full_name": "Stable Renamed"},
            format="json", **HDR(self.hotel),
        )
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="guest.updated"
        ).latest("id")
        self.assertNotIn("national_id:", event.message)

    def test_no_full_document_anywhere_in_activity(self):
        g = Guest.objects.create(
            hotel=self.hotel, full_name="Secret Holder",
            document_type="passport", document_number="FULLSECRET99",
        )
        self.client.patch(
            reverse("guests:guest-detail", args=[g.id]),
            {"document_number": "FULLSECRET88"},
            format="json", **HDR(self.hotel),
        )
        for event in ActivityEvent.objects.filter(hotel=self.hotel):
            self.assertNotIn("FULLSECRET99", event.title)
            self.assertNotIn("FULLSECRET99", event.message)
            self.assertNotIn("FULLSECRET88", event.title)
            self.assertNotIn("FULLSECRET88", event.message)

    def test_full_national_id_never_appears_in_activity(self):
        # Companion to the document check: a raw national_id never lands anywhere.
        g = Guest.objects.create(
            hotel=self.hotel, full_name="Nid Secret", national_id="RAWNID55550",
        )
        self.client.patch(
            reverse("guests:guest-detail", args=[g.id]),
            {"national_id": "RAWNID66660"},
            format="json", **HDR(self.hotel),
        )
        for event in ActivityEvent.objects.filter(hotel=self.hotel):
            self.assertNotIn("RAWNID55550", event.title)
            self.assertNotIn("RAWNID55550", event.message)
            self.assertNotIn("RAWNID66660", event.title)
            self.assertNotIn("RAWNID66660", event.message)


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


# --------------------------------------------------------------------------- #
# Guests API hardening (EXEC-GUESTS-CLOSURE-01, W3a)                           #
# --------------------------------------------------------------------------- #


class GuestSearchOracleTests(APITestCase):
    """Decision 5 / U-09 / U-10 / S3.

    The document-number SUBSTRING search is a reconstruction oracle and is closed
    for a basic viewer. The national ID is searchable EXACT-normalized only (never
    partial). Output stays masked per permission. Covers BOTH the plain list and
    the directory (they share ``_guest_search_q``)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.rtype, (self.r101, _unused) = make_room_env(self.hotel)
        # Phone deliberately avoids the "1234"/"5678" substrings so the
        # "national id never partial-matches" checks can't pass via the phone.
        self.guest = Guest.objects.create(
            hotel=self.hotel, full_name="Oracle Target", phone="+905550009999",
            document_type="passport", document_number="SECRET789",
            national_id="12345678",
        )
        make_stay(self.hotel, self.guest, self.r101)  # so it appears in directory
        self.viewer = add_member(self.hotel, "v@x.com", perms=["guests.view"])
        self.sensitive = add_member(
            self.hotel, "vs@x.com",
            perms=["guests.view", "guests.view_sensitive_data"],
        )

    def _list_count(self, term):
        return self.client.get(
            reverse("guests:guest-list"), {"search": term}, **HDR(self.hotel)
        ).data["count"]

    def _dir_count(self, term):
        return self.client.get(
            reverse("guests:guest-directory"), {"search": term}, **HDR(self.hotel)
        ).data["count"]

    def test_document_substring_hidden_from_basic_viewer(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self._list_count("SECRET"), 0)
        self.assertEqual(self._dir_count("SECRET"), 0)
        # Name search still works for the basic viewer.
        self.assertEqual(self._list_count("Oracle"), 1)

    def test_document_substring_visible_with_sensitive_perm(self):
        self.client.force_authenticate(self.sensitive)
        self.assertEqual(self._list_count("SECRET"), 1)
        self.assertEqual(self._dir_count("SECRET"), 1)

    def test_national_id_exact_match_for_basic_viewer(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self._list_count("12345678"), 1)
        self.assertEqual(self._list_count("1234-5678"), 1)  # punctuation ignored
        self.assertEqual(self._dir_count("12345678"), 1)
        # The row is still masked for a basic viewer.
        row = self.client.get(
            reverse("guests:guest-list"), {"search": "12345678"}, **HDR(self.hotel)
        ).data["results"][0]
        self.assertIn("•", row["national_id"])

    def test_national_id_never_partial_matches(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self._list_count("1234"), 0)
        self.assertEqual(self._list_count("5678"), 0)
        self.assertEqual(self._dir_count("1234"), 0)


class GuestProfileUpcomingTests(APITestCase):
    """U-15 / S5: the profile surfaces upcoming reservations + ``needs_review``,
    and masks ``date_of_birth`` / ``address`` behind guests.view_sensitive_data."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(
            hotel=self.hotel, full_name="Upcoming Guest", phone="+905551110000",
            date_of_birth=date(1990, 5, 12), address="12 Baker Street",
        )

    def _reservation(self, *, number, status, ci, co):
        from apps.reservations.models import Reservation

        return Reservation.objects.create(
            hotel=self.hotel, reservation_number=number,
            status=status, booking_kind="future",
            check_in_date=ci, check_out_date=co,
            primary_guest=self.guest, primary_guest_name="Upcoming Guest",
        )

    def _profile(self):
        return self.client.get(
            reverse("guests:guest-profile", args=[self.guest.id]), **HDR(self.hotel)
        )

    def test_only_active_future_reservations_are_upcoming(self):
        future = self._reservation(
            number="R-future", status=ReservationStatus.CONFIRMED,
            ci=TODAY + timedelta(days=2), co=TODAY + timedelta(days=4),
        )
        # Departed booking -> not upcoming.
        self._reservation(
            number="R-past", status=ReservationStatus.CONFIRMED,
            ci=TODAY - timedelta(days=5), co=TODAY - timedelta(days=2),
        )
        # Cancelled future booking -> not active.
        self._reservation(
            number="R-cancelled", status=ReservationStatus.CANCELLED,
            ci=TODAY + timedelta(days=3), co=TODAY + timedelta(days=6),
        )
        data = self._profile().data
        numbers = [r["reservation_number"] for r in data["upcoming_reservations"]]
        self.assertEqual(numbers, ["R-future"])
        self.assertEqual(data["upcoming_reservations"][0]["reservation_id"], future.id)

    def test_needs_review_true_only_when_blocked_with_upcoming(self):
        from apps.guests.services import block_guest

        self._reservation(
            number="R1", status=ReservationStatus.CONFIRMED,
            ci=TODAY + timedelta(days=1), co=TODAY + timedelta(days=3),
        )
        self.assertFalse(self._profile().data["needs_review"])
        block_guest(self.guest, reason="pending dispute", user=self.manager)
        self.assertTrue(self._profile().data["needs_review"])

    def test_blocked_without_upcoming_does_not_need_review(self):
        from apps.guests.services import block_guest

        block_guest(self.guest, reason="old issue", user=self.manager)
        self.assertFalse(self._profile().data["needs_review"])

    def test_dob_and_address_masked_without_sensitive_perm(self):
        viewer = add_member(self.hotel, "v@x.com", perms=["guests.view"])
        self.client.force_authenticate(viewer)
        data = self._profile().data
        self.assertEqual(data["date_of_birth"], "••••")
        self.assertEqual(data["address"], "••••")
        # The manager (holds the sensitive permission) sees the real values.
        self.client.force_authenticate(self.manager)
        data = self._profile().data
        self.assertEqual(data["date_of_birth"], "1990-05-12")
        self.assertEqual(data["address"], "12 Baker Street")


class GuestUpdateHardeningTests(APITestCase):
    """Decision 3 (reject a national_id document) + Decision 1 (canonical phone
    on update)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(
            hotel=self.hotel, full_name="Edit Target", phone="+905551110000",
        )

    def _patch(self, body):
        return self.client.patch(
            reverse("guests:guest-detail", args=[self.guest.id]),
            body, format="json", **HDR(self.hotel),
        )

    def test_national_id_document_type_rejected(self):
        r = self._patch({"document_type": "national_id", "document_number": "999"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(
            r.data["details"]["document_type"][0].code,
            "national_id_must_use_national_id_field",
        )

    def test_passport_document_type_allowed(self):
        r = self._patch({"document_type": "passport", "document_number": "P55"})
        self.assertEqual(r.status_code, 200)

    def test_phone_canonicalized_on_update(self):
        from apps.hotels.models import HotelSettings

        HotelSettings.objects.create(hotel=self.hotel, default_phone_country="SA")
        r = self._patch({"phone": "0555 111 222"})
        self.assertEqual(r.status_code, 200)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.phone, "+966555111222")
        self.assertEqual(self.guest.phone_normalized, "+966555111222")

    def test_uninterpretable_local_phone_rejected(self):
        # No default_phone_country on this hotel -> a LOCAL number cannot be
        # canonicalized and is refused (never stored approximately).
        r = self._patch({"phone": "0555111222"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["details"]["phone"][0].code, "invalid_phone")
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.phone, "+905551110000")  # unchanged


# --------------------------------------------------------------------------- #
# GAP-1 read-only profile sub-resources (EXEC-GUESTS-CLOSURE-01, W3b)          #
# stays / reservations / documents / change-log — paginated, hotel-scoped,    #
# permission-scoped, masking fail-closed, block-reason gated.                 #
# --------------------------------------------------------------------------- #

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.reservations.models import (
    Reservation,
    ReservationDocument,
    ReservationOccupant,
)


def make_res(hotel, guest, *, number, status=ReservationStatus.CONFIRMED,
             source="direct", ci=None, co=None):
    """A reservation LINKED to ``guest`` as the primary guest (FK set)."""
    ci = ci or TODAY
    co = co or TODAY + timedelta(days=2)
    return Reservation.objects.create(
        hotel=hotel,
        reservation_number=number,
        status=status,
        source=source,
        booking_kind="future",
        check_in_date=ci,
        check_out_date=co,
        primary_guest=guest,
        primary_guest_name=guest.full_name,
    )


class GuestStaysEndpointTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype, (self.r101, self.r102) = make_room_env(self.hotel)
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Stayer")
        self.res = make_res(self.hotel, self.guest, number="RS1")
        # Newest arrival last-created on purpose so ordering (not insertion) is
        # what surfaces it first.
        self.old = make_stay(
            self.hotel, self.guest, self.r101,
            ci=TODAY - timedelta(days=10), co=TODAY - timedelta(days=8),
        )
        self.recent = make_stay(
            self.hotel, self.guest, self.r102, status=StayStatus.IN_HOUSE,
            ci=TODAY, co=TODAY + timedelta(days=3), reservation=self.res,
        )

    def _url(self, guest=None):
        return reverse("guests:guest-stays", args=[(guest or self.guest).id])

    def test_permission_required(self):
        staff = add_member(self.hotel, "no@x.com", perms=["rooms.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 403)
        viewer = add_member(self.hotel, "yes@x.com", perms=["guests.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 200)

    def test_tenant_isolation_other_hotel_guest_404(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(User.objects.get(email="om@x.com"))
        # The other hotel's member cannot resolve THIS hotel's guest.
        r = self.client.get(self._url(), **HDR(other))
        self.assertEqual(r.status_code, 404)

    def test_newest_first_and_fields(self):
        r = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 2)
        first = r.data["results"][0]
        self.assertEqual(first["stay_id"], self.recent.id)  # newest first
        self.assertEqual(first["status"], "in_house")
        self.assertFalse(first["is_checked_out"])
        self.assertEqual(first["room_number"], "102")
        self.assertEqual(first["room_type_name"], "Standard")
        self.assertEqual(first["nights"], 3)
        self.assertEqual(first["reservation_number"], self.res.reservation_number)
        second = r.data["results"][1]
        self.assertEqual(second["stay_id"], self.old.id)
        self.assertTrue(second["is_checked_out"])

    def test_folio_link_when_present(self):
        from apps.finance import services as fin

        folio = fin.create_folio(self.hotel, stay=self.recent, guest=self.guest)
        first = self.client.get(self._url(), **HDR(self.hotel)).data["results"][0]
        self.assertEqual(first["folio"]["folio_number"], folio.folio_number)
        self.assertEqual(first["folio"]["status"], "open")
        # No monetary value leaks into a stay row (finance.view territory).
        self.assertNotIn("balance", first["folio"])

    def test_only_this_guests_stays(self):
        other_guest = Guest.objects.create(hotel=self.hotel, full_name="Someone")
        make_stay(self.hotel, other_guest, self.r101,
                  ci=TODAY - timedelta(days=2), co=TODAY - timedelta(days=1))
        r = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r.data["count"], 2)  # unchanged

    def test_pagination_is_real_not_first_page_only(self):
        # A third stay -> with page_size=2 the last row must appear on page 2.
        make_stay(self.hotel, self.guest, self.r101,
                  ci=TODAY - timedelta(days=20), co=TODAY - timedelta(days=19))
        p1 = self.client.get(self._url(), {"page_size": 2}, **HDR(self.hotel))
        self.assertEqual(p1.data["count"], 3)
        self.assertEqual(len(p1.data["results"]), 2)
        self.assertIsNotNone(p1.data["next"])
        p2 = self.client.get(
            self._url(), {"page_size": 2, "page": 2}, **HDR(self.hotel)
        )
        self.assertEqual(len(p2.data["results"]), 1)
        seen = {row["stay_id"] for row in p1.data["results"] + p2.data["results"]}
        self.assertEqual(len(seen), 3)  # every stay reachable, none duplicated


class GuestReservationsEndpointTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Booker")
        self.past = make_res(
            self.hotel, self.guest, number="RP",
            ci=TODAY - timedelta(days=9), co=TODAY - timedelta(days=6),
        )
        self.future = make_res(
            self.hotel, self.guest, number="RF", source="phone",
            ci=TODAY + timedelta(days=5), co=TODAY + timedelta(days=8),
        )

    def _url(self, guest=None):
        return reverse("guests:guest-reservations", args=[(guest or self.guest).id])

    def test_permission_required(self):
        staff = add_member(self.hotel, "no@x.com", perms=["rooms.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 403)

    def test_tenant_isolation_other_hotel_guest_404(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(User.objects.get(email="om@x.com"))
        self.assertEqual(self.client.get(self._url(), **HDR(other)).status_code, 404)

    def test_history_fields_and_order(self):
        r = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r.data["count"], 2)
        first = r.data["results"][0]  # newest arrival first
        self.assertEqual(first["reservation_number"], "RF")
        self.assertEqual(first["source"], "phone")
        self.assertEqual(first["status"], "confirmed")
        self.assertEqual(first["booking_kind"], "future")
        self.assertEqual(first["check_in_date"], str(TODAY + timedelta(days=5)))
        self.assertEqual(r.data["results"][1]["reservation_number"], "RP")

    def test_only_reservations_where_guest_is_primary(self):
        stranger = Guest.objects.create(hotel=self.hotel, full_name="Stranger")
        make_res(self.hotel, stranger, number="RX")
        self.assertEqual(
            self.client.get(self._url(), **HDR(self.hotel)).data["count"], 2
        )

    def test_pagination_is_real(self):
        make_res(self.hotel, self.guest, number="R3",
                 ci=TODAY + timedelta(days=1), co=TODAY + timedelta(days=2))
        p1 = self.client.get(self._url(), {"page_size": 2}, **HDR(self.hotel))
        self.assertEqual(p1.data["count"], 3)
        self.assertEqual(len(p1.data["results"]), 2)
        p2 = self.client.get(
            self._url(), {"page_size": 2, "page": 2}, **HDR(self.hotel)
        )
        self.assertEqual(len(p2.data["results"]), 1)


class GuestDocumentsEndpointTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Doc Owner")
        # (a) a whole-reservation / primary-guest document (occupant NULL).
        self.res = make_res(self.hotel, self.guest, number="RD1")
        self.primary_doc = ReservationDocument.objects.create(
            hotel=self.hotel, reservation=self.res, occupant=None,
            doc_type="passport", number="PP1234567",
        )
        # (b) a document attached to the guest AS a named occupant on another
        # reservation (whose primary guest is someone else).
        stranger = Guest.objects.create(hotel=self.hotel, full_name="Host")
        self.other_res = make_res(self.hotel, stranger, number="RD2")
        self.occupant = ReservationOccupant.objects.create(
            hotel=self.hotel, reservation=self.other_res, guest=self.guest,
            first_name="Doc", last_name="Owner",
        )
        self.occupant_doc = ReservationDocument.objects.create(
            hotel=self.hotel, reservation=self.other_res, occupant=self.occupant,
            doc_type="national_id", number="NID99",
        )
        # A document that is NOT this guest's (stranger's own primary doc).
        self.noise_doc = ReservationDocument.objects.create(
            hotel=self.hotel, reservation=self.other_res, occupant=None,
            doc_type="visa", number="ZZZ",
        )
        self._files = []

    def tearDown(self):
        for field in self._files:
            try:
                field.delete(save=False)
            except Exception:  # pragma: no cover - best-effort disk cleanup
                pass

    def _url(self, guest=None):
        return reverse("guests:guest-documents", args=[(guest or self.guest).id])

    def _member(self, email, perms):
        m = add_member(self.hotel, email, perms=perms)
        self.client.force_authenticate(m)
        return m

    def test_requires_both_guests_view_and_reservation_documents_view(self):
        # guests.view alone is NOT enough — the reservation-document control is
        # required in addition.
        self._member("gv@x.com", ["guests.view"])
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 403)
        # reservation_documents.view alone is not enough either.
        self._member("rd@x.com", ["reservation_documents.view"])
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 403)
        # Both together -> allowed.
        self._member("both@x.com", ["guests.view", "reservation_documents.view"])
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 200)

    def test_aggregates_primary_and_occupant_docs_excludes_others(self):
        r = self.client.get(self._url(), **HDR(self.hotel))  # manager has all perms
        self.assertEqual(r.status_code, 200)
        ids = {row["id"] for row in r.data["results"]}
        self.assertEqual(ids, {self.primary_doc.id, self.occupant_doc.id})
        self.assertNotIn(self.noise_doc.id, ids)

    def test_number_masked_without_sensitive_perm(self):
        self._member("v@x.com", ["guests.view", "reservation_documents.view"])
        rows = {row["id"]: row for row in
                self.client.get(self._url(), **HDR(self.hotel)).data["results"]}
        self.assertEqual(rows[self.primary_doc.id]["number"], "••••4567")
        # Manager (holds guests.view_sensitive_data) sees the full number.
        self.client.force_authenticate(self.manager)
        rows = {row["id"]: row for row in
                self.client.get(self._url(), **HDR(self.hotel)).data["results"]}
        self.assertEqual(rows[self.primary_doc.id]["number"], "PP1234567")

    def test_tenant_isolation_other_hotel_guest_404(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(User.objects.get(email="om@x.com"))
        self.assertEqual(self.client.get(self._url(), **HDR(other)).status_code, 404)

    def test_image_access_reuses_existing_signed_url_mint_endpoint(self):
        doc = ReservationDocument.objects.create(
            hotel=self.hotel, reservation=self.res, occupant=None,
            doc_type="residence", number="IMG1",
            front_file=SimpleUploadedFile(
                "id.jpg", b"\xff\xd8\xff\xe0jpegbytes", content_type="image/jpeg"
            ),
        )
        self._files.append(doc.front_file)
        rows = {row["id"]: row for row in
                self.client.get(self._url(), **HDR(self.hotel)).data["results"]}
        row = rows[doc.id]
        self.assertTrue(row["has_front"])
        self.assertFalse(row["has_back"])
        self.assertIsNone(row["back_url"])
        # front_url points at the EXISTING reservation-document signed-URL mint
        # endpoint (no new file service).
        expected = reverse(
            "reservations:reservation-document-signed-url",
            kwargs={"doc_id": doc.id, "side": "front"},
        )
        self.assertIsNotNone(row["front_url"])
        self.assertTrue(row["front_url"].endswith(expected))

    def test_expiry_is_always_null(self):
        r = self.client.get(self._url(), **HDR(self.hotel))
        for row in r.data["results"]:
            self.assertIsNone(row["expiry_date"])

    def test_pagination_is_real(self):
        # There are already 2 of this guest's docs; add a third.
        ReservationDocument.objects.create(
            hotel=self.hotel, reservation=self.res, occupant=None,
            doc_type="visa", number="EXTRA",
        )
        p1 = self.client.get(self._url(), {"page_size": 2}, **HDR(self.hotel))
        self.assertEqual(p1.data["count"], 3)
        self.assertEqual(len(p1.data["results"]), 2)
        p2 = self.client.get(
            self._url(), {"page_size": 2, "page": 2}, **HDR(self.hotel)
        )
        self.assertEqual(len(p2.data["results"]), 1)


class GuestChangeLogEndpointTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="Logged")
        from apps.guests.services import (
            block_guest,
            record_guest_created,
            record_guest_updated,
        )

        record_guest_created(self.guest, user=self.manager)
        record_guest_updated(
            self.guest, old_values={"full_name": "Old", "phone": ""},
            user=self.manager,
        )
        block_guest(self.guest, reason="stole the towels", user=self.manager)

    def _url(self, guest=None):
        return reverse("guests:guest-change-log", args=[(guest or self.guest).id])

    def test_permission_required(self):
        staff = add_member(self.hotel, "no@x.com", perms=["rooms.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 403)
        viewer = add_member(self.hotel, "yes@x.com", perms=["guests.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(self.client.get(self._url(), **HDR(self.hotel)).status_code, 200)

    def test_tenant_isolation_other_hotel_guest_404(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(User.objects.get(email="om@x.com"))
        self.assertEqual(self.client.get(self._url(), **HDR(other)).status_code, 404)

    def test_lists_guest_events_newest_first(self):
        r = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r.status_code, 200)
        types = [row["event_type"] for row in r.data["results"]]
        self.assertEqual(
            set(types), {"guest.created", "guest.updated", "guest.blocked"}
        )
        # Newest first: the block (last recorded) leads.
        self.assertEqual(r.data["results"][0]["event_type"], "guest.blocked")

    def test_only_this_guests_events(self):
        from apps.guests.services import record_guest_created

        other_guest = Guest.objects.create(hotel=self.hotel, full_name="Another")
        record_guest_created(other_guest, user=self.manager)
        r = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r.data["count"], 3)  # only self.guest's events

    def test_block_reason_gated_behind_guests_block(self):
        # A plain viewer (no guests.block) must NOT see the block reason.
        viewer = add_member(self.hotel, "v@x.com", perms=["guests.view"])
        self.client.force_authenticate(viewer)
        rows = self.client.get(self._url(), **HDR(self.hotel)).data["results"]
        blocked = next(row for row in rows if row["event_type"] == "guest.blocked")
        self.assertIsNone(blocked["message"])
        # A non-block event keeps its message for the same viewer.
        updated = next(row for row in rows if row["event_type"] == "guest.updated")
        self.assertIsNotNone(updated["message"])
        # A block-permission holder sees the reason.
        blocker = add_member(
            self.hotel, "b@x.com", perms=["guests.view", "guests.block"]
        )
        self.client.force_authenticate(blocker)
        rows = self.client.get(self._url(), **HDR(self.hotel)).data["results"]
        blocked = next(row for row in rows if row["event_type"] == "guest.blocked")
        self.assertEqual(blocked["message"], "stole the towels")

    def test_pagination_is_real(self):
        p1 = self.client.get(self._url(), {"page_size": 2}, **HDR(self.hotel))
        self.assertEqual(p1.data["count"], 3)
        self.assertEqual(len(p1.data["results"]), 2)
        p2 = self.client.get(
            self._url(), {"page_size": 2, "page": 2}, **HDR(self.hotel)
        )
        self.assertEqual(len(p2.data["results"]), 1)


# --------------------------------------------------------------------------- #
# Dead-code removal guard (Decision 4)                                          #
# --------------------------------------------------------------------------- #


class DeadCodeRemovalGuardTests(SimpleTestCase):
    """`find_blocked_guest_matching` was the old raw reservation-side ban guard.
    The central identity service (``resolve_or_create_guest``) now runs the ban
    check on the normalized identity for every path, so the function was deleted
    (Decision 4). This guard proves the symbol cannot silently return — if anyone
    re-adds it, this test fails."""

    def test_symbol_is_gone(self):
        import apps.guests.services as guests_services

        self.assertFalse(
            hasattr(guests_services, "find_blocked_guest_matching"),
            "find_blocked_guest_matching must stay deleted (Decision 4)",
        )
