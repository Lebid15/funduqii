"""Authentication, platform-owner, and regression tests (Phase 2)."""
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.tenancy.models import Hotel


class AuthTokenTests(APITestCase):
    def setUp(self):
        self.password = "StrongPass!234"
        self.user = User.objects.create_user(
            email="staff@example.com", password=self.password, full_name="Staff One"
        )

    def test_obtain_token_success(self):
        res = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "staff@example.com", "password": self.password},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)

    def test_obtain_token_wrong_password(self):
        res = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "staff@example.com", "password": "wrong"},
            format="json",
        )
        self.assertEqual(res.status_code, 401)

    def test_inactive_user_cannot_obtain_token(self):
        self.user.is_active = False
        self.user.save()
        res = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "staff@example.com", "password": self.password},
            format="json",
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data["code"], "no_active_account")

    def test_refresh_token_works(self):
        obtain = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "staff@example.com", "password": self.password},
            format="json",
        )
        refresh = obtain.data["refresh"]
        res = self.client.post(
            reverse("token_refresh"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)

    def test_me_requires_authentication(self):
        res = self.client.get(reverse("auth_me"))
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data["code"], "not_authenticated")

    def test_me_returns_current_user(self):
        self.client.force_authenticate(self.user)
        res = self.client.get(reverse("auth_me"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["user"]["email"], "staff@example.com")
        self.assertFalse(res.data["user"]["is_platform_owner"])
        self.assertEqual(res.data["memberships"], [])
        self.assertIsNone(res.data["current_hotel"])

    def test_end_to_end_token_then_me(self):
        obtain = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "staff@example.com", "password": self.password},
            format="json",
        )
        access = obtain.data["access"]
        res = self.client.get(
            reverse("auth_me"), HTTP_AUTHORIZATION=f"Bearer {access}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["user"]["email"], "staff@example.com")


class PlatformOwnerTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_platform_owner(
            email="owner@example.com", password="StrongPass!234", full_name="Owner"
        )
        self.hotel_user = User.objects.create_user(
            email="hotel@example.com", password="StrongPass!234", full_name="Hotel User"
        )

    def test_platform_owner_flag(self):
        self.assertTrue(self.owner.is_platform_owner)
        self.assertEqual(self.owner.account_type, AccountType.PLATFORM_OWNER)
        self.assertFalse(self.hotel_user.is_platform_owner)

    def test_platform_ping_allowed_for_owner(self):
        self.client.force_authenticate(self.owner)
        res = self.client.get(reverse("platform-ping"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["scope"], "platform")

    def test_platform_ping_forbidden_for_hotel_user(self):
        self.client.force_authenticate(self.hotel_user)
        res = self.client.get(reverse("platform-ping"))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "permission_denied")

    def test_platform_ping_requires_authentication(self):
        res = self.client.get(reverse("platform-ping"))
        self.assertEqual(res.status_code, 401)

    def test_owner_has_no_hotel_permissions_without_membership(self):
        from apps.rbac.services import has_hotel_permission

        hotel = Hotel.objects.create(name="Hotel X", slug="hotel-x")
        self.assertFalse(
            has_hotel_permission(self.owner, hotel, "reservations.view")
        )


class LogoutTests(APITestCase):
    def setUp(self):
        self.password = "StrongPass!234"
        self.user = User.objects.create_user(
            email="logout@example.com", password=self.password, full_name="Logout User"
        )

    def test_logout_blacklists_refresh_token(self):
        obtain = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "logout@example.com", "password": self.password},
            format="json",
        )
        refresh = obtain.data["refresh"]
        self.client.force_authenticate(self.user)
        res = self.client.post(reverse("auth_logout"), {"refresh": refresh}, format="json")
        self.assertEqual(res.status_code, 205)

        # The blacklisted refresh token can no longer be used.
        self.client.force_authenticate(user=None)
        again = self.client.post(
            reverse("token_refresh"), {"refresh": refresh}, format="json"
        )
        self.assertEqual(again.status_code, 401)

    def test_logout_requires_refresh_token(self):
        self.client.force_authenticate(self.user)
        res = self.client.post(reverse("auth_logout"), {}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_request")


class RegressionTests(APITestCase):
    def test_health_endpoint_still_works(self):
        res = self.client.get(reverse("health"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, {"status": "ok", "service": "funduqii-api"})

    def test_no_operational_endpoints_exist(self):
        # These business sections belong to later phases and must not be routed.
        for path in (
            "/api/reservations/",
            "/api/rooms/",
            "/api/guests/",
            "/api/payments/",
            "/api/hotels/",
            "/api/subscriptions/",
        ):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 404, f"{path} should not be routed yet")
