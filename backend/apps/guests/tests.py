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
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Guest.objects.filter(pk=gid).exists())
