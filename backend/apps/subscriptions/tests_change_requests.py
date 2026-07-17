"""Service tests for hotel-initiated subscription change requests (§8.5).

Covers the full lifecycle (submit / accept / reject / cancel / execute), the
kind + plan-target preconditions (including no-downgrade), the one-open-request
rule, server-side re-validation at execute, the per-hotel plan availability
classification (§8.4), and a PostgreSQL concurrency proof for the partial-unique
one-open-request constraint.
"""
from __future__ import annotations

import threading
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.common.exceptions import (
    InvalidSubscriptionRequestTransition,
    PlanNotAvailableForRequest,
    SubscriptionRequestConflict,
    SubscriptionRequestNotAllowed,
    SubscriptionRequestReasonRequired,
)
from apps.subscriptions import request_services as rs
from apps.subscriptions import services
from apps.subscriptions.models import (
    ChangeRequestKind,
    ChangeRequestStatus,
    HotelSubscription,
    PlatformSubscriptionPayment,
    SubscriptionChangeRequest,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel

from .tests import make_plan


def make_plans():
    basic = make_plan(name="Basic", slug="basic", price="49.00", room_limit=10)
    pro = make_plan(name="Pro", slug="pro", price="99.00", room_limit=50)
    mini = make_plan(name="Mini", slug="mini", price="29.00", room_limit=5)
    return basic, pro, mini


class SubmitRequestTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name="Sea View", slug="sea-view")
        self.basic, self.pro, self.mini = make_plans()

    def test_new_subscription_when_no_live_sub(self):
        req = rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.basic
        )
        self.assertEqual(req.status, ChangeRequestStatus.UNDER_REVIEW)
        self.assertEqual(req.requested_plan_id, self.basic.id)

    def test_new_subscription_blocked_when_live(self):
        services.activate_subscription(self.hotel, self.basic)
        with self.assertRaises(SubscriptionRequestNotAllowed):
            rs.submit_change_request(
                self.hotel,
                kind=ChangeRequestKind.NEW_SUBSCRIPTION,
                requested_plan=self.pro,
            )

    def test_renewal_requires_live_sub(self):
        with self.assertRaises(SubscriptionRequestNotAllowed):
            rs.submit_change_request(self.hotel, kind=ChangeRequestKind.RENEWAL)

    def test_renewal_ok_and_drops_plan(self):
        services.activate_subscription(self.hotel, self.basic)
        req = rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.RENEWAL, requested_plan=self.pro
        )
        # Renewal never changes the plan — the target plan is discarded.
        self.assertIsNone(req.requested_plan_id)

    def test_renewal_on_trial_rejected(self):
        # A trial is not renewable — it is converted to paid / upgraded instead.
        services.start_trial(self.hotel, self.basic)
        self.assertFalse(
            rs.can_request_renewal(
                services.get_current_subscription(self.hotel)
            )
        )
        with self.assertRaises(SubscriptionRequestNotAllowed):
            rs.submit_change_request(self.hotel, kind=ChangeRequestKind.RENEWAL)

    def test_plan_change_to_hidden_plan_rejected(self):
        services.activate_subscription(self.hotel, self.basic)
        self.pro.is_public = False
        self.pro.save(update_fields=["is_public"])
        with self.assertRaises(PlanNotAvailableForRequest):
            rs.submit_change_request(
                self.hotel,
                kind=ChangeRequestKind.PLAN_CHANGE,
                requested_plan=self.pro,
            )

    def test_new_subscription_to_hidden_plan_rejected(self):
        self.pro.is_public = False
        self.pro.save(update_fields=["is_public"])
        with self.assertRaises(PlanNotAvailableForRequest):
            rs.submit_change_request(
                self.hotel,
                kind=ChangeRequestKind.NEW_SUBSCRIPTION,
                requested_plan=self.pro,
            )

    def test_plan_change_upgrade_ok(self):
        services.activate_subscription(self.hotel, self.basic)
        req = rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.PLAN_CHANGE, requested_plan=self.pro
        )
        self.assertEqual(req.kind, ChangeRequestKind.PLAN_CHANGE)

    def test_plan_change_downgrade_rejected(self):
        services.activate_subscription(self.hotel, self.basic)
        with self.assertRaises(PlanNotAvailableForRequest):
            rs.submit_change_request(
                self.hotel,
                kind=ChangeRequestKind.PLAN_CHANGE,
                requested_plan=self.mini,
            )

    def test_plan_change_same_plan_rejected(self):
        services.activate_subscription(self.hotel, self.basic)
        with self.assertRaises(PlanNotAvailableForRequest):
            rs.submit_change_request(
                self.hotel,
                kind=ChangeRequestKind.PLAN_CHANGE,
                requested_plan=self.basic,
            )

    def test_plan_change_to_inactive_rejected(self):
        services.activate_subscription(self.hotel, self.basic)
        self.pro.is_active = False
        self.pro.save(update_fields=["is_active"])
        with self.assertRaises(PlanNotAvailableForRequest):
            rs.submit_change_request(
                self.hotel,
                kind=ChangeRequestKind.PLAN_CHANGE,
                requested_plan=self.pro,
            )

    def test_second_open_request_conflicts(self):
        rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.basic
        )
        with self.assertRaises(SubscriptionRequestConflict):
            rs.submit_change_request(
                self.hotel,
                kind=ChangeRequestKind.NEW_SUBSCRIPTION,
                requested_plan=self.pro,
            )

    def test_new_request_allowed_after_terminal(self):
        req = rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.basic
        )
        rs.cancel_change_request(req, by_hotel=True)
        # The open slot is freed — a fresh request may be submitted.
        req2 = rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.pro
        )
        self.assertEqual(req2.status, ChangeRequestStatus.UNDER_REVIEW)


class DecisionTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name="Palm", slug="palm")
        self.basic, self.pro, self.mini = make_plans()
        self.req = rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.basic
        )

    def test_accept_moves_to_accepted(self):
        req = rs.accept_change_request(self.req)
        self.assertEqual(req.status, ChangeRequestStatus.ACCEPTED)
        self.assertIsNotNone(req.decided_at)

    def test_accept_non_under_review_rejected(self):
        rs.accept_change_request(self.req)
        with self.assertRaises(InvalidSubscriptionRequestTransition):
            rs.accept_change_request(self.req)

    def test_reject_requires_reason(self):
        with self.assertRaises(SubscriptionRequestReasonRequired):
            rs.reject_change_request(self.req, reason="   ")

    def test_reject_with_reason(self):
        req = rs.reject_change_request(self.req, reason="Not now")
        self.assertEqual(req.status, ChangeRequestStatus.REJECTED)
        self.assertEqual(req.admin_note, "Not now")

    def test_hotel_cannot_cancel_accepted(self):
        rs.accept_change_request(self.req)
        with self.assertRaises(InvalidSubscriptionRequestTransition):
            rs.cancel_change_request(self.req, by_hotel=True)

    def test_owner_can_cancel_accepted(self):
        rs.accept_change_request(self.req)
        req = rs.cancel_change_request(self.req, by_hotel=False)
        self.assertEqual(req.status, ChangeRequestStatus.CANCELLED)


class ExecuteTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name="Cedar", slug="cedar")
        self.basic, self.pro, self.mini = make_plans()

    def _accepted(self, **submit_kwargs):
        req = rs.submit_change_request(self.hotel, **submit_kwargs)
        return rs.accept_change_request(req)

    def test_execute_new_subscription_activates(self):
        req = self._accepted(
            kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.pro
        )
        req, sub = rs.execute_change_request(req)
        self.assertEqual(req.status, ChangeRequestStatus.EXECUTED)
        self.assertEqual(req.resulting_subscription_id, sub.id)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(sub.plan_id, self.pro.id)
        self.assertIsNotNone(req.executed_at)

    def test_execute_plan_change_upgrades_single_live(self):
        services.activate_subscription(self.hotel, self.basic)
        req = self._accepted(
            kind=ChangeRequestKind.PLAN_CHANGE, requested_plan=self.pro
        )
        req, sub = rs.execute_change_request(req)
        self.assertEqual(sub.plan_id, self.pro.id)
        # Exactly one live subscription remains (the old one was terminated).
        live = HotelSubscription.objects.filter(
            hotel=self.hotel, status__in=list(services.LIVE_STATUSES)
        )
        self.assertEqual(live.count(), 1)
        self.assertEqual(live.first().id, sub.id)
        # New snapshot reflects the new plan.
        self.assertEqual(sub.plan_snapshot["plan_id"], self.pro.id)

    def test_execute_renewal_is_fresh_cycle(self):
        sub = services.activate_subscription(self.hotel, self.basic)
        # Push the end far into the future to prove a fresh cycle is applied.
        far = timezone.now() + timedelta(days=300)
        sub.ends_at = far
        sub.save(update_fields=["ends_at"])
        req = self._accepted(kind=ChangeRequestKind.RENEWAL)
        req, renewed = rs.execute_change_request(req)
        # Fresh cycle from execution (~30 days), NOT the old far-future date.
        self.assertLess(renewed.ends_at, far)
        delta_days = (renewed.ends_at - timezone.now()).days
        self.assertTrue(28 <= delta_days <= 31, delta_days)

    def test_execute_requires_accepted(self):
        req = rs.submit_change_request(
            self.hotel, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.pro
        )
        with self.assertRaises(InvalidSubscriptionRequestTransition):
            rs.execute_change_request(req)  # still under_review

    def test_execute_revalidates_plan_availability(self):
        req = self._accepted(
            kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.pro
        )
        # The plan is deactivated AFTER acceptance, BEFORE execution.
        self.pro.is_active = False
        self.pro.save(update_fields=["is_active"])
        with self.assertRaises(PlanNotAvailableForRequest):
            rs.execute_change_request(req)
        req.refresh_from_db()
        # The request stays accepted; no subscription was created.
        self.assertEqual(req.status, ChangeRequestStatus.ACCEPTED)
        self.assertFalse(
            HotelSubscription.objects.filter(hotel=self.hotel).exists()
        )

    def test_execute_records_optional_payment(self):
        req = self._accepted(
            kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=self.pro
        )
        req, sub = rs.execute_change_request(
            req, payment={"amount": Decimal("99.00"), "method": "cash", "reference": "R-1"}
        )
        pay = PlatformSubscriptionPayment.objects.get(hotel=self.hotel)
        self.assertEqual(str(pay.amount), "99.00")
        self.assertEqual(pay.subscription_id, sub.id)


class AvailabilityTests(TestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name="Oasis", slug="oasis")
        self.basic, self.pro, self.mini = make_plans()

    def _state(self, rows, plan):
        return next(r["state"] for r in rows if r["plan"].id == plan.id)

    def test_no_live_sub_all_available(self):
        rows, live = rs.available_plans_for_hotel(self.hotel)
        self.assertIsNone(live)
        for plan in (self.basic, self.pro, self.mini):
            self.assertEqual(self._state(rows, plan), "available")

    def test_live_sub_states(self):
        services.activate_subscription(self.hotel, self.basic)
        rows, live = rs.available_plans_for_hotel(self.hotel)
        self.assertIsNotNone(live)
        self.assertEqual(self._state(rows, self.basic), "current")
        self.assertEqual(self._state(rows, self.pro), "upgradeable")
        # A lower plan is not self-service (owner-handled downgrade).
        self.assertEqual(self._state(rows, self.mini), "unavailable")

    def test_hidden_plan_not_leaked(self):
        self.pro.is_public = False
        self.pro.save(update_fields=["is_public"])
        rows, _ = rs.available_plans_for_hotel(self.hotel)
        self.assertFalse(any(r["plan"].id == self.pro.id for r in rows))


class PlanDeletionGuardTests(TestCase):
    def test_plan_with_request_history_is_in_use(self):
        hotel = Hotel.objects.create(name="Rock", slug="rock")
        plan = make_plan(name="Solo", slug="solo")
        self.assertFalse(plan.is_in_use)
        req = rs.submit_change_request(
            hotel, kind=ChangeRequestKind.NEW_SUBSCRIPTION, requested_plan=plan
        )
        rs.reject_change_request(req, reason="no")
        # Even a terminal request keeps the plan "in use" (PROTECT + clean 409).
        self.assertTrue(plan.is_in_use)


_PG_SKIP = (
    "The one-open-request partial-unique constraint is only a real concurrency "
    "backstop on PostgreSQL. SQLite serialises writers, so this is skipped there."
)


class RequestConcurrencyTests(TransactionTestCase):
    """Two threads submit a request for the SAME hotel at once — the partial
    unique constraint must let exactly ONE become open."""

    def setUp(self):
        self.hotel = Hotel.objects.create(name="Twin", slug="twin")
        self.plan = make_plan(name="Basic", slug="basic")

    def test_concurrent_submit_yields_one_open_request(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)

        barrier = threading.Barrier(2)
        results: list[str] = []

        def worker():
            barrier.wait()
            try:
                with transaction.atomic():
                    rs.submit_change_request(
                        self.hotel,
                        kind=ChangeRequestKind.NEW_SUBSCRIPTION,
                        requested_plan=self.plan,
                    )
                results.append("ok")
            except (SubscriptionRequestConflict, IntegrityError):
                results.append("conflict")
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), ["conflict", "ok"])
        open_count = SubscriptionChangeRequest.objects.filter(
            hotel=self.hotel, status__in=list(rs.OPEN_REQUEST_STATUSES)
        ).count()
        self.assertEqual(open_count, 1)
