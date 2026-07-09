"""Phase 16 tests — platform owner panel completion.

Covers: access separation, the dashboard, hotel status lifecycle
(activate/suspend-with-reason/unsuspend, no hard delete), plan completion
(Decimal prices, deactivate-not-delete), the subscription lifecycle
(trial once-only, manual paid activation, renew, cancel, expire, preserved
history), manual platform payments (void-not-delete, separate from hotel
finance), the public-site settings (owner-only write, safe public read),
and the hotel-console subscription state.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.notifications.models import ActivityEvent
from apps.subscriptions.models import (
    HotelSubscription,
    PlatformSubscriptionPayment,
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
        user=user, hotel=hotel, membership_type=MembershipType.MANAGER
    )
    return user


def make_plan(**kw):
    defaults = dict(
        name="Basic",
        slug=kw.pop("slug", "basic"),
        price=Decimal("49.00"),
        currency="USD",
        billing_cycle="monthly",
        trial_days=14,
    )
    defaults.update(kw)
    return SubscriptionPlan.objects.create(**defaults)


class PlatformAccessTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.hotel = Hotel.objects.create(name="H", slug="h", status=HotelStatus.ACTIVE)
        self.manager = make_manager(self.hotel)

    def test_unauthenticated_denied(self):
        for name in ("platform:dashboard", "platform:public-site-settings"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 401)

    def test_hotel_manager_denied_platform_apis(self):
        self.client.force_authenticate(self.manager)
        for name in (
            "platform:dashboard",
            "platform:hotel-list",
            "platform:plan-list",
            "platform:subscription-list",
            "platform:payment-list",
            "platform:public-site-settings",
        ):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_owner_allowed(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(
            self.client.get(reverse("platform:dashboard")).status_code, 200
        )

    def test_owner_not_hotel_member_cannot_use_hotel_apis(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get(
            reverse("reservations:reservation-list"),
            HTTP_X_HOTEL_ID=str(self.hotel.id),
        )
        self.assertEqual(r.status_code, 403)


class DashboardTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.client.force_authenticate(self.owner)
        self.plan_m = make_plan(slug="m", price=Decimal("50.00"))
        self.plan_y = make_plan(
            slug="y", price=Decimal("120.00"), billing_cycle="yearly"
        )
        self.h1 = Hotel.objects.create(name="A", slug="a", status=HotelStatus.ACTIVE)
        self.h2 = Hotel.objects.create(name="B", slug="b", status=HotelStatus.SUSPENDED)
        now = timezone.now()
        HotelSubscription.objects.create(
            hotel=self.h1,
            plan=self.plan_m,
            status=SubscriptionStatus.ACTIVE,
            ends_at=now + datetime.timedelta(days=5),
        )
        HotelSubscription.objects.create(
            hotel=self.h2,
            plan=self.plan_y,
            status=SubscriptionStatus.ACTIVE,
            ends_at=now + datetime.timedelta(days=300),
        )

    def get(self):
        return self.client.get(reverse("platform:dashboard")).data

    def test_counts(self):
        data = self.get()
        self.assertEqual(data["total_hotels"], 2)
        self.assertEqual(data["active_hotels"], 1)
        self.assertEqual(data["suspended_hotels"], 1)
        self.assertEqual(data["paid_hotels"], 2)
        self.assertEqual(data["trial_hotels"], 0)
        self.assertEqual(data["total_plans"], 2)
        self.assertEqual(data["expiring_soon_subscriptions"], 1)

    def test_revenue_estimate_decimal_and_naming(self):
        data = self.get()
        # 50 monthly + 120/12=10 yearly-normalized = 60.00 USD, Decimal string.
        self.assertEqual(
            data["estimated_monthly_recurring_revenue"], {"USD": "60.00"}
        )
        # The figure is never called profit anywhere in the payload.
        self.assertNotIn("profit", str(data).lower())

    def test_recent_lists_present(self):
        data = self.get()
        self.assertEqual(len(data["recent_hotels"]), 2)
        self.assertTrue(len(data["recent_subscription_events"]) >= 2)


class HotelLifecycleTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.client.force_authenticate(self.owner)
        self.hotel = Hotel.objects.create(name="H", slug="h")  # setup

    def test_activate_from_setup(self):
        r = self.client.post(reverse("platform:hotel-activate", args=[self.hotel.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "active")
        self.assertEqual(r.data["status_changed_by"], self.owner.email)

    def test_suspend_requires_reason(self):
        self.hotel.status = HotelStatus.ACTIVE
        self.hotel.save(update_fields=["status"])
        url = reverse("platform:hotel-suspend", args=[self.hotel.id])
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        r = self.client.post(url, {"reason": "Unpaid invoices"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "suspended")
        self.assertEqual(r.data["suspension_reason"], "Unpaid invoices")

    def test_suspend_records_activity_event(self):
        self.hotel.status = HotelStatus.ACTIVE
        self.hotel.save(update_fields=["status"])
        self.client.post(
            reverse("platform:hotel-suspend", args=[self.hotel.id]),
            {"reason": "abuse"},
        )
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="hotel.suspended"
            ).exists()
        )

    def test_unsuspend(self):
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save(update_fields=["status"])
        r = self.client.post(reverse("platform:hotel-unsuspend", args=[self.hotel.id]))
        self.assertEqual(r.data["status"], "active")
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="hotel.unsuspended"
            ).exists()
        )

    def test_no_hard_delete_route(self):
        r = self.client.delete(reverse("platform:hotel-detail", args=[self.hotel.id]))
        self.assertEqual(r.status_code, 405)

    def test_enriched_hotel_payload(self):
        r = self.client.get(reverse("platform:hotel-detail", args=[self.hotel.id]))
        for key in (
            "trial_used",
            "public_is_listed",
            "public_booking_enabled",
            "rooms_count",
            "staff_count",
            "reservations_count",
        ):
            self.assertIn(key, r.data)


class PlanTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.client.force_authenticate(self.owner)

    def test_create_with_phase16_fields(self):
        r = self.client.post(
            reverse("platform:plan-list"),
            {
                "name": "Pro",
                "slug": "pro",
                "price": "99.00",
                "price_yearly": "990.00",
                "currency": "USD",
                "billing_cycle": "monthly",
                "is_public": True,
                "max_public_bookings_per_month": 500,
                "notes": "internal note",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["price_yearly"], "990.00")
        self.assertEqual(r.data["max_public_bookings_per_month"], 500)

    def test_used_plan_cannot_be_deleted_but_can_deactivate(self):
        plan = make_plan()
        hotel = Hotel.objects.create(name="H", slug="h", status=HotelStatus.ACTIVE)
        HotelSubscription.objects.create(
            hotel=hotel, plan=plan, status=SubscriptionStatus.ACTIVE
        )
        r = self.client.delete(reverse("platform:plan-detail", args=[plan.id]))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "plan_in_use")
        r = self.client.post(reverse("platform:plan-deactivate", args=[plan.id]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["is_active"])
        r = self.client.post(reverse("platform:plan-activate", args=[plan.id]))
        self.assertTrue(r.data["is_active"])


class SubscriptionLifecycleTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.client.force_authenticate(self.owner)
        self.plan = make_plan()
        self.hotel = Hotel.objects.create(
            name="H", slug="h", status=HotelStatus.ACTIVE
        )

    def start_trial(self):
        return self.client.post(
            reverse("platform:hotel-start-trial", args=[self.hotel.id]),
            {"plan": self.plan.id},
            format="json",
        )

    def activate_paid(self, **extra):
        return self.client.post(
            reverse("platform:hotel-activate-paid", args=[self.hotel.id]),
            {"plan": self.plan.id, **extra},
            format="json",
        )

    def test_trial_first_time_only(self):
        self.assertEqual(self.start_trial().status_code, 201)
        # Cancel it, then try again — the one-time rule survives cancellation.
        self.client.post(
            reverse("platform:hotel-cancel-subscription", args=[self.hotel.id]), {}
        )
        r = self.start_trial()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "trial_already_used")

    def test_no_trial_after_paid_subscription(self):
        # The free trial can only be the FIRST subscription: a hotel whose
        # paid subscription ended (cancelled here) is refused a trial.
        self.assertEqual(self.activate_paid().status_code, 201)
        self.client.post(
            reverse("platform:hotel-cancel-subscription", args=[self.hotel.id]), {}
        )
        r = self.start_trial()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "trial_already_used")

    def test_activate_paid_with_manual_payment(self):
        r = self.activate_paid(
            payment_amount="49.00", payment_method="bank_transfer",
            payment_reference="TRX-100",
        )
        self.assertEqual(r.status_code, 201)
        payment = PlatformSubscriptionPayment.objects.get(hotel=self.hotel)
        self.assertEqual(payment.amount, Decimal("49.00"))
        self.assertEqual(payment.method, "bank_transfer")
        self.assertEqual(payment.recorded_by, self.owner)

    def test_renew_extends_end(self):
        self.activate_paid()
        sub = HotelSubscription.objects.get(hotel=self.hotel)
        old_end = sub.ends_at
        r = self.client.post(
            reverse("platform:hotel-renew", args=[self.hotel.id]), {}, format="json"
        )
        self.assertEqual(r.status_code, 200)
        sub.refresh_from_db()
        self.assertGreater(sub.ends_at, old_end)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="subscription.renewed"
            ).exists()
        )

    def test_cancel_and_expire_preserve_history(self):
        self.start_trial()
        self.client.post(
            reverse("platform:hotel-cancel-subscription", args=[self.hotel.id]), {}
        )
        self.activate_paid()
        self.client.post(
            reverse("platform:hotel-expire-subscription", args=[self.hotel.id]), {}
        )
        history = self.client.get(
            reverse("platform:hotel-subscription-history", args=[self.hotel.id])
        ).data
        self.assertEqual(len(history), 2)
        statuses = {row["status"] for row in history}
        self.assertEqual(statuses, {"cancelled", "expired"})

    def test_lifecycle_records_activity_events(self):
        self.start_trial()
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="subscription.trial_started"
            ).exists()
        )
        self.activate_paid()
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="subscription.activated"
            ).exists()
        )
        self.client.post(
            reverse("platform:hotel-expire-subscription", args=[self.hotel.id]), {}
        )
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="subscription.expired"
            ).exists()
        )

    def test_expiring_soon_filter(self):
        self.activate_paid(
            ends_at=(timezone.now() + datetime.timedelta(days=3)).isoformat()
        )
        r = self.client.get(reverse("platform:subscription-list") + "?expiring=soon")
        self.assertEqual(r.data["count"], 1)

    def test_no_payment_gateway_endpoints(self):
        from django.urls import NoReverseMatch

        for name in ("checkout", "stripe", "paypal", "gateway"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"platform:{name}")


class PlatformPaymentTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.client.force_authenticate(self.owner)
        self.hotel = Hotel.objects.create(
            name="H", slug="h", status=HotelStatus.ACTIVE
        )

    def test_create_and_void_not_delete(self):
        r = self.client.post(
            reverse("platform:payment-list"),
            {"hotel": self.hotel.id, "amount": "100.00", "method": "cash"},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        pid = r.data["id"]
        # Void requires a reason and never deletes.
        void_url = reverse("platform:payment-void", args=[pid])
        self.assertEqual(self.client.post(void_url, {}).status_code, 400)
        r = self.client.post(void_url, {"reason": "typo"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["is_voided"])
        self.assertEqual(PlatformSubscriptionPayment.objects.count(), 1)

    def test_zero_amount_rejected(self):
        r = self.client.post(
            reverse("platform:payment-list"),
            {"hotel": self.hotel.id, "amount": "0.00", "method": "cash"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_not_linked_to_hotel_finance(self):
        from apps.finance.models import Payment

        self.client.post(
            reverse("platform:payment-list"),
            {"hotel": self.hotel.id, "amount": "10.00", "method": "manual"},
            format="json",
        )
        self.assertEqual(Payment.objects.count(), 0)


class PublicSiteSettingsTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.hotel = Hotel.objects.create(
            name="H", slug="h", status=HotelStatus.ACTIVE
        )
        self.manager = make_manager(self.hotel)
        self.url = reverse("platform:public-site-settings")

    def test_owner_reads_and_updates(self):
        self.client.force_authenticate(self.owner)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        r = self.client.patch(
            self.url,
            {
                "show_trial_button": False,
                "hero_title": {"ar": "عنوان", "en": "Title", "tr": "Başlık"},
                "public_email": "hello@funduqii.com",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["show_trial_button"])
        self.assertEqual(r.data["hero_title"]["en"], "Title")

    def test_hotel_staff_denied(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.patch(self.url, {}).status_code, 403)

    def test_unsafe_url_rejected(self):
        self.client.force_authenticate(self.owner)
        r = self.client.patch(
            self.url,
            {"hero_primary_button_url": "javascript:alert(1)"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_public_read_endpoint_safe_subset(self):
        self.client.force_authenticate(self.owner)
        self.client.patch(
            self.url,
            {"public_phone": "+90 555", "show_book_now_button": False},
            format="json",
        )
        self.client.force_authenticate()  # anonymous
        r = self.client.get(reverse("public_site:site-settings"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["contact"]["phone"], "+90 555")
        self.assertFalse(r.data["header"]["show_book_now_button"])
        blob = str(r.data).lower()
        for forbidden in ("maintenance_mode", "default_trial_days", "secret"):
            self.assertNotIn(forbidden, blob)
