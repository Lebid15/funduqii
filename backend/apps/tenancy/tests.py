"""Tenant context & membership isolation tests (Phase 2)."""
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.tenancy.models import Hotel, HotelMembership, MembershipType


class HotelContextTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="member@example.com", password="StrongPass!234", full_name="Member"
        )
        self.hotel_a = Hotel.objects.create(name="Hotel A", slug="hotel-a")
        self.hotel_b = Hotel.objects.create(name="Hotel B", slug="hotel-b")
        self.membership = HotelMembership.objects.create(
            user=self.user,
            hotel=self.hotel_a,
            membership_type=MembershipType.MANAGER,
            is_primary_manager=True,
        )
        self.url = reverse("auth_context")
        self.client.force_authenticate(self.user)

    def test_context_requires_hotel_header(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "hotel_context_required")

    def test_context_for_own_hotel(self):
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_a.id))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["hotel_id"], self.hotel_a.id)
        self.assertEqual(res.data["membership_type"], "manager")

    def test_context_for_other_hotel_is_denied(self):
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_b.id))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "no_hotel_membership")

    def test_unknown_hotel_id(self):
        res = self.client.get(self.url, HTTP_X_HOTEL_ID="99999")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data["code"], "hotel_not_found")

    def test_non_numeric_hotel_id(self):
        res = self.client.get(self.url, HTTP_X_HOTEL_ID="not-a-number")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data["code"], "hotel_not_found")

    def test_inactive_membership_is_denied(self):
        self.membership.is_active = False
        self.membership.save()
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_a.id))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "membership_inactive")

    def test_inactive_user_is_denied(self):
        self.user.is_active = False
        self.user.save()
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_a.id))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "user_inactive")


class MembershiplessUserTests(APITestCase):
    def test_user_without_membership_cannot_use_hotel_context(self):
        user = User.objects.create_user(
            email="lonely@example.com", password="StrongPass!234", full_name="Lonely"
        )
        hotel = Hotel.objects.create(name="Hotel C", slug="hotel-c")
        self.client.force_authenticate(user)
        res = self.client.get(reverse("auth_context"), HTTP_X_HOTEL_ID=str(hotel.id))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "no_hotel_membership")
