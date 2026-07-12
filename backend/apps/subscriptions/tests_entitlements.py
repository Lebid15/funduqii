"""Subscriptions final closure — grandfathering, entitlement limits, plan
change, reactivation, duplicate-reference guard, effective state, events and
the public plan catalog.

These complement (never replace) the Phase 3/16 tests. Everything routes through
the central services/entitlements — no hard-coded plan names anywhere.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.common.exceptions import (
    ConflictingSubscription,
    DuplicatePaymentReference,
    InvalidSubscriptionTransition,
    RoomLimitReached,
    StaffLimitReached,
    TrialAlreadyUsed,
)
from apps.notifications.models import ActivityEvent
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.subscriptions import entitlements as E
from apps.subscriptions import services as S
from apps.subscriptions.enforcement import (
    effective_status,
    effectively_live_q,
    subscription_blocks_writes,
)
from apps.subscriptions.models import (
    HotelSubscription,
    PlatformSubscriptionPayment,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

STRONG = "StrongPass!234"


def HDR(h):
    return {"HTTP_X_HOTEL_ID": str(h.id)}


def make_owner(email="owner@platform.local"):
    return User.objects.create_user(
        email=email, password=STRONG, full_name="Owner",
        account_type=AccountType.PLATFORM_OWNER,
    )


def make_hotel(slug="h", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name=slug.upper(), slug=slug, status=status)


def make_manager(hotel, email="mgr@hotel.local"):
    user = User.objects.create_user(email=email, password=STRONG, full_name="Mgr")
    HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=MembershipType.MANAGER, is_active=True
    )
    return user


def make_plan(slug="basic", **kw):
    defaults = dict(
        name=kw.pop("name", "Basic"), slug=slug, price=Decimal("49.00"),
        currency="USD", billing_cycle="monthly", trial_days=14, is_active=True,
        is_public=True,
    )
    defaults.update(kw)
    return SubscriptionPlan.objects.create(**defaults)


# --- Grandfathering / snapshot -----------------------------------------------


class SnapshotTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.plan = make_plan(price=Decimal("49.00"), room_limit=5, user_limit=3,
                              feature_codes=["restaurant_cafe"])

    def test_trial_captures_snapshot(self):
        sub = S.start_trial(self.hotel, self.plan)
        self.assertIsNotNone(sub.plan_snapshot)
        self.assertEqual(sub.plan_snapshot["price"], "49.00")
        self.assertEqual(sub.plan_snapshot["room_limit"], 5)
        self.assertEqual(sub.plan_snapshot["feature_codes"], ["restaurant_cafe"])

    def test_activate_captures_snapshot(self):
        sub = S.activate_subscription(self.hotel, self.plan)
        self.assertEqual(sub.plan_snapshot["user_limit"], 3)

    def test_editing_plan_does_not_change_existing_sub(self):
        sub = S.activate_subscription(self.hotel, self.plan)
        # Owner edits the live plan afterwards.
        self.plan.price = Decimal("999.00")
        self.plan.room_limit = 1
        self.plan.save(update_fields=["price", "room_limit"])
        terms = S.subscription_terms(sub)
        self.assertEqual(terms["price"], "49.00")   # frozen
        self.assertEqual(terms["room_limit"], 5)     # frozen

    def test_new_sub_takes_new_terms(self):
        S.activate_subscription(self.hotel, self.plan)
        self.plan.price = Decimal("999.00")
        self.plan.room_limit = 1
        self.plan.save(update_fields=["price", "room_limit"])
        # A fresh subscription (reactivation) captures the NEW terms.
        S.expire_subscription(S.get_current_subscription(self.hotel))
        new = S.reactivate_subscription(self.hotel, self.plan)
        self.assertEqual(new.plan_snapshot["price"], "999.00")
        self.assertEqual(new.plan_snapshot["room_limit"], 1)

    def test_legacy_null_snapshot_falls_back_to_live_plan(self):
        sub = HotelSubscription.objects.create(
            hotel=self.hotel, plan=self.plan, status=SubscriptionStatus.ACTIVE,
            ends_at=timezone.now() + datetime.timedelta(days=10), plan_snapshot=None,
        )
        self.assertEqual(S.subscription_terms(sub)["room_limit"], 5)


# --- Free trial once-only (explicit regression) ------------------------------


class TrialOnceTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.plan = make_plan()

    def test_trial_once_only(self):
        S.start_trial(self.hotel, self.plan)
        # A second trial is refused by the once-only guard (trial_ends_at is set).
        with self.assertRaises(TrialAlreadyUsed):
            S.start_trial(self.hotel, self.plan)

    def test_no_trial_after_expiry(self):
        sub = S.start_trial(self.hotel, self.plan)
        S.expire_subscription(sub)
        with self.assertRaises(TrialAlreadyUsed):
            S.start_trial(self.hotel, self.plan)

    def test_no_trial_with_prior_paid_subscription(self):
        S.activate_subscription(self.hotel, self.plan)
        S.cancel_subscription(S.get_current_subscription(self.hotel))
        with self.assertRaises(TrialAlreadyUsed):
            S.start_trial(self.hotel, self.plan)

    def test_reading_state_does_not_create_trial(self):
        before = HotelSubscription.objects.filter(hotel=self.hotel).count()
        E.effective_subscription_state(self.hotel)
        E.entitlement_summary(self.hotel)
        self.assertEqual(
            HotelSubscription.objects.filter(hotel=self.hotel).count(), before
        )


# --- Usage state --------------------------------------------------------------


class UsageStateTests(APITestCase):
    def test_thresholds(self):
        self.assertEqual(E.usage_state(0, 10), "normal")
        self.assertEqual(E.usage_state(7, 10), "normal")
        self.assertEqual(E.usage_state(8, 10), "nearing_limit")
        self.assertEqual(E.usage_state(10, 10), "limit_reached")
        self.assertEqual(E.usage_state(11, 10), "over_limit")
        self.assertEqual(E.usage_state(999, None), "normal")  # unlimited


# --- Room limit (API) ---------------------------------------------------------


class RoomLimitTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = make_manager(self.hotel)
        self.plan = make_plan(room_limit=1)
        S.activate_subscription(self.hotel, self.plan)
        self.floor = Floor.objects.create(hotel=self.hotel, name="F1")
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD", base_capacity=2, max_capacity=3
        )
        self.client.force_authenticate(user=self.manager)

    def _create_room(self, number):
        return self.client.post(
            reverse("rooms:room-list"),
            {"floor": self.floor.id, "room_type": self.rtype.id, "number": number},
            **HDR(self.hotel),
        )

    def test_within_limit_ok(self):
        self.assertEqual(self._create_room("101").status_code, 201)

    def test_over_limit_blocked(self):
        self.assertEqual(self._create_room("101").status_code, 201)
        r = self._create_room("102")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_limit_reached")

    def test_existing_over_limit_grandfathered(self):
        # Two rooms exist (created directly), then the plan allows only 1.
        Room.objects.create(hotel=self.hotel, floor=self.floor, room_type=self.rtype,
                           number="101", status="available")
        Room.objects.create(hotel=self.hotel, floor=self.floor, room_type=self.rtype,
                           number="102", status="available")
        self.assertEqual(E.room_usage(self.hotel), 2)
        # New room is blocked, but the two existing rooms stay.
        r = self._create_room("103")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Room.objects.filter(hotel=self.hotel).count(), 2)

    def test_archived_room_not_counted(self):
        Room.objects.create(hotel=self.hotel, floor=self.floor, room_type=self.rtype,
                           number="101", status=RoomStatus.ARCHIVED)
        self.assertEqual(E.room_usage(self.hotel), 0)
        self.assertEqual(self._create_room("102").status_code, 201)

    def test_unlimited_plan_never_blocks(self):
        S.change_subscription_plan(self.hotel, make_plan(slug="unl", room_limit=None))
        for n in ("101", "102", "103"):
            self.assertEqual(self._create_room(n).status_code, 201)


# --- Staff limit (service) ----------------------------------------------------


class StaffLimitTests(APITestCase):
    def setUp(self):
        from apps.staff import services as staff_services

        self.staff_services = staff_services
        self.hotel = make_hotel()
        self.manager = make_manager(self.hotel)  # 1 active membership
        self.plan = make_plan(user_limit=2)
        S.activate_subscription(self.hotel, self.plan)

    def _create_staff(self, email):
        return self.staff_services.create_staff_member(
            self.hotel, actor=self.manager, email=email, full_name="S",
            password=STRONG, permissions=(),
        )

    def test_manager_counts_in_usage(self):
        self.assertEqual(E.staff_usage(self.hotel), 1)

    def test_limit_blocks_new_staff(self):
        self._create_staff("s1@h.local")  # usage now 2 (== limit)
        with self.assertRaises(StaffLimitReached):
            self._create_staff("s2@h.local")

    def test_existing_grandfathered_on_downgrade(self):
        self._create_staff("s1@h.local")  # usage 2
        # Downgrade to user_limit 1: existing 2 memberships remain.
        S.change_subscription_plan(self.hotel, make_plan(slug="tiny", user_limit=1))
        self.assertEqual(E.staff_usage(self.hotel), 2)
        with self.assertRaises(StaffLimitReached):
            self._create_staff("s2@h.local")


# --- Feature helper -----------------------------------------------------------


class FeatureHelperTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.plan = make_plan(feature_codes=["restaurant_cafe", "advanced_reports"])
        S.activate_subscription(self.hotel, self.plan)

    def test_has_feature(self):
        self.assertTrue(E.has_subscription_feature(self.hotel, "restaurant_cafe"))
        self.assertFalse(E.has_subscription_feature(self.hotel, "public_booking"))

    def test_no_live_subscription_has_no_feature(self):
        h2 = make_hotel(slug="h2")
        self.assertFalse(E.has_subscription_feature(h2, "restaurant_cafe"))

    def test_normalize_drops_unknown_and_dedupes(self):
        self.assertEqual(
            E.normalize_feature_codes(["Restaurant_Cafe", "restaurant_cafe", "bogus"]),
            ["restaurant_cafe"],
        )


# --- Public booking limit (gate) ---------------------------------------------


class PublicBookingLimitTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()

    def test_zero_allowance_blocks(self):
        from apps.common.exceptions import PublicBookingLimitReached

        S.activate_subscription(self.hotel, make_plan(max_public_bookings_per_month=0))
        with self.assertRaises(PublicBookingLimitReached):
            E.check_public_booking_quota(self.hotel)

    def test_null_allowance_never_blocks(self):
        S.activate_subscription(
            self.hotel, make_plan(max_public_bookings_per_month=None)
        )
        E.check_public_booking_quota(self.hotel)  # must not raise

    def test_fresh_hotel_usage_is_zero(self):
        self.assertEqual(E.public_booking_usage(self.hotel), 0)


# --- Change plan --------------------------------------------------------------


class ChangePlanTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.small = make_plan(slug="small", price=Decimal("10"), room_limit=5)
        self.big = make_plan(slug="big", price=Decimal("50"), room_limit=50)

    def test_upgrade_replaces_live_sub(self):
        S.activate_subscription(self.hotel, self.small)
        new = S.change_subscription_plan(self.hotel, self.big)
        self.assertEqual(new.plan_id, self.big.id)
        self.assertEqual(new.status, SubscriptionStatus.ACTIVE)
        # Exactly one live subscription.
        self.assertEqual(
            HotelSubscription.objects.filter(
                hotel=self.hotel, status__in=list(S.LIVE_STATUSES)
            ).count(),
            1,
        )
        ev = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="subscription.plan_changed"
        ).latest("id")
        self.assertIn("upgrade", ev.message)

    def test_downgrade_classified(self):
        S.activate_subscription(self.hotel, self.big)
        S.change_subscription_plan(self.hotel, self.small)
        ev = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="subscription.plan_changed"
        ).latest("id")
        self.assertIn("downgrade", ev.message)

    def test_lateral_change_classified(self):
        S.activate_subscription(self.hotel, self.small)
        same = make_plan(slug="same", price=Decimal("10"), room_limit=5)
        S.change_subscription_plan(self.hotel, same)
        ev = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="subscription.plan_changed"
        ).latest("id")
        self.assertIn("lateral_change", ev.message)

    def test_change_without_live_raises(self):
        with self.assertRaises(InvalidSubscriptionTransition):
            S.change_subscription_plan(self.hotel, self.big)

    def test_change_does_not_create_trial(self):
        S.activate_subscription(self.hotel, self.small)
        S.change_subscription_plan(self.hotel, self.big)
        self.assertFalse(
            HotelSubscription.objects.filter(
                hotel=self.hotel, status=SubscriptionStatus.TRIAL
            ).exists()
        )

    def test_isolation_other_hotel_unaffected(self):
        other = make_hotel(slug="other")
        S.activate_subscription(other, self.small)
        S.activate_subscription(self.hotel, self.small)
        S.change_subscription_plan(self.hotel, self.big)
        self.assertEqual(
            S.get_current_subscription(other).plan_id, self.small.id
        )


# --- Reactivate ---------------------------------------------------------------


class ReactivateTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.plan = make_plan()

    def test_reactivate_after_expiry(self):
        sub = S.activate_subscription(self.hotel, self.plan)
        S.expire_subscription(sub)
        new = S.reactivate_subscription(self.hotel, self.plan)
        self.assertEqual(new.status, SubscriptionStatus.ACTIVE)
        self.assertFalse(subscription_blocks_writes(self.hotel))
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="subscription.reactivated"
            ).exists()
        )

    def test_reactivate_requires_history(self):
        with self.assertRaises(InvalidSubscriptionTransition):
            S.reactivate_subscription(self.hotel, self.plan)

    def test_reactivate_conflicts_with_live(self):
        S.activate_subscription(self.hotel, self.plan)
        with self.assertRaises(ConflictingSubscription):
            S.reactivate_subscription(self.hotel, self.plan)


# --- Manual payments: duplicate reference, void, events ----------------------


class PaymentTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.plan = make_plan()

    def _pay(self, reference=""):
        return S.record_platform_payment(
            self.hotel, amount=Decimal("10"), currency="USD", method="cash",
            reference=reference,
        )

    def test_duplicate_reference_rejected(self):
        self._pay("REF-1")
        with self.assertRaises(DuplicatePaymentReference):
            self._pay("REF-1")

    def test_no_reference_allows_duplicates(self):
        self._pay("")
        self._pay("")
        self.assertEqual(
            PlatformSubscriptionPayment.objects.filter(hotel=self.hotel).count(), 2
        )

    def test_voided_reference_can_be_reused(self):
        p = self._pay("REF-2")
        S.void_platform_payment(p, reason="mistake")
        self._pay("REF-2")  # non-voided uniqueness — allowed again
        self.assertEqual(
            PlatformSubscriptionPayment.objects.filter(
                hotel=self.hotel, reference="REF-2"
            ).count(),
            2,
        )

    def test_double_void_rejected(self):
        p = self._pay("REF-3")
        S.void_platform_payment(p, reason="x")
        with self.assertRaises(InvalidSubscriptionTransition):
            S.void_platform_payment(
                PlatformSubscriptionPayment.objects.get(pk=p.pk), reason="again"
            )

    def test_payment_events_recorded(self):
        p = self._pay("REF-4")
        S.void_platform_payment(p, reason="x")
        self.assertTrue(ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="subscription.payment_recorded").exists())
        self.assertTrue(ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="subscription.payment_voided").exists())


# --- Effective status ---------------------------------------------------------


class EffectiveStatusTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.plan = make_plan()

    def test_trial_past_end_is_effectively_expired(self):
        sub = HotelSubscription.objects.create(
            hotel=self.hotel, plan=self.plan, status=SubscriptionStatus.TRIAL,
            trial_ends_at=timezone.now() - datetime.timedelta(hours=1),
        )
        self.assertEqual(sub.status, SubscriptionStatus.TRIAL)  # stored unchanged
        self.assertEqual(effective_status(sub), SubscriptionStatus.EXPIRED)

    def test_live_trial_is_trial(self):
        sub = HotelSubscription.objects.create(
            hotel=self.hotel, plan=self.plan, status=SubscriptionStatus.TRIAL,
            trial_ends_at=timezone.now() + datetime.timedelta(days=5),
        )
        self.assertEqual(effective_status(sub), SubscriptionStatus.TRIAL)

    def test_overview_counts_use_effective_status(self):
        # A trial past its end must NOT count as an active trial.
        HotelSubscription.objects.create(
            hotel=self.hotel, plan=self.plan, status=SubscriptionStatus.TRIAL,
            trial_ends_at=timezone.now() - datetime.timedelta(hours=1),
        )
        owner = make_owner()
        self.client.force_authenticate(user=owner)
        data = self.client.get(reverse("platform:overview")).data
        self.assertEqual(data["subscriptions"]["active_trials"], 0)
        self.assertEqual(data["subscriptions"]["expired"], 1)


# --- Renew idempotency / rejection -------------------------------------------


class RenewTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.plan = make_plan()
        self.sub = S.activate_subscription(self.hotel, self.plan)

    def test_renew_explicit_target_is_idempotent(self):
        target = timezone.now() + datetime.timedelta(days=60)
        S.renew_subscription(self.sub, ends_at=target)
        S.renew_subscription(
            HotelSubscription.objects.get(pk=self.sub.pk), ends_at=target
        )
        self.assertEqual(
            HotelSubscription.objects.get(pk=self.sub.pk).ends_at, target
        )

    def test_renew_from_trial_rejected(self):
        h2 = make_hotel(slug="h2")
        trial = S.start_trial(h2, self.plan)
        with self.assertRaises(InvalidSubscriptionTransition):
            S.renew_subscription(trial)

    def test_extend_emits_extended_event(self):
        S.renew_subscription(self.sub, days=10, kind="extend")
        self.assertTrue(ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="subscription.extended").exists())


# --- Platform endpoints: change-plan / reactivate / state --------------------


class PlatformSubscriptionEndpointTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.hotel = make_hotel()
        self.manager = make_manager(self.hotel)
        self.small = make_plan(slug="small", room_limit=5)
        self.big = make_plan(slug="big", room_limit=50)
        S.activate_subscription(self.hotel, self.small)

    def test_owner_change_plan(self):
        self.client.force_authenticate(user=self.owner)
        r = self.client.post(
            reverse("platform:hotel-change-plan", args=[self.hotel.id]),
            {"plan": self.big.id, "reason": "growth"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["plan"], self.big.id)

    def test_manager_cannot_change_plan(self):
        self.client.force_authenticate(user=self.manager)
        r = self.client.post(
            reverse("platform:hotel-change-plan", args=[self.hotel.id]),
            {"plan": self.big.id},
        )
        self.assertEqual(r.status_code, 403)

    def test_owner_reads_subscription_state(self):
        self.client.force_authenticate(user=self.owner)
        r = self.client.get(
            reverse("platform:hotel-subscription-state", args=[self.hotel.id])
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("entitlements", r.data)
        self.assertEqual(r.data["entitlements"]["rooms"]["limit"], 5)

    def test_owner_reactivate_after_expiry(self):
        S.expire_subscription(S.get_current_subscription(self.hotel))
        self.client.force_authenticate(user=self.owner)
        r = self.client.post(
            reverse("platform:hotel-reactivate", args=[self.hotel.id]),
            {"plan": self.big.id, "payment_amount": "50.00", "payment_method": "cash"},
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(
            PlatformSubscriptionPayment.objects.filter(hotel=self.hotel).exists()
        )


# --- Public catalog -----------------------------------------------------------


class PublicCatalogTests(APITestCase):
    def test_only_active_public_plans_in_sort_order(self):
        make_plan(slug="p-b", name="B", is_active=True, is_public=True, sort_order=2)
        make_plan(slug="p-a", name="A", is_active=True, is_public=True, sort_order=1)
        make_plan(slug="hidden", name="Hidden", is_active=True, is_public=False)
        make_plan(slug="inactive", name="Inactive", is_active=False, is_public=True)
        r = self.client.get(reverse("public_site:plans"))
        self.assertEqual(r.status_code, 200)
        slugs = [p["slug"] for p in r.data["plans"]]
        self.assertEqual(slugs, ["p-a", "p-b"])  # sorted, hidden+inactive excluded

    def test_no_checkout_fields_exposed(self):
        make_plan(slug="p1", is_active=True, is_public=True)
        r = self.client.get(reverse("public_site:plans"))
        keys = set(r.data["plans"][0].keys())
        self.assertIn("price", keys)
        self.assertIn("feature_codes", keys)
        for forbidden in ("checkout_url", "payment_url", "stripe", "card"):
            self.assertNotIn(forbidden, keys)


# --- Event contract -----------------------------------------------------------


class EventContractTests(APITestCase):
    def test_contract_lists_the_required_event_types(self):
        for name in (
            "plan.created", "plan.updated", "plan.activated", "plan.deactivated",
            "subscription.trial_started", "subscription.activated",
            "subscription.renewed", "subscription.extended",
            "subscription.plan_changed", "subscription.cancelled",
            "subscription.expired", "subscription.reactivated",
            "subscription.payment_recorded", "subscription.payment_voided",
            "subscription.restricted",
        ):
            self.assertIn(name, S.SUBSCRIPTION_EVENT_TYPES)
