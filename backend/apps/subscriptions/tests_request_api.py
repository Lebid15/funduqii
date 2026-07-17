"""API tests for the subscription change-request endpoints (§8.4/§8.5).

Verifies authorization (hotel RBAC + platform-owner gate), tenant isolation, the
suspended-hotel rule, and the hotel->owner happy path end to end.
"""
from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.rbac.services import grant_permission
from apps.subscriptions.models import (
    ChangeRequestKind,
    ChangeRequestStatus,
    HotelSubscription,
    SubscriptionChangeRequest,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

STRONG = "StrongPass!234"


def make_owner():
    return User.objects.create_user(
        email="owner@platform.local",
        password=STRONG,
        full_name="Owner",
        account_type=AccountType.PLATFORM_OWNER,
    )


def make_manager(hotel, email="mgr@hotel.local"):
    user = User.objects.create_user(email=email, password=STRONG, full_name="Mgr")
    HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=MembershipType.MANAGER, is_active=True
    )
    return user


def make_staff(hotel, email="staff@hotel.local", perms=()):
    user = User.objects.create_user(email=email, password=STRONG, full_name="Staff")
    m = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=MembershipType.STAFF, is_active=True
    )
    for code in perms:
        grant_permission(m, code)
    return user


def make_plan(slug="basic", **kw):
    defaults = dict(
        name=slug.title(), slug=slug, price=Decimal("49.00"),
        currency="USD", billing_cycle="monthly", trial_days=14, room_limit=10,
    )
    defaults.update(kw)
    return SubscriptionPlan.objects.create(**defaults)


class HotelRequestApiTests(APITestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name="H", slug="h", status=HotelStatus.ACTIVE)
        self.manager = make_manager(self.hotel)
        self.plan = make_plan("basic")
        self.headers = {"HTTP_X_HOTEL_ID": str(self.hotel.id)}

    def test_unauthenticated_denied(self):
        res = self.client.get(reverse("hotel:subscription-requests"), **self.headers)
        self.assertEqual(res.status_code, 401)

    def test_staff_without_update_cannot_submit(self):
        staff = make_staff(self.hotel, perms=("settings.view",))
        self.client.force_authenticate(staff)
        res = self.client.post(
            reverse("hotel:subscription-requests"),
            {"kind": ChangeRequestKind.NEW_SUBSCRIPTION, "requested_plan": self.plan.id},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 403)

    def test_manager_submits_and_lists(self):
        self.client.force_authenticate(self.manager)
        res = self.client.post(
            reverse("hotel:subscription-requests"),
            {"kind": ChangeRequestKind.NEW_SUBSCRIPTION, "requested_plan": self.plan.id},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["status"], ChangeRequestStatus.UNDER_REVIEW)
        lst = self.client.get(reverse("hotel:subscription-requests"), **self.headers)
        self.assertEqual(len(lst.data), 1)

    def test_available_plans_reports_state(self):
        self.client.force_authenticate(self.manager)
        res = self.client.get(reverse("hotel:subscription-plans"), **self.headers)
        self.assertEqual(res.status_code, 200)
        states = {p["id"]: p["state"] for p in res.data["plans"]}
        self.assertEqual(states[self.plan.id], "available")

    def test_suspended_hotel_cannot_submit(self):
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save(update_fields=["status"])
        self.client.force_authenticate(self.manager)
        res = self.client.post(
            reverse("hotel:subscription-requests"),
            {"kind": ChangeRequestKind.NEW_SUBSCRIPTION, "requested_plan": self.plan.id},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")

    def test_cannot_cancel_another_hotels_request(self):
        other = Hotel.objects.create(name="O", slug="o", status=HotelStatus.ACTIVE)
        req = SubscriptionChangeRequest.objects.create(
            hotel=other, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.plan
        )
        self.client.force_authenticate(self.manager)
        res = self.client.post(
            reverse("hotel:subscription-request-cancel", args=[req.id]), **self.headers
        )
        self.assertEqual(res.status_code, 404)  # tenant isolation


class PlatformRequestApiTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.hotel = Hotel.objects.create(name="H", slug="h", status=HotelStatus.ACTIVE)
        self.manager = make_manager(self.hotel)
        self.plan = make_plan("pro", price=Decimal("99.00"), room_limit=50)
        self.req = SubscriptionChangeRequest.objects.create(
            hotel=self.hotel,
            kind=ChangeRequestKind.NEW_SUBSCRIPTION,
            requested_plan=self.plan,
        )

    def test_hotel_user_cannot_reach_owner_review(self):
        self.client.force_authenticate(self.manager)
        res = self.client.get(reverse("platform:subscription-request-list"))
        self.assertEqual(res.status_code, 403)

    def test_owner_lists_requests(self):
        self.client.force_authenticate(self.owner)
        res = self.client.get(reverse("platform:subscription-request-list"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["hotel"], self.hotel.id)

    def test_reject_requires_reason(self):
        self.client.force_authenticate(self.owner)
        res = self.client.post(
            reverse("platform:subscription-request-reject", args=[self.req.id]),
            {},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_accept_then_execute_activates_subscription(self):
        self.client.force_authenticate(self.owner)
        acc = self.client.post(
            reverse("platform:subscription-request-accept", args=[self.req.id]),
            {},
            format="json",
        )
        self.assertEqual(acc.status_code, 200)
        self.assertEqual(acc.data["status"], ChangeRequestStatus.ACCEPTED)
        exe = self.client.post(
            reverse("platform:subscription-request-execute", args=[self.req.id]),
            {"payment_amount": "99.00", "payment_method": "cash"},
            format="json",
        )
        self.assertEqual(exe.status_code, 200, exe.content)
        self.assertEqual(exe.data["status"], ChangeRequestStatus.EXECUTED)
        live = HotelSubscription.objects.get(
            hotel=self.hotel, status=SubscriptionStatus.ACTIVE
        )
        self.assertEqual(live.plan_id, self.plan.id)

    def test_execute_before_accept_conflicts(self):
        self.client.force_authenticate(self.owner)
        res = self.client.post(
            reverse("platform:subscription-request-execute", args=[self.req.id]),
            {},
            format="json",
        )
        self.assertEqual(res.status_code, 409)
