"""Phase 16 — central subscription enforcement tests.

An EXPIRED (or trial-ended) subscription must block every important write in
the hotel console AND public booking, with the stable error code
``subscription_inactive`` — while reads (lists, reports, notifications,
settings) keep working and nothing is deleted. A hotel with NO subscription
history is not blocked (documented decision: billing starts with onboarding).
Suspension keeps its own code ``hotel_suspended`` and wins over subscription
state.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.hotels.models import HotelSettings
from apps.rooms.models import Floor, RoomType
from apps.subscriptions.enforcement import (
    ensure_hotel_operational,
    subscription_blocked_hotel_ids,
    subscription_blocks_writes,
    subscription_state,
)
from apps.subscriptions.models import (
    HotelSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

STRONG = "StrongPass!234"


def expire_hotel_subscription(hotel):
    """Give the hotel an ended trial → writes must be blocked."""
    plan = SubscriptionPlan.objects.create(
        name="P", slug=f"p-{hotel.slug}", price=Decimal("10.00")
    )
    HotelSubscription.objects.create(
        hotel=hotel,
        plan=plan,
        status=SubscriptionStatus.EXPIRED,
        starts_at=timezone.now() - datetime.timedelta(days=40),
        trial_ends_at=timezone.now() - datetime.timedelta(days=10),
        ends_at=timezone.now() - datetime.timedelta(days=10),
    )


class EnforcementUnitTests(APITestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="H", slug="h", status=HotelStatus.ACTIVE
        )

    def test_no_history_not_blocked(self):
        self.assertFalse(subscription_blocks_writes(self.hotel))
        ensure_hotel_operational(self.hotel)  # must not raise

    def test_expired_blocks(self):
        expire_hotel_subscription(self.hotel)
        self.assertTrue(subscription_blocks_writes(self.hotel))

    def test_live_trial_past_end_blocks(self):
        # A trial whose end passed blocks even if the status was never flipped
        # (enforcement is time-aware; there is no background job).
        plan = SubscriptionPlan.objects.create(name="P", slug="p", price=0)
        HotelSubscription.objects.create(
            hotel=self.hotel,
            plan=plan,
            status=SubscriptionStatus.TRIAL,
            trial_ends_at=timezone.now() - datetime.timedelta(hours=1),
        )
        self.assertTrue(subscription_blocks_writes(self.hotel))

    def test_active_unexpired_not_blocked(self):
        plan = SubscriptionPlan.objects.create(name="P", slug="p", price=0)
        HotelSubscription.objects.create(
            hotel=self.hotel,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            ends_at=timezone.now() + datetime.timedelta(days=10),
        )
        self.assertFalse(subscription_blocks_writes(self.hotel))

    def test_suspension_wins_in_error_code(self):
        from apps.common.exceptions import HotelSuspended

        expire_hotel_subscription(self.hotel)
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save(update_fields=["status"])
        with self.assertRaises(HotelSuspended):
            ensure_hotel_operational(self.hotel)

    def test_subscription_state_shape(self):
        state = subscription_state(self.hotel)
        self.assertFalse(state["write_blocked"])
        expire_hotel_subscription(self.hotel)
        state = subscription_state(self.hotel)
        self.assertTrue(state["expired"])
        self.assertTrue(state["write_blocked"])
        self.assertEqual(state["blocked_reason"], "subscription_inactive")

    def test_batch_blocked_ids_matches_per_hotel_rule(self):
        """Phase 17: the batch used by list endpoints must agree with the
        per-hotel check for every subscription situation."""
        plan = SubscriptionPlan.objects.create(name="P", slug="batch-p", price=0)
        no_history = Hotel.objects.create(
            name="N", slug="n", status=HotelStatus.ACTIVE
        )
        active = Hotel.objects.create(name="A", slug="a", status=HotelStatus.ACTIVE)
        HotelSubscription.objects.create(
            hotel=active,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            ends_at=timezone.now() + datetime.timedelta(days=10),
        )
        open_ended = Hotel.objects.create(
            name="O", slug="o", status=HotelStatus.ACTIVE
        )
        HotelSubscription.objects.create(
            hotel=open_ended, plan=plan, status=SubscriptionStatus.ACTIVE
        )
        trial_over = Hotel.objects.create(
            name="T", slug="t", status=HotelStatus.ACTIVE
        )
        HotelSubscription.objects.create(
            hotel=trial_over,
            plan=plan,
            status=SubscriptionStatus.TRIAL,
            trial_ends_at=timezone.now() - datetime.timedelta(hours=1),
        )
        expired = Hotel.objects.create(name="E", slug="e", status=HotelStatus.ACTIVE)
        expire_hotel_subscription(expired)

        hotels = [self.hotel, no_history, active, open_ended, trial_over, expired]
        batch = subscription_blocked_hotel_ids([h.id for h in hotels])
        for hotel in hotels:
            self.assertEqual(
                hotel.id in batch,
                subscription_blocks_writes(hotel),
                hotel.name,
            )
        self.assertEqual(batch, {trial_over.id, expired.id})


class EnforcementAPITests(APITestCase):
    """One representative important write per app must return 403
    subscription_inactive; representative reads keep working."""

    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Ops", slug="ops", status=HotelStatus.ACTIVE
        )
        HotelSettings.objects.create(hotel=self.hotel)
        self.manager = User.objects.create_user(
            email="m@x.com", password=STRONG, full_name="M"
        )
        HotelMembership.objects.create(
            user=self.manager,
            hotel=self.hotel,
            membership_type=MembershipType.MANAGER,
        )
        self.floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        self.room_type = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD",
            base_capacity=2, max_capacity=2,
        )
        expire_hotel_subscription(self.hotel)
        self.client.force_authenticate(self.manager)

    def hdr(self):
        return {"HTTP_X_HOTEL_ID": str(self.hotel.id)}

    def assert_blocked(self, name, url, body=None):
        r = self.client.post(url, body or {}, format="json", **self.hdr())
        self.assertEqual(r.status_code, 403, f"{name}: {r.status_code}")
        self.assertEqual(r.data["code"], "subscription_inactive", name)

    def test_important_writes_blocked(self):
        cases = [
            ("reservation create", reverse("reservations:reservation-list")),
            ("check-in", reverse("stays:stay-check-in")),
            # Payments/invoices are created via their folio routes; the guard
            # runs before the folio lookup, so a placeholder pk is fine.
            ("payment create", reverse("finance:folio-payment-create", args=[999])),
            ("expense create", reverse("finance:expense-list")),
            ("invoice create", reverse("finance:folio-invoice-create", args=[999])),
            ("service order create", reverse("services:order-list")),
            ("housekeeping create", reverse("operations:housekeeping-list")),
            ("maintenance create", reverse("operations:maintenance-list")),
            ("staff create", reverse("staff:staff-list")),
            ("shift open", reverse("shifts:shift-list")),
            ("daily close", reverse("shifts:daily-close-close")),
            ("room create", reverse("rooms:room-list")),
        ]
        for name, url in cases:
            self.assert_blocked(name, url)
        # Guests validate before their guard (perform_create) — send a valid
        # body so the request reaches the enforcement and is refused there.
        self.assert_blocked(
            "guest create",
            reverse("guests:guest-list"),
            {"full_name": "Blocked Guest", "phone": "+90 555 000"},
        )

    def test_permissions_update_blocked(self):
        staff = User.objects.create_user(
            email="s@x.com", password=STRONG, full_name="S"
        )
        membership = HotelMembership.objects.create(
            user=staff, hotel=self.hotel, membership_type=MembershipType.STAFF
        )
        r = self.client.put(
            reverse("staff:staff-permissions", args=[membership.id]),
            {"permissions": []},
            format="json",
            **self.hdr(),
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "subscription_inactive")

    def test_reads_still_work(self):
        for name in (
            "reservations:reservation-list",
            "finance:folio-list",
            "reports:overview",
            "notifications:notification-list",
            "staff:staff-list",
        ):
            r = self.client.get(reverse(name), **self.hdr())
            self.assertEqual(r.status_code, 200, name)

    def test_settings_read_works(self):
        r = self.client.get("/api/v1/hotel/settings/", **self.hdr())
        self.assertEqual(r.status_code, 200)

    def test_profile_exposes_subscription_state(self):
        r = self.client.get("/api/v1/hotel/profile/", **self.hdr())
        self.assertEqual(r.status_code, 200)
        state = r.data["subscription_state"]
        self.assertTrue(state["write_blocked"])
        self.assertEqual(state["blocked_reason"], "subscription_inactive")

    def test_nothing_deleted(self):
        self.assertTrue(Hotel.objects.filter(id=self.hotel.id).exists())
        self.assertEqual(HotelSubscription.objects.filter(hotel=self.hotel).count(), 1)


class PublicBookingEnforcementTests(APITestCase):
    """Phase 15 public booking must stop when the subscription is inactive
    and must keep working while it is active."""

    def setUp(self):
        self.hotel = Hotel.objects.create(
            name="Pub", slug="pub", status=HotelStatus.ACTIVE
        )
        self.settings_obj = HotelSettings.objects.create(
            hotel=self.hotel,
            public_is_listed=True,
            public_slug="pub",
            allow_public_booking=True,
        )
        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        self.room_type = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD",
            base_capacity=2, max_capacity=2, public_is_visible=True,
        )
        from apps.rooms.models import Room

        Room.objects.create(
            hotel=self.hotel, floor=floor, room_type=self.room_type, number="101"
        )

    def book(self):
        check_in = timezone.localdate() + datetime.timedelta(days=7)
        return self.client.post(
            reverse("public_site:booking-create", args=["pub"]),
            {
                "check_in": str(check_in),
                "check_out": str(check_in + datetime.timedelta(days=2)),
                "room_type": self.room_type.id,
                "rooms_count": 1,
                "adults": 2,
                "guest_name": "Visitor",
                "guest_phone": "+90 555",
                "accept_terms": True,
            },
            format="json",
        )

    def test_booking_works_with_active_subscription(self):
        plan = SubscriptionPlan.objects.create(name="P", slug="p", price=0)
        HotelSubscription.objects.create(
            hotel=self.hotel,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            ends_at=timezone.now() + datetime.timedelta(days=30),
        )
        self.assertEqual(self.book().status_code, 201)

    def test_booking_blocked_when_subscription_inactive(self):
        expire_hotel_subscription(self.hotel)
        r = self.book()
        self.assertEqual(r.status_code, 403)
        # The hotel may stay listed, but booking is closed.
        detail = self.client.get(
            reverse("public_site:hotel-detail", args=["pub"])
        ).data
        self.assertFalse(detail["booking_enabled"])

    def test_booking_works_with_no_subscription_history(self):
        # Not-yet-onboarded hotels are not blocked (documented decision).
        self.assertEqual(self.book().status_code, 201)
