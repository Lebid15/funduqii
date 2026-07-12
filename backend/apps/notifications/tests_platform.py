"""Notifications final closure tests — platform-owner notifications, scope
isolation, dedup/idempotency, and the notify=False noise control.

Complements the Phase 14 suite (never replaces it). Everything routes through
the central services; no new RBAC permission is introduced.
"""
from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.notifications import services as N
from apps.notifications.models import (
    ActivityEvent,
    Notification,
    NotificationScope,
)
from apps.platform.services import create_hotel
from apps.rbac.services import grant_permission
from apps.subscriptions import services as S
from apps.subscriptions.models import SubscriptionPlan
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

STRONG = "StrongPass!234"


def HDR(h):
    return {"HTTP_X_HOTEL_ID": str(h.id)}


def make_owner(email="owner@platform.local"):
    return User.objects.create_user(
        email=email, password=STRONG, full_name="Owner",
        account_type=AccountType.PLATFORM_OWNER,
    )


def make_manager(hotel, email="mgr@hotel.local"):
    u = User.objects.create_user(email=email, password=STRONG, full_name="Mgr")
    HotelMembership.objects.create(
        user=u, hotel=hotel, membership_type=MembershipType.MANAGER, is_active=True
    )
    return u


def make_plan(slug="basic", **kw):
    d = dict(name="Basic", slug=slug, price=Decimal("49.00"), currency="USD",
             billing_cycle="monthly", trial_days=14, is_active=True)
    d.update(kw)
    return SubscriptionPlan.objects.create(**d)


def platform_notifs(user):
    return Notification.objects.filter(
        recipient=user, scope=NotificationScope.PLATFORM
    )


# --- Platform notifications: sourcing ----------------------------------------


class PlatformSourcingTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()

    def test_hotel_registered_notifies_owner_only(self):
        before = platform_notifs(self.owner).count()
        hotel = create_hotel(name="H", slug="h")
        self.assertEqual(platform_notifs(self.owner).count(), before + 1)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=hotel,
                scope=NotificationScope.PLATFORM,
                event_type="platform.hotel_registered",
            ).exists()
        )

    def test_hotel_registered_dedup(self):
        hotel = create_hotel(name="H", slug="h")
        n1 = platform_notifs(self.owner).count()
        # Re-emitting the same registration event does not duplicate.
        N.notify_platform_owners(
            event_type="platform.hotel_registered", title="dup", hotel=hotel,
            dedup_key=f"platform.hotel_registered:platform:{hotel.id}",
        )
        self.assertEqual(platform_notifs(self.owner).count(), n1)

    def test_subscription_events_notify_owner(self):
        hotel = create_hotel(name="H", slug="h")
        plan = make_plan()
        base = platform_notifs(self.owner).count()
        S.activate_subscription(hotel, plan)
        self.assertEqual(platform_notifs(self.owner).count(), base + 1)
        sub = S.get_current_subscription(hotel)
        S.renew_subscription(sub, days=30)
        S.record_platform_payment(
            hotel, amount=Decimal("49"), currency="USD", method="cash"
        )
        # activated + renewed + payment_recorded = 3 new platform notifications.
        self.assertEqual(platform_notifs(self.owner).count(), base + 3)

    def test_two_owners_each_notified(self):
        owner2 = make_owner("owner2@platform.local")
        create_hotel(name="H", slug="h")
        self.assertEqual(platform_notifs(self.owner).count(), 1)
        self.assertEqual(platform_notifs(owner2).count(), 1)


# --- Scope isolation ----------------------------------------------------------


class ScopeIsolationTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.hotel = create_hotel(name="H", slug="h")
        self.manager = make_manager(self.hotel)

    def test_platform_notification_not_in_hotel_console(self):
        # A subscription event fans out to the hotel manager (system) AND the
        # owner (platform). The manager's hotel inbox must contain no platform row.
        S.activate_subscription(self.hotel, make_plan())
        self.client.force_authenticate(self.manager)
        rows = self.client.get(
            reverse("notifications:notification-list"), **HDR(self.hotel)
        ).data["results"]
        self.assertTrue(all(r["scope"] == "hotel" for r in rows))

    def test_hotel_notification_not_in_platform_centre(self):
        # A pure hotel event (reservation) never appears in the platform centre.
        N.record_activity(
            self.hotel, event_type="reservation.created", category="reservation",
            title="R",
        )
        self.assertEqual(
            platform_notifs(self.owner)
            .filter(activity__event_type="reservation.created")
            .count(),
            0,
        )


# --- Platform API: RBAC + operations -----------------------------------------


class PlatformApiTests(APITestCase):
    def setUp(self):
        self.owner = make_owner()
        self.hotel = create_hotel(name="H", slug="h")  # 1 platform notification
        self.manager = make_manager(self.hotel)

    def test_owner_overview_and_unread(self):
        self.client.force_authenticate(self.owner)
        ov = self.client.get(reverse("platform_notifications:overview"))
        self.assertEqual(ov.status_code, 200)
        self.assertGreaterEqual(ov.data["unread_count"], 1)
        uc = self.client.get(reverse("platform_notifications:unread-count"))
        self.assertGreaterEqual(uc.data["unread"], 1)

    def test_manager_denied_platform_endpoints(self):
        self.client.force_authenticate(self.manager)
        for name in ("platform_notifications:overview",
                     "platform_notifications:unread-count",
                     "platform_notifications:list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_owner_mark_read_and_all_and_archive(self):
        self.client.force_authenticate(self.owner)
        n = platform_notifs(self.owner).first()
        r = self.client.post(
            reverse("platform_notifications:mark-read", args=[n.id])
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["is_read"])
        create_hotel(name="H2", slug="h2")  # another unread
        allr = self.client.post(reverse("platform_notifications:mark-all-read"))
        self.assertGreaterEqual(allr.data["updated"], 1)
        self.assertEqual(
            platform_notifs(self.owner).filter(is_read=False).count(), 0
        )
        arch = self.client.post(
            reverse("platform_notifications:archive", args=[n.id])
        )
        self.assertTrue(arch.data["is_archived"])

    def test_owner_list_excludes_hotel_notifications(self):
        # Give the owner a (hypothetical) hotel notification and ensure the
        # platform list never shows it.
        Notification.objects.create(
            hotel=self.hotel, scope=NotificationScope.HOTEL,
            notification_number="NTF99999", recipient=self.owner,
            category="system", title="hotelrow",
        )
        self.client.force_authenticate(self.owner)
        rows = self.client.get(reverse("platform_notifications:list")).data["results"]
        self.assertTrue(all(r["scope"] == "platform" for r in rows))

    def test_get_does_not_write(self):
        self.client.force_authenticate(self.owner)
        before = platform_notifs(self.owner).count()
        self.client.get(reverse("platform_notifications:list"))
        self.client.get(reverse("platform_notifications:overview"))
        self.assertEqual(platform_notifs(self.owner).count(), before)


# --- Deduplication ------------------------------------------------------------


class DedupTests(APITestCase):
    def setUp(self):
        self.hotel = create_hotel(name="H", slug="h")
        self.user = make_manager(self.hotel)

    def test_dedup_prevents_duplicate(self):
        a = N.create_notification(self.hotel, recipient=self.user, title="A",
                                  dedup_key="k1")
        b = N.create_notification(self.hotel, recipient=self.user, title="B",
                                  dedup_key="k1")
        self.assertEqual(a.id, b.id)  # same row returned (idempotent)
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, dedup_key="k1").count(), 1
        )

    def test_different_key_allows_new(self):
        N.create_notification(self.hotel, recipient=self.user, title="A", dedup_key="k1")
        N.create_notification(self.hotel, recipient=self.user, title="B", dedup_key="k2")
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.user, dedup_key__isnull=False
            ).count(),
            2,
        )

    def test_same_key_different_recipient_allows(self):
        other = make_manager(self.hotel, "other@x.local")
        N.create_notification(self.hotel, recipient=self.user, title="A", dedup_key="k1")
        N.create_notification(self.hotel, recipient=other, title="A", dedup_key="k1")
        self.assertEqual(Notification.objects.filter(dedup_key="k1").count(), 2)

    def test_no_key_keeps_legacy_behaviour(self):
        N.create_notification(self.hotel, recipient=self.user, title="A")
        N.create_notification(self.hotel, recipient=self.user, title="A")
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, dedup_key__isnull=True).count(),
            2,
        )


# --- Noise control (notify=False) --------------------------------------------


class NoiseControlTests(APITestCase):
    def setUp(self):
        self.hotel = create_hotel(name="H", slug="h")
        self.manager = make_manager(self.hotel)

    def _notifs_for(self, event):
        return Notification.objects.filter(activity=event).count()

    def test_routine_event_is_activity_only(self):
        for et in ("stay.checked_in", "shift.opened", "service_order.created",
                   "payment.recorded", "report.exported"):
            ev = N.record_activity(self.hotel, event_type=et, category="system",
                                   title=et)
            self.assertEqual(self._notifs_for(ev), 0, et)
            self.assertTrue(ActivityEvent.objects.filter(pk=ev.pk).exists())

    def test_important_event_still_notifies(self):
        ev = N.record_activity(self.hotel, event_type="reservation.created",
                               category="reservation", title="R")
        self.assertGreaterEqual(self._notifs_for(ev), 1)
