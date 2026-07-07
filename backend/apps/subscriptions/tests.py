"""Model + service tests for the subscriptions domain (Phase 3)."""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.common.exceptions import (
    ConflictingSubscription,
    InvalidSubscriptionTransition,
    TrialAlreadyUsed,
)
from apps.subscriptions import services
from apps.subscriptions.models import (
    HotelSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel


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


class SubscriptionServiceTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name="Sea View", slug="sea-view")
        self.plan = make_plan()

    def test_start_trial_creates_trial_subscription(self):
        sub = services.start_trial(self.hotel, self.plan)
        self.assertEqual(sub.status, SubscriptionStatus.TRIAL)
        self.assertIsNotNone(sub.trial_ends_at)
        self.assertIsNotNone(sub.starts_at)

    def test_trial_cannot_be_granted_twice(self):
        services.start_trial(self.hotel, self.plan)
        services.expire_subscription(services.get_current_subscription(self.hotel))
        # Even after the first trial expired, a second trial is refused.
        with self.assertRaises(TrialAlreadyUsed):
            services.start_trial(self.hotel, self.plan)

    def test_trial_blocked_when_live_subscription_exists(self):
        services.activate_subscription(self.hotel, self.plan)
        with self.assertRaises(ConflictingSubscription):
            services.start_trial(self.hotel, self.plan)

    def test_activate_paid_sets_end_date_from_cycle(self):
        sub = services.activate_subscription(self.hotel, self.plan)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertIsNotNone(sub.ends_at)

    def test_activate_upgrades_running_trial(self):
        services.start_trial(self.hotel, self.plan)
        active = services.activate_subscription(self.hotel, self.plan)
        # The trial is closed; only one live subscription remains.
        live = HotelSubscription.objects.filter(
            hotel=self.hotel,
            status__in=[
                SubscriptionStatus.TRIAL,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE,
            ],
        )
        self.assertEqual(live.count(), 1)
        self.assertEqual(live.first().id, active.id)

    def test_cancel_sets_cancelled_at(self):
        sub = services.activate_subscription(self.hotel, self.plan)
        cancelled = services.cancel_subscription(sub)
        self.assertEqual(cancelled.status, SubscriptionStatus.CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)

    def test_cannot_cancel_terminal_subscription(self):
        sub = services.activate_subscription(self.hotel, self.plan)
        services.cancel_subscription(sub)
        with self.assertRaises(InvalidSubscriptionTransition):
            services.cancel_subscription(sub)

    def test_db_constraint_blocks_two_live_subscriptions(self):
        services.activate_subscription(self.hotel, self.plan)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                HotelSubscription.objects.create(
                    hotel=self.hotel,
                    plan=self.plan,
                    status=SubscriptionStatus.ACTIVE,
                )


class SubscriptionPlanModelTests(TestCase):
    def test_is_in_use_reflects_subscriptions(self):
        hotel = Hotel.objects.create(name="Palm", slug="palm")
        plan = make_plan()
        self.assertFalse(plan.is_in_use)
        services.activate_subscription(hotel, plan)
        self.assertTrue(plan.is_in_use)
