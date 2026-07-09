"""API tests for the platform-owner surface (Phase 3).

Covers authorization (unauthenticated / hotel-user / owner), the hotels, plans,
subscriptions and settings endpoints, the trial-once and no-conflict rules,
pagination, and regressions (no forbidden business routes; auth + health still
work).
"""
from __future__ import annotations

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.subscriptions.models import (
    HotelSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel, HotelMembership, MembershipType


def make_plan(**kwargs) -> SubscriptionPlan:
    defaults = {
        "name": "Standard",
        "slug": "standard",
        "price": "49.00",
        "billing_cycle": "monthly",
        "trial_days": 14,
    }
    defaults.update(kwargs)
    return SubscriptionPlan.objects.create(**defaults)


class PlatformAuthorizationTests(APITestCase):
    """Only the platform owner may reach /api/v1/platform/ endpoints."""

    def setUp(self):
        self.owner = User.objects.create_platform_owner(
            email="owner@example.com", password="StrongPass!234", full_name="Owner"
        )
        self.hotel_user = User.objects.create_user(
            email="staff@example.com", password="StrongPass!234", full_name="Staff"
        )

    def test_unauthenticated_is_rejected(self):
        res = self.client.get(reverse("platform:overview"))
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data["code"], "not_authenticated")

    def test_hotel_user_is_forbidden(self):
        self.client.force_authenticate(self.hotel_user)
        for name in ("platform:overview", "platform:hotel-list", "platform:plan-list"):
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 403, name)

    def test_owner_can_access_overview(self):
        self.client.force_authenticate(self.owner)
        res = self.client.get(reverse("platform:overview"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("hotels", res.data)
        self.assertIn("subscriptions", res.data)
        self.assertIn("recent_hotels", res.data)


class HotelManagementTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_platform_owner(
            email="owner@example.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(self.owner)

    def test_list_hotels_is_paginated(self):
        for i in range(3):
            Hotel.objects.create(name=f"Hotel {i}", slug=f"hotel-{i}")
        res = self.client.get(reverse("platform:hotel-list"))
        self.assertEqual(res.status_code, 200)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, res.data)
        self.assertEqual(res.data["count"], 3)

    def test_create_minimal_hotel(self):
        res = self.client.post(
            reverse("platform:hotel-list"),
            {"name": "New Hotel", "slug": "new-hotel"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["slug"], "new-hotel")
        self.assertEqual(res.data["status"], "setup")
        self.assertIsNone(res.data["primary_manager"])

    def test_create_hotel_with_primary_manager(self):
        res = self.client.post(
            reverse("platform:hotel-list"),
            {
                "name": "Managed Hotel",
                "slug": "managed-hotel",
                "manager": {
                    "email": "mgr@example.com",
                    "full_name": "Manager One",
                    "password": "StrongPass!234",
                },
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertIsNotNone(res.data["primary_manager"])
        self.assertEqual(res.data["primary_manager"]["email"], "mgr@example.com")
        membership = HotelMembership.objects.get(user__email="mgr@example.com")
        self.assertTrue(membership.is_primary_manager)
        self.assertEqual(membership.membership_type, MembershipType.MANAGER)

    def test_update_hotel_status(self):
        # Phase 16: status is NOT patchable — it changes only through the
        # audited actions (activate/suspend/unsuspend).
        hotel = Hotel.objects.create(name="Hotel", slug="hotel")
        res = self.client.patch(
            reverse("platform:hotel-detail", args=[hotel.id]),
            {"status": "active"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        hotel.refresh_from_db()
        self.assertEqual(hotel.status, "setup")  # unchanged via PATCH
        res = self.client.post(
            reverse("platform:hotel-activate", args=[hotel.id])
        )
        self.assertEqual(res.status_code, 200)
        hotel.refresh_from_db()
        self.assertEqual(hotel.status, "active")

    def test_hotel_search_filter(self):
        Hotel.objects.create(name="Beach Resort", slug="beach")
        Hotel.objects.create(name="Mountain Lodge", slug="mountain")
        res = self.client.get(reverse("platform:hotel-list"), {"search": "beach"})
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["slug"], "beach")

    def test_set_manager_on_existing_hotel(self):
        hotel = Hotel.objects.create(name="Hotel", slug="hotel")
        res = self.client.post(
            reverse("platform:hotel-manager", args=[hotel.id]),
            {
                "email": "boss@example.com",
                "full_name": "Boss",
                "password": "StrongPass!234",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["primary_manager"]["email"], "boss@example.com")


class PlanManagementTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_platform_owner(
            email="owner@example.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(self.owner)

    def test_create_plan(self):
        res = self.client.post(
            reverse("platform:plan-list"),
            {
                "name": "Pro",
                "slug": "pro",
                "price": "99.00",
                "currency": "USD",
                "billing_cycle": "monthly",
                "trial_days": 14,
                "feature_codes": ["reservations", "reports"],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["slug"], "pro")
        self.assertTrue(res.data["is_active"])

    def test_update_plan_toggle_active(self):
        plan = make_plan()
        res = self.client.patch(
            reverse("platform:plan-detail", args=[plan.id]),
            {"is_active": False},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        plan.refresh_from_db()
        self.assertFalse(plan.is_active)

    def test_feature_codes_must_be_list_of_strings(self):
        res = self.client.post(
            reverse("platform:plan-list"),
            {"name": "Bad", "slug": "bad", "feature_codes": [1, 2]},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_can_delete_unused_plan(self):
        plan = make_plan(slug="unused")
        res = self.client.delete(reverse("platform:plan-detail", args=[plan.id]))
        self.assertEqual(res.status_code, 204)
        self.assertFalse(SubscriptionPlan.objects.filter(id=plan.id).exists())

    def test_cannot_hard_delete_used_plan(self):
        plan = make_plan(slug="used")
        hotel = Hotel.objects.create(name="Hotel", slug="hotel")
        HotelSubscription.objects.create(
            hotel=hotel, plan=plan, status=SubscriptionStatus.ACTIVE
        )
        res = self.client.delete(reverse("platform:plan-detail", args=[plan.id]))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "plan_in_use")
        self.assertTrue(SubscriptionPlan.objects.filter(id=plan.id).exists())


class SubscriptionApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_platform_owner(
            email="owner@example.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(self.owner)
        self.hotel = Hotel.objects.create(name="Hotel", slug="hotel")
        self.plan = make_plan()

    def _create(self, **body):
        return self.client.post(
            reverse("platform:subscription-list"), body, format="json"
        )

    def test_assign_plan_via_trial(self):
        res = self._create(hotel=self.hotel.id, plan=self.plan.id, kind="trial")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "trial")
        self.assertIsNotNone(res.data["trial_ends_at"])

    def test_assign_plan_via_paid(self):
        res = self._create(hotel=self.hotel.id, plan=self.plan.id, kind="paid")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "active")

    def test_trial_cannot_be_granted_twice(self):
        self._create(hotel=self.hotel.id, plan=self.plan.id, kind="trial")
        # Expire the first trial, then try again — must be refused.
        sub = HotelSubscription.objects.get(hotel=self.hotel)
        self.client.patch(
            reverse("platform:subscription-detail", args=[sub.id]),
            {"status": "expired"},
            format="json",
        )
        res = self._create(hotel=self.hotel.id, plan=self.plan.id, kind="trial")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "trial_already_used")

    def test_no_conflicting_active_subscriptions(self):
        self._create(hotel=self.hotel.id, plan=self.plan.id, kind="trial")
        # A second trial while one is live is a conflict (trial-once triggers
        # first here, but the live-conflict rule is covered by the service test).
        res = self._create(hotel=self.hotel.id, plan=self.plan.id, kind="trial")
        self.assertEqual(res.status_code, 409)

    def test_paid_activation_upgrades_trial_without_conflict(self):
        self._create(hotel=self.hotel.id, plan=self.plan.id, kind="trial")
        res = self._create(hotel=self.hotel.id, plan=self.plan.id, kind="paid")
        self.assertEqual(res.status_code, 201)
        live = HotelSubscription.objects.filter(
            hotel=self.hotel,
            status__in=[
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE,
            ],
        )
        self.assertEqual(live.count(), 1)

    def test_filter_subscriptions_by_status(self):
        self._create(hotel=self.hotel.id, plan=self.plan.id, kind="trial")
        res = self.client.get(
            reverse("platform:subscription-list"), {"status": "trial"}
        )
        self.assertEqual(res.data["count"], 1)
        res2 = self.client.get(
            reverse("platform:subscription-list"), {"status": "active"}
        )
        self.assertEqual(res2.data["count"], 0)

    def test_cancel_subscription(self):
        self._create(hotel=self.hotel.id, plan=self.plan.id, kind="paid")
        sub = HotelSubscription.objects.get(hotel=self.hotel)
        res = self.client.patch(
            reverse("platform:subscription-detail", args=[sub.id]),
            {"status": "cancelled"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "cancelled")
        self.assertIsNotNone(res.data["cancelled_at"])


class PlatformSettingsTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_platform_owner(
            email="owner@example.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(self.owner)

    def test_get_settings_returns_singleton(self):
        res = self.client.get(reverse("platform:settings"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("platform_name", res.data)

    def test_patch_settings(self):
        res = self.client.patch(
            reverse("platform:settings"),
            {"platform_name": "My Platform", "default_trial_days": 30},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["platform_name"], "My Platform")
        self.assertEqual(res.data["default_trial_days"], 30)

    def test_hotel_user_cannot_read_settings(self):
        self.client.force_authenticate(
            User.objects.create_user(
                email="hu@example.com", password="StrongPass!234", full_name="HU"
            )
        )
        res = self.client.get(reverse("platform:settings"))
        self.assertEqual(res.status_code, 403)


class RegressionTests(APITestCase):
    """Phase-3 boundaries: no forbidden business routes; foundations intact."""

    def test_health_endpoint_still_works(self):
        res = self.client.get(reverse("health"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "ok")

    def test_auth_token_endpoint_still_works(self):
        User.objects.create_user(
            email="u@example.com", password="StrongPass!234", full_name="U"
        )
        res = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "u@example.com", "password": "StrongPass!234"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)

    def test_forbidden_reservation_route_does_not_exist(self):
        for path in (
            "/api/v1/reservations/",
            "/api/v1/rooms/",
            "/api/v1/guests/",
            "/api/v1/payments/",
        ):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 404, path)
