"""Tests for notifications + activity center (Phase 14).

Covers access control, tenant isolation, the suspended-hotel read+user-state
rule, ACT/NTF numbering, metadata scrubbing, internal-only related URLs,
permission-matched recipients (managers + section viewers only; never the
actor, a deactivated member or another hotel), the recipient-only inbox
operations (read/all-read/archive), the activity visibility split
(view vs view_all/manager), the wired event subset, and regression.
"""
from __future__ import annotations

from decimal import Decimal

from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.finance.models import PaymentMethod
from apps.finance.services import create_folio, record_payment, void_payment
from apps.notifications.models import ActivityEvent, Notification
from apps.notifications.services import (
    create_notification,
    record_activity,
    safe_metadata,
    safe_related_url,
)
from apps.rbac.services import grant_permission
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

STRONG = "StrongPass!234"


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=()):
    user = User.objects.create_user(email=email, password=STRONG, full_name=email.split("@")[0])
    m = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True
    )
    for code in perms:
        grant_permission(m, code)
    return user


class NotificationsMixin:
    def act_on(self, name, pk=None, body=None, hotel=None):
        args = [pk] if pk is not None else []
        return self.client.post(
            reverse(f"notifications:{name}", args=args),
            body or {},
            format="json",
            **HDR(hotel or self.hotel),
        )


# --------------------------------------------------------------------------- #
# Access / permissions                                                          #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase, NotificationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(
                reverse("notifications:notification-list"), **HDR(self.hotel)
            ).status_code,
            401,
        )

    def test_no_membership_denied(self):
        lonely = User.objects.create_user(email="l@x.com", password=STRONG, full_name="L")
        self.client.force_authenticate(lonely)
        self.assertEqual(
            self.client.get(
                reverse("notifications:notification-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_platform_owner_without_membership_denied(self):
        owner = User.objects.create_user(email="p@x.com", password=STRONG, full_name="P")
        owner.account_type = AccountType.PLATFORM_OWNER
        owner.save(update_fields=["account_type"])
        self.client.force_authenticate(owner)
        for name in ("notification-list", "activity-list", "overview"):
            self.assertEqual(
                self.client.get(
                    reverse(f"notifications:{name}"), **HDR(self.hotel)
                ).status_code,
                403,
                name,
            )

    def test_manager_can_view(self):
        self.client.force_authenticate(self.manager)
        for name in ("notification-list", "activity-list", "overview", "unread-count"):
            self.assertEqual(
                self.client.get(
                    reverse(f"notifications:{name}"), **HDR(self.hotel)
                ).status_code,
                200,
                name,
            )

    def test_staff_permission_split(self):
        viewer = add_member(self.hotel, "v@x.com", perms=["notifications.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(
            self.client.get(
                reverse("notifications:notification-list"), **HDR(self.hotel)
            ).status_code,
            200,
        )
        # No notifications.update -> cannot mark read.
        n = create_notification(
            self.hotel, recipient=viewer, title="Hello", category="system"
        )
        self.assertEqual(self.act_on("mark-read", n.id).status_code, 403)
        # No activity.view -> no activity center.
        self.assertEqual(
            self.client.get(
                reverse("notifications:activity-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_staff_without_view_denied(self):
        worker = add_member(self.hotel, "w@x.com", perms=["rooms.view"])
        self.client.force_authenticate(worker)
        self.assertEqual(
            self.client.get(
                reverse("notifications:notification-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_hotel_isolation(self):
        record_activity(
            self.hotel, event_type="x", category="system", title="A event"
        )
        other = make_hotel(slug="o")
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(om)
        listed = self.client.get(
            reverse("notifications:activity-list"), **HDR(other)
        ).data
        self.assertEqual(listed["count"], 0)
        listed = self.client.get(
            reverse("notifications:notification-list"), **HDR(other)
        ).data
        self.assertEqual(listed["count"], 0)

    def test_suspended_hotel_read_and_user_state_allowed(self):
        hotel = make_hotel(slug="susp", status=HotelStatus.SUSPENDED)
        manager = add_member(hotel, "sm@x.com", kind=MembershipType.MANAGER)
        n = create_notification(hotel, recipient=manager, title="Hi", category="system")
        self.client.force_authenticate(manager)
        # Reading AND marking read/archiving stay allowed — user-state only
        # (documented decision).
        self.assertEqual(
            self.client.get(
                reverse("notifications:notification-list"), **HDR(hotel)
            ).status_code,
            200,
        )
        self.assertEqual(self.act_on("mark-read", n.id, hotel=hotel).status_code, 200)
        self.assertEqual(self.act_on("archive", n.id, hotel=hotel).status_code, 200)


# --------------------------------------------------------------------------- #
# ActivityEvent + Notification services                                         #
# --------------------------------------------------------------------------- #


class ServiceTests(APITestCase, NotificationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_numbers_generated_per_hotel(self):
        e1 = record_activity(self.hotel, event_type="x", category="system", title="A")
        e2 = record_activity(self.hotel, event_type="x", category="system", title="B")
        self.assertEqual(e1.event_number, "ACT00001")
        self.assertEqual(e2.event_number, "ACT00002")
        other = make_hotel(slug="o")
        e3 = record_activity(other, event_type="x", category="system", title="C")
        self.assertEqual(e3.event_number, "ACT00001")

    def test_metadata_scrubbed(self):
        self.assertEqual(
            safe_metadata(
                {
                    "amount": "10.00",
                    "password": "nope",
                    "api_key": "nope",
                    "auth_token": "nope",
                    "AUTHORIZATION": "nope",
                    "nested": {"deep": 1},
                    "ok_flag": True,
                }
            ),
            {"amount": "10.00", "ok_flag": True},
        )
        event = record_activity(
            self.hotel, event_type="x", category="system", title="A",
            metadata={"password": "secret", "count": 3},
        )
        self.assertEqual(event.metadata_json, {"count": 3})

    def test_related_url_internal_only(self):
        self.assertEqual(safe_related_url("/hotel/finance"), "/hotel/finance")
        self.assertEqual(safe_related_url("https://evil.example.com"), "")
        self.assertEqual(safe_related_url("//evil.example.com"), "")
        self.assertEqual(safe_related_url("javascript:alert(1)"), "")

    def test_notification_requires_active_member(self):
        outsider = User.objects.create_user(email="out@x.com", password=STRONG, full_name="O")
        self.assertIsNone(
            create_notification(self.hotel, recipient=outsider, title="X", category="system")
        )

    def test_deactivated_member_receives_nothing(self):
        staff = add_member(self.hotel, "s@x.com", perms=["finance.view"])
        HotelMembership.objects.filter(user=staff, hotel=self.hotel).update(
            is_active=False
        )
        record_activity(
            self.hotel, event_type="payment.recorded", category="finance",
            title="Payment", actor=self.manager,
        )
        self.assertFalse(Notification.objects.filter(recipient=staff).exists())

    def test_no_delete_endpoints(self):
        self.client.force_authenticate(self.manager)
        n = create_notification(
            self.hotel, recipient=self.manager, title="X", category="system"
        )
        r = self.client.delete(
            reverse("notifications:notification-detail", args=[n.id]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 405)
        event = record_activity(self.hotel, event_type="x", category="system", title="A")
        r = self.client.delete(
            reverse("notifications:activity-detail", args=[event.id]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 405)


# --------------------------------------------------------------------------- #
# Recipients                                                                    #
# --------------------------------------------------------------------------- #


class RecipientTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.finance_staff = add_member(self.hotel, "fin@x.com", perms=["finance.view"])
        self.hk_staff = add_member(self.hotel, "hk@x.com", perms=["housekeeping.view"])
        self.plain_staff = add_member(self.hotel, "plain@x.com", perms=["rooms.view"])

    def recipients_of(self, event):
        return set(
            Notification.objects.filter(activity=event).values_list(
                "recipient__email", flat=True
            )
        )

    def test_finance_event_recipients(self):
        event = record_activity(
            self.hotel, event_type="payment.reversed", category="finance",
            title="Payment", actor=self.plain_staff,
        )
        self.assertEqual(self.recipients_of(event), {"m@x.com", "fin@x.com"})

    def test_operations_event_recipients(self):
        event = record_activity(
            self.hotel, event_type="housekeeping.task_created", category="operation",
            title="Task",
        )
        self.assertEqual(self.recipients_of(event), {"m@x.com", "hk@x.com"})

    def test_actor_not_notified(self):
        event = record_activity(
            self.hotel, event_type="payment.reversed", category="finance",
            title="Payment", actor=self.finance_staff,
        )
        self.assertEqual(self.recipients_of(event), {"m@x.com"})

    def test_system_events_managers_only(self):
        event = record_activity(
            self.hotel, event_type="system.note", category="system", title="Note"
        )
        self.assertEqual(self.recipients_of(event), {"m@x.com"})

    def test_other_hotel_not_notified(self):
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        event = record_activity(
            self.hotel, event_type="payment.reversed", category="finance", title="P"
        )
        self.assertNotIn("om@x.com", self.recipients_of(event))

    def test_platform_owner_without_membership_not_notified(self):
        owner = User.objects.create_user(email="po@x.com", password=STRONG, full_name="PO")
        owner.account_type = AccountType.PLATFORM_OWNER
        owner.save(update_fields=["account_type"])
        event = record_activity(
            self.hotel, event_type="payment.reversed", category="finance", title="P"
        )
        self.assertNotIn("po@x.com", self.recipients_of(event))


# --------------------------------------------------------------------------- #
# Inbox operations                                                              #
# --------------------------------------------------------------------------- #


class InboxTests(APITestCase, NotificationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.other_user = add_member(
            self.hotel, "o@x.com",
            perms=["notifications.view", "notifications.update"],
        )
        self.client.force_authenticate(self.manager)
        self.mine = create_notification(
            self.hotel, recipient=self.manager, title="Mine", category="system"
        )
        self.theirs = create_notification(
            self.hotel, recipient=self.other_user, title="Theirs", category="system"
        )

    def test_user_sees_own_only(self):
        listed = self.client.get(
            reverse("notifications:notification-list"), **HDR(self.hotel)
        ).data
        titles = [row["title"] for row in listed["results"]]
        self.assertIn("Mine", titles)
        self.assertNotIn("Theirs", titles)

    def test_cannot_touch_another_users_notification(self):
        self.assertEqual(self.act_on("mark-read", self.theirs.id).status_code, 404)
        self.assertEqual(self.act_on("archive", self.theirs.id).status_code, 404)
        r = self.client.get(
            reverse("notifications:notification-detail", args=[self.theirs.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 404)

    def test_mark_read_and_all_read(self):
        r = self.act_on("mark-read", self.mine.id)
        self.assertTrue(r.data["is_read"])
        self.assertIsNotNone(r.data["read_at"])
        create_notification(self.hotel, recipient=self.manager, title="Two", category="system")
        r = self.act_on("mark-all-read")
        self.assertEqual(r.data["updated"], 1)
        count = self.client.get(
            reverse("notifications:unread-count"), **HDR(self.hotel)
        ).data
        self.assertEqual(count["unread"], 0)

    def test_archive_hides_from_default_list(self):
        self.act_on("archive", self.mine.id)
        listed = self.client.get(
            reverse("notifications:notification-list"), **HDR(self.hotel)
        ).data
        self.assertEqual(listed["count"], 0)
        archived = self.client.get(
            reverse("notifications:notification-list") + "?archived=true",
            **HDR(self.hotel),
        ).data
        self.assertEqual(archived["count"], 1)

    def test_filters(self):
        create_notification(
            self.hotel, recipient=self.manager, title="Danger!",
            category="finance", severity="danger",
        )
        base = reverse("notifications:notification-list")
        self.assertEqual(
            self.client.get(base + "?severity=danger", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?category=finance", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?unread=true", **HDR(self.hotel)).data["count"], 2
        )

    def test_overview_counts(self):
        create_notification(
            self.hotel, recipient=self.manager, title="W",
            category="finance", severity="warning",
        )
        data = self.client.get(
            reverse("notifications:overview"), **HDR(self.hotel)
        ).data
        self.assertEqual(data["unread_count"], 2)
        self.assertEqual(data["warning_count"], 1)
        self.assertEqual(data["archived_count"], 0)


# --------------------------------------------------------------------------- #
# Activity visibility                                                           #
# --------------------------------------------------------------------------- #


class ActivityVisibilityTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        record_activity(self.hotel, event_type="payment.recorded", category="finance", title="F")
        record_activity(self.hotel, event_type="housekeeping.task_created", category="operation", title="O")

    def test_manager_sees_all(self):
        self.client.force_authenticate(self.manager)
        listed = self.client.get(
            reverse("notifications:activity-list"), **HDR(self.hotel)
        ).data
        self.assertEqual(listed["count"], 2)

    def test_scoped_staff_sees_own_categories_only(self):
        staff = add_member(
            self.hotel, "s@x.com", perms=["activity.view", "finance.view"]
        )
        self.client.force_authenticate(staff)
        listed = self.client.get(
            reverse("notifications:activity-list"), **HDR(self.hotel)
        ).data
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["results"][0]["category"], "finance")

    def test_view_all_staff_sees_everything(self):
        staff = add_member(
            self.hotel, "va@x.com", perms=["activity.view", "activity.view_all"]
        )
        self.client.force_authenticate(staff)
        listed = self.client.get(
            reverse("notifications:activity-list"), **HDR(self.hotel)
        ).data
        self.assertEqual(listed["count"], 2)

    def test_staff_sees_own_actions_regardless(self):
        staff = add_member(self.hotel, "self@x.com", perms=["activity.view"])
        record_activity(
            self.hotel, event_type="shift.closed", category="shift",
            title="Mine", actor=staff,
        )
        self.client.force_authenticate(staff)
        listed = self.client.get(
            reverse("notifications:activity-list"), **HDR(self.hotel)
        ).data
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["results"][0]["title"], "Mine")

    def test_activity_filters(self):
        self.client.force_authenticate(self.manager)
        base = reverse("notifications:activity-list")
        self.assertEqual(
            self.client.get(base + "?category=finance", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(
                base + "?event_type=housekeeping.task_created", **HDR(self.hotel)
            ).data["count"],
            1,
        )


# --------------------------------------------------------------------------- #
# Event wiring (the implemented subset)                                         #
# --------------------------------------------------------------------------- #


class EventWiringTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def types(self):
        return set(
            ActivityEvent.objects.filter(hotel=self.hotel).values_list(
                "event_type", flat=True
            )
        )

    def test_payment_recorded_and_voided_wired(self):
        folio = create_folio(self.hotel, customer_name="W")
        payment = record_payment(
            folio, amount="10.00", method=PaymentMethod.CASH, user=self.manager
        )
        void_payment(payment, reason="entry error", user=self.manager)
        self.assertIn("payment.recorded", self.types())
        self.assertIn("payment.voided", self.types())
        voided_event = ActivityEvent.objects.get(
            hotel=self.hotel, event_type="payment.voided"
        )
        self.assertEqual(voided_event.severity, "danger")
        self.assertEqual(voided_event.related_url, "/hotel/finance")

    def test_reservation_created_and_cancelled_wired(self):
        import datetime

        from apps.reservations.services import cancel_reservation, create_reservation
        from apps.rooms.models import Floor, Room, RoomType

        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        rt = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD", base_capacity=2, max_capacity=2
        )
        Room.objects.create(hotel=self.hotel, floor=floor, room_type=rt, number="101")
        from django.utils import timezone as dj_tz

        today = dj_tz.localdate()
        reservation = create_reservation(
            self.hotel,
            lines=[{"room_type": rt, "quantity": 1}],
            status="confirmed",
            user=self.manager,
            check_in_date=today,
            check_out_date=today + datetime.timedelta(days=1),
            primary_guest_name="G",
        )
        cancel_reservation(reservation, reason="guest changed plans", user=self.manager)
        self.assertIn("reservation.created", self.types())
        self.assertIn("reservation.cancelled", self.types())

    def test_operations_events_wired(self):
        from apps.operations.services import (
            complete_housekeeping_task,
            create_housekeeping_task,
            create_maintenance_request,
            resolve_maintenance_request,
        )
        from apps.rooms.models import Floor, Room, RoomType

        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        rt = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD2", base_capacity=2, max_capacity=2
        )
        room = Room.objects.create(
            hotel=self.hotel, floor=floor, room_type=rt, number="102", status="dirty"
        )
        task = create_housekeeping_task(
            self.hotel, user=self.manager, room=room, priority="normal"
        )
        complete_housekeeping_task(task, user=self.manager)
        request = create_maintenance_request(
            self.hotel, user=self.manager, title="AC", category="hvac", priority="normal"
        )
        resolve_maintenance_request(request, user=self.manager)
        for expected in (
            "housekeeping.task_created", "housekeeping.task_completed",
            "maintenance.request_created", "maintenance.request_resolved",
        ):
            self.assertIn(expected, self.types())

    def test_shift_and_daily_close_wired(self):
        from apps.shifts.services import (
            close_business_day,
            close_shift,
            get_business_date,
            open_shift,
        )

        shift = open_shift(
            self.hotel, user=self.manager, opening_cash_amount=Decimal("0.00")
        )
        close_shift(shift, user=self.manager, actual_cash_amount=Decimal("0.00"))
        close_business_day(
            self.hotel, get_business_date(self.hotel), user=self.manager
        )
        self.assertIn("shift.closed", self.types())
        self.assertIn("daily_close.closed", self.types())

    def test_staff_permissions_updated_wired(self):
        from apps.staff.services import set_staff_permissions

        staff = add_member(self.hotel, "s@x.com", perms=["rooms.view"])
        membership = HotelMembership.objects.get(user=staff, hotel=self.hotel)
        set_staff_permissions(
            membership, actor=self.manager, codes=["rooms.view", "guests.view"]
        )
        self.assertIn("staff.permissions_updated", self.types())
        event = ActivityEvent.objects.get(
            hotel=self.hotel, event_type="staff.permissions_updated"
        )
        self.assertEqual(event.target_user_id, staff.id)


# --------------------------------------------------------------------------- #
# Regression                                                                    #
# --------------------------------------------------------------------------- #


class RegressionTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_health_still_works(self):
        self.client.force_authenticate()
        self.assertEqual(self.client.get("/api/health/").status_code, 200)

    def test_existing_phase_endpoints_reachable(self):
        for name in (
            "rooms:room-list", "reservations:reservation-list", "guests:guest-list",
            "stays:stay-list", "finance:folio-list", "services:order-list",
            "operations:housekeeping-list", "staff:staff-list",
            "shifts:shift-list", "reports:overview",
        ):
            self.assertEqual(
                self.client.get(reverse(name), **HDR(self.hotel)).status_code, 200, name
            )

    def test_reports_still_read_only(self):
        r = self.client.post(reverse("reports:overview"), {}, **HDR(self.hotel))
        self.assertEqual(r.status_code, 405)

    def test_no_external_channel_endpoints(self):
        for name in ("whatsapp", "email", "sms", "push", "chat"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"notifications:{name}")
