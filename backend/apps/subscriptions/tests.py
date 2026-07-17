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


class SubscriptionStateDatesTests(TestCase):
    """§8.3 — subscription_state exposes the live subscription's own dates
    (read straight from the model, never invented) without altering days_left."""

    def setUp(self):
        from apps.subscriptions.enforcement import subscription_state

        self._state = subscription_state
        self.hotel = Hotel.objects.create(name="Dune", slug="dune")
        self.plan = make_plan()

    def test_active_exposes_starts_at_and_no_trial(self):
        sub = services.activate_subscription(self.hotel, self.plan)
        st = self._state(self.hotel)
        # Exact value — proves the date is the model's own, never invented.
        self.assertEqual(st["starts_at"], sub.starts_at.isoformat())
        self.assertIsNone(st["trial_ends_at"])  # a paid sub has no trial
        self.assertIsNotNone(st["ends_at"])
        self.assertIsNotNone(st["days_left"])  # days_left calc unchanged

    def test_trial_exposes_trial_ends_at(self):
        sub = services.start_trial(self.hotel, self.plan)
        st = self._state(self.hotel)
        self.assertEqual(st["starts_at"], sub.starts_at.isoformat())
        self.assertEqual(st["trial_ends_at"], sub.trial_ends_at.isoformat())

    def test_past_due_behaves_like_active(self):
        from apps.subscriptions.models import SubscriptionStatus

        sub = services.activate_subscription(self.hotel, self.plan)
        sub.status = SubscriptionStatus.PAST_DUE
        sub.save(update_fields=["status"])
        st = self._state(self.hotel)
        self.assertEqual(st["starts_at"], sub.starts_at.isoformat())
        self.assertIsNone(st["trial_ends_at"])

    def test_no_subscription_is_null_safe(self):
        st = self._state(self.hotel)
        self.assertIsNone(st["starts_at"])
        self.assertIsNone(st["trial_ends_at"])
        self.assertIsNone(st["days_left"])
        self.assertFalse(st["has_subscription"])

    def test_expired_history_is_null_safe(self):
        # History exists but no live subscription (live is None) -> dates null.
        services.expire_subscription(services.activate_subscription(self.hotel, self.plan))
        st = self._state(self.hotel)
        self.assertTrue(st["has_subscription"])
        self.assertTrue(st["expired"])
        self.assertIsNone(st["starts_at"])
        self.assertIsNone(st["trial_ends_at"])

    def test_effective_subscription_state_carries_dates(self):
        # The FE + owner panel consume the effective_subscription_state WRAPPER,
        # not subscription_state directly — prove the fields survive the wrapper.
        from apps.subscriptions.entitlements import effective_subscription_state

        sub = services.activate_subscription(self.hotel, self.plan)
        st = effective_subscription_state(self.hotel)
        self.assertEqual(st["starts_at"], sub.starts_at.isoformat())
        self.assertIn("trial_ends_at", st)

    def test_dates_are_tenant_scoped(self):
        other = Hotel.objects.create(name="Reef", slug="reef")
        services.activate_subscription(self.hotel, self.plan)
        # The other hotel has no subscription — its state must not borrow ours.
        self.assertIsNotNone(self._state(self.hotel)["starts_at"])
        self.assertIsNone(self._state(other)["starts_at"])
