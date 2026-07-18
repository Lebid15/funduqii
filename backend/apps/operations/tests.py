"""Tests for operations (Phase 10): housekeeping, maintenance, lost & found.

Covers access/permissions, tenant isolation, the suspended-hotel read-only
rule, HK/MT/LF numbering, status workflows + logs, the room-status integration
(never `occupied`; housekeeping never overrides a maintenance block; closing
maintenance never auto-releases a room) and the check-out auto-task.
"""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.guests.models import Guest
from apps.operations.models import (
    HousekeepingStatus,
    HousekeepingTask,
    HousekeepingTaskType,
    LostFoundItem,
    LostFoundStatus,
    MaintenanceRequest,
    MaintenanceStatus,
)
from apps.operations.services import create_checkout_cleaning_task
from apps.rbac.services import grant_permission
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.rooms.services import change_room_status
from apps.stays.models import Stay, StayStatus
from apps.stays.services import CheckOutService
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

HK_PERMS = [
    "housekeeping.view", "housekeeping.create", "housekeeping.update",
    "housekeeping.cancel", "housekeeping.status_update", "housekeeping.assign",
]
MT_PERMS = [
    "maintenance.view", "maintenance.create", "maintenance.update",
    "maintenance.cancel", "maintenance.status_update", "maintenance.assign",
    "maintenance.close",
]
LF_PERMS = [
    "lost_found.view", "lost_found.create", "lost_found.update",
    "lost_found.status_update", "lost_found.close",
]


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=()):
    user = User.objects.create_user(
        email=email, password="StrongPass!234", full_name="Member"
    )
    m = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True
    )
    for code in perms:
        grant_permission(m, code)
    return user


def make_room(hotel, number="101", status=RoomStatus.AVAILABLE):
    floor = Floor.objects.create(hotel=hotel, name="G", number="0")
    rt = RoomType.objects.create(
        hotel=hotel, name="Std", code=f"S{number}", base_capacity=2, max_capacity=2
    )
    return Room.objects.create(
        hotel=hotel, floor=floor, room_type=rt, number=number, status=status
    )


def make_stay(hotel, room, *, status=StayStatus.IN_HOUSE):
    guest = Guest.objects.create(hotel=hotel, full_name="Guest One", email="g@x.com")
    return Stay.objects.create(
        hotel=hotel,
        room=room,
        primary_guest=guest,
        status=status,
        planned_check_in_date=timezone.localdate(),
        planned_check_out_date=timezone.localdate() + timezone.timedelta(days=2),
        actual_check_in_at=timezone.now(),
    )


class OperationsMixin:
    def create_hk(self, hotel=None, **body):
        hotel = hotel or self.hotel
        body.setdefault("room", self.room.id)
        return self.client.post(
            reverse("operations:housekeeping-list"), body, format="json", **HDR(hotel)
        )

    def create_mt(self, hotel=None, **body):
        hotel = hotel or self.hotel
        body.setdefault("title", "Broken AC")
        return self.client.post(
            reverse("operations:maintenance-list"), body, format="json", **HDR(hotel)
        )

    def create_lf(self, hotel=None, **body):
        hotel = hotel or self.hotel
        body.setdefault("title", "Black wallet")
        return self.client.post(
            reverse("operations:lost-found-list"), body, format="json", **HDR(hotel)
        )

    def act(self, kind, pk, action, body=None, hotel=None):
        return self.client.post(
            reverse(f"operations:{kind}-{action}", args=[pk]),
            body or {},
            format="json",
            **HDR(hotel or self.hotel),
        )


# --------------------------------------------------------------------------- #
# Access / permissions                                                          #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(
                reverse("operations:housekeeping-list"), **HDR(self.hotel)
            ).status_code,
            401,
        )

    def test_no_membership_denied(self):
        lonely = User.objects.create_user(
            email="l@x.com", password="StrongPass!234", full_name="L"
        )
        self.client.force_authenticate(lonely)
        self.assertEqual(
            self.client.get(
                reverse("operations:maintenance-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_platform_owner_without_membership_denied(self):
        owner = User.objects.create_user(
            email="p@x.com", password="StrongPass!234", full_name="P"
        )
        owner.account_type = AccountType.PLATFORM_OWNER
        owner.save(update_fields=["account_type"])
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(
                reverse("operations:lost-found-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )

    def test_other_hotel_data_invisible(self):
        self.client.force_authenticate(self.manager)
        task = self.create_hk().data
        other = make_hotel(slug="o")
        other_manager = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(other_manager)
        r = self.client.get(
            reverse("operations:housekeeping-detail", args=[task["id"]]), **HDR(other)
        )
        self.assertEqual(r.status_code, 404)
        listed = self.client.get(
            reverse("operations:housekeeping-list"), **HDR(other)
        ).data["results"]
        self.assertEqual(listed, [])

    def test_manager_can_manage_all_sections(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.create_hk().status_code, 201)
        self.assertEqual(self.create_mt().status_code, 201)
        self.assertEqual(self.create_lf().status_code, 201)

    def test_staff_view_only_cannot_create(self):
        staff = add_member(self.hotel, "s@x.com", perms=["housekeeping.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(
                reverse("operations:housekeeping-list"), **HDR(self.hotel)
            ).status_code,
            200,
        )
        self.assertEqual(self.create_hk().status_code, 403)

    def test_staff_with_create_can_create(self):
        staff = add_member(
            self.hotel, "s2@x.com", perms=["housekeeping.view", "housekeeping.create"]
        )
        self.client.force_authenticate(staff)
        self.assertEqual(self.create_hk().status_code, 201)

    def test_housekeeping_perms_do_not_unlock_maintenance(self):
        staff = add_member(self.hotel, "s3@x.com", perms=HK_PERMS)
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(
                reverse("operations:maintenance-list"), **HDR(self.hotel)
            ).status_code,
            403,
        )
        self.assertEqual(self.create_mt().status_code, 403)

    def test_maintenance_perms_do_not_unlock_lost_found(self):
        staff = add_member(self.hotel, "s4@x.com", perms=MT_PERMS)
        self.client.force_authenticate(staff)
        self.assertEqual(self.create_mt().status_code, 201)
        self.assertEqual(self.create_lf().status_code, 403)

    def test_lost_found_perms_scoped(self):
        staff = add_member(self.hotel, "s5@x.com", perms=LF_PERMS)
        self.client.force_authenticate(staff)
        self.assertEqual(self.create_lf().status_code, 201)
        self.assertEqual(self.create_hk().status_code, 403)

    def test_overview_reachable_with_any_view_permission(self):
        staff = add_member(self.hotel, "s6@x.com", perms=["lost_found.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(
                reverse("operations:overview"), **HDR(self.hotel)
            ).status_code,
            200,
        )
        none_staff = add_member(self.hotel, "s7@x.com", perms=["rooms.view"])
        self.client.force_authenticate(none_staff)
        self.assertEqual(
            self.client.get(
                reverse("operations:overview"), **HDR(self.hotel)
            ).status_code,
            403,
        )


class SuspendedHotelTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel(status=HotelStatus.SUSPENDED)
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel)
        self.client.force_authenticate(self.manager)

    def test_view_allowed(self):
        for name in ("housekeeping-list", "maintenance-list", "lost-found-list", "overview"):
            self.assertEqual(
                self.client.get(
                    reverse(f"operations:{name}"), **HDR(self.hotel)
                ).status_code,
                200,
            )

    def test_writes_blocked(self):
        r = self.create_hk()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "hotel_suspended")
        self.assertEqual(self.create_mt().data["code"], "hotel_suspended")
        self.assertEqual(self.create_lf().data["code"], "hotel_suspended")

    def test_actions_blocked(self):
        task = HousekeepingTask.objects.create(
            hotel=self.hotel, task_number="HK00001", room=self.room
        )
        for action, body in (
            ("status", {"status": "in_progress"}),
            ("assign", {"assigned_to": None}),
            ("complete", {}),
            ("cancel", {"reason": "x"}),
        ):
            r = self.act("housekeeping", task.id, action, body)
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.data["code"], "hotel_suspended")


# --------------------------------------------------------------------------- #
# Housekeeping                                                                  #
# --------------------------------------------------------------------------- #


class HousekeepingTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)
        self.client.force_authenticate(self.manager)

    def test_create_generates_number(self):
        r = self.create_hk(task_type="deep_cleaning", priority="high")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["task_number"], "HK00001")
        self.assertEqual(r.data["status"], "pending")
        # Final closure: one active task per room — use a second room.
        room2 = make_room(self.hotel, number="102", status=RoomStatus.DIRTY)
        self.assertEqual(
            self.create_hk(room=room2.id).data["task_number"], "HK00002"
        )

    def test_numbering_is_per_hotel(self):
        self.create_hk()
        other = make_hotel(slug="o")
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        oroom = make_room(other)
        self.client.force_authenticate(om)
        r = self.create_hk(hotel=other, room=oroom.id)
        self.assertEqual(r.data["task_number"], "HK00001")

    def test_list_filters_and_search(self):
        self.create_hk(priority="urgent")
        # Final closure: one active task per room — the second task needs its
        # own room (completed/cancelled tasks would still count on room 1).
        room2 = make_room(self.hotel, number="103", status=RoomStatus.DIRTY)
        self.create_hk(task_type="inspection", room=room2.id)
        base = reverse("operations:housekeeping-list")
        self.assertEqual(
            self.client.get(base + "?priority=urgent", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?task_type=inspection", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?search=HK00002", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + f"?room={self.room.id}", **HDR(self.hotel)).data["count"], 1
        )

    def test_cross_tenant_room_rejected(self):
        other_room = make_room(make_hotel(slug="o"), number="900")
        self.assertEqual(self.create_hk(room=other_room.id).status_code, 404)

    def test_cross_tenant_stay_rejected(self):
        other = make_hotel(slug="o2")
        ostay = make_stay(other, make_room(other, number="901"))
        self.assertEqual(self.create_hk(stay=ostay.id).status_code, 404)

    def test_assign_requires_same_hotel_member(self):
        outsider = User.objects.create_user(
            email="out@x.com", password="StrongPass!234", full_name="Out"
        )
        task = self.create_hk().data
        r = self.act("housekeeping", task["id"], "assign", {"assigned_to": outsider.id})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "cross_tenant_reference")

    def test_assign_invalid_user_rejected(self):
        task = self.create_hk().data
        r = self.act("housekeeping", task["id"], "assign", {"assigned_to": 99999})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "cross_tenant_reference")

    def test_assign_moves_pending_to_assigned(self):
        staff = add_member(self.hotel, "hk@x.com", perms=["housekeeping.view"])
        task = self.create_hk().data
        r = self.act("housekeeping", task["id"], "assign", {"assigned_to": staff.id})
        self.assertEqual(r.data["status"], "assigned")
        self.assertEqual(r.data["assigned_to"], staff.id)

    def test_start_sets_room_cleaning_and_started_at(self):
        task = self.create_hk().data
        r = self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.data["started_at"])
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.CLEANING)

    def test_generic_status_cannot_complete_or_cancel(self):
        task = self.create_hk().data
        for target in ("completed", "cancelled"):
            r = self.act("housekeeping", task["id"], "status", {"status": target})
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.data["code"], "invalid_operation_status_transition")

    def test_status_log_created(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        detail = self.client.get(
            reverse("operations:housekeeping-detail", args=[task["id"]]), **HDR(self.hotel)
        ).data
        transitions = [(l["previous_status"], l["new_status"]) for l in detail["status_logs"]]
        self.assertIn(("pending", "in_progress"), transitions)
        self.assertIn(("", "pending"), transitions)

    def test_cancel_requires_reason(self):
        task = self.create_hk().data
        r = self.act("housekeeping", task["id"], "cancel", {"reason": ""})
        self.assertEqual(r.status_code, 400)

    def test_cancel_returns_cleaning_room_to_dirty(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        r = self.act("housekeeping", task["id"], "cancel", {"reason": "guest returned"})
        self.assertEqual(r.data["status"], "cancelled")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.DIRTY)

    def test_complete_can_release_room_when_safe(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        r = self.act(
            "housekeeping", task["id"], "complete", {"mark_room_available": True}
        )
        self.assertEqual(r.data["status"], "completed")
        self.assertIsNotNone(r.data["completed_at"])
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)

    def test_complete_without_release_keeps_room_dirty(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        self.act("housekeeping", task["id"], "complete", {})
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.DIRTY)

    def test_cannot_release_room_blocked_by_status(self):
        change_room_status(
            self.room, RoomStatus.MAINTENANCE, note="pump", user=self.manager
        )
        task = self.create_hk().data
        r = self.act(
            "housekeeping", task["id"], "complete", {"mark_room_available": True}
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_blocked_by_maintenance")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.MAINTENANCE)

    def test_cannot_release_room_with_open_blocking_request(self):
        self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        )
        # Ops staff manually pulled the room back to dirty; the open request
        # must STILL prevent housekeeping from releasing it.
        change_room_status(self.room, RoomStatus.DIRTY, note="", user=self.manager)
        self.room.refresh_from_db()
        task = self.create_hk().data
        r = self.act(
            "housekeeping", task["id"], "complete", {"mark_room_available": True}
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_blocked_by_maintenance")

    def test_completed_task_not_editable(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "complete", {})
        r = self.client.patch(
            reverse("operations:housekeeping-detail", args=[task["id"]]),
            {"priority": "high"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "operation_not_editable")

    def test_no_delete_endpoint(self):
        task = self.create_hk().data
        r = self.client.delete(
            reverse("operations:housekeeping-detail", args=[task["id"]]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 405)
        self.assertTrue(HousekeepingTask.objects.filter(pk=task["id"]).exists())


# --------------------------------------------------------------------------- #
# Maintenance                                                                   #
# --------------------------------------------------------------------------- #


class MaintenanceTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel, status=RoomStatus.AVAILABLE)
        self.client.force_authenticate(self.manager)

    def test_create_generates_number(self):
        r = self.create_mt(category="plumbing", priority="urgent")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["request_number"], "MT00001")
        self.assertEqual(r.data["status"], "open")

    def test_blocking_request_moves_room_to_maintenance(self):
        self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        )
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.MAINTENANCE)

    def test_blocking_request_moves_room_out_of_service(self):
        self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="out_of_service",
        )
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.OUT_OF_SERVICE)

    def test_affecting_request_requires_room_and_block(self):
        r = self.create_mt(affects_room_availability=True, room_block_status="none")
        self.assertEqual(r.status_code, 400)
        r = self.create_mt(affects_room_availability=True, room_block_status="maintenance")
        self.assertEqual(r.status_code, 400)  # no room given

    def test_non_affecting_request_leaves_room_alone(self):
        self.create_mt(room=self.room.id)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)

    def test_list_filters_and_search(self):
        self.create_mt(title="AC broken", category="hvac")
        self.create_mt(
            title="Leaking sink",
            category="plumbing",
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        )
        base = reverse("operations:maintenance-list")
        self.assertEqual(
            self.client.get(base + "?category=hvac", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?search=Leaking", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(
                base + "?affects_room_availability=true", **HDR(self.hotel)
            ).data["count"],
            1,
        )

    def test_cross_tenant_room_rejected(self):
        other_room = make_room(make_hotel(slug="o"), number="900")
        self.assertEqual(self.create_mt(room=other_room.id).status_code, 404)

    def test_assign_requires_member(self):
        req = self.create_mt().data
        outsider = User.objects.create_user(
            email="out@x.com", password="StrongPass!234", full_name="Out"
        )
        r = self.act("maintenance", req["id"], "assign", {"assigned_to": outsider.id})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "cross_tenant_reference")
        tech = add_member(self.hotel, "t@x.com", perms=["maintenance.view"])
        r = self.act("maintenance", req["id"], "assign", {"assigned_to": tech.id})
        self.assertEqual(r.data["status"], "assigned")

    def test_status_workflow_and_log(self):
        req = self.create_mt().data
        r = self.act("maintenance", req["id"], "status", {"status": "in_progress"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.data["started_at"])
        r = self.act("maintenance", req["id"], "status", {"status": "closed"})
        self.assertEqual(r.status_code, 400)
        detail = self.client.get(
            reverse("operations:maintenance-detail", args=[req["id"]]), **HDR(self.hotel)
        ).data
        transitions = [(l["previous_status"], l["new_status"]) for l in detail["status_logs"]]
        self.assertIn(("open", "in_progress"), transitions)

    def test_resolve_then_close_marks_room_dirty(self):
        req = self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        ).data
        r = self.act("maintenance", req["id"], "resolve", {"resolution_notes": "fixed"})
        self.assertEqual(r.data["status"], "resolved")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.MAINTENANCE)  # not auto-released
        r = self.act("maintenance", req["id"], "close", {"room_next_status": "dirty"})
        self.assertEqual(r.data["status"], "closed")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.DIRTY)

    def test_close_can_release_room_explicitly(self):
        req = self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        ).data
        self.act("maintenance", req["id"], "resolve", {})
        self.act("maintenance", req["id"], "close", {"room_next_status": "available"})
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)

    def test_close_keep_leaves_room_blocked(self):
        req = self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="out_of_service",
        ).data
        self.act("maintenance", req["id"], "resolve", {})
        self.act("maintenance", req["id"], "close", {"room_next_status": "keep"})
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.OUT_OF_SERVICE)

    def test_close_available_blocked_by_other_open_request(self):
        self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="out_of_service",
            title="Second issue",
        )
        req = self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        ).data
        self.act("maintenance", req["id"], "resolve", {})
        r = self.act("maintenance", req["id"], "close", {"room_next_status": "available"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_blocked_by_maintenance")

    def test_close_requires_resolved(self):
        req = self.create_mt().data
        r = self.act("maintenance", req["id"], "close", {"room_next_status": "dirty"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_operation_status_transition")

    def test_cancel_requires_reason_and_releases_block_to_dirty(self):
        req = self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        ).data
        r = self.act("maintenance", req["id"], "cancel", {"reason": ""})
        self.assertEqual(r.status_code, 400)
        r = self.act("maintenance", req["id"], "cancel", {"reason": "duplicate"})
        self.assertEqual(r.data["status"], "cancelled")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.DIRTY)

    def test_closed_request_not_editable(self):
        req = self.create_mt().data
        self.act("maintenance", req["id"], "resolve", {})
        self.act("maintenance", req["id"], "close", {})
        r = self.client.patch(
            reverse("operations:maintenance-detail", args=[req["id"]]),
            {"priority": "high"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        r = self.act("maintenance", req["id"], "cancel", {"reason": "x"})
        self.assertEqual(r.status_code, 409)

    def test_no_delete_endpoint(self):
        req = self.create_mt().data
        r = self.client.delete(
            reverse("operations:maintenance-detail", args=[req["id"]]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 405)
        self.assertTrue(MaintenanceRequest.objects.filter(pk=req["id"]).exists())


# --------------------------------------------------------------------------- #
# Lost & Found                                                                  #
# --------------------------------------------------------------------------- #


class LostFoundTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel)
        self.client.force_authenticate(self.manager)

    def test_create_generates_number(self):
        r = self.create_lf(category="electronics", found_location="Lobby")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["item_number"], "LF00001")
        self.assertEqual(r.data["status"], "found")

    def test_list_filters_and_search(self):
        self.create_lf(title="Phone", category="electronics", room=self.room.id)
        self.create_lf(title="Passport", category="documents")
        base = reverse("operations:lost-found-list")
        self.assertEqual(
            self.client.get(base + "?category=documents", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?search=Phone", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + f"?room={self.room.id}", **HDR(self.hotel)).data["count"], 1
        )

    def test_cross_tenant_guest_rejected(self):
        other = make_hotel(slug="o")
        oguest = Guest.objects.create(hotel=other, full_name="Foreign", email="f@x.com")
        self.assertEqual(self.create_lf(guest=oguest.id).status_code, 404)

    def test_store_via_status(self):
        item = self.create_lf().data
        r = self.act("lost-found", item["id"], "status", {"status": "stored"})
        self.assertEqual(r.data["status"], "stored")

    def test_generic_status_rejects_jumps(self):
        item = self.create_lf().data
        r = self.act("lost-found", item["id"], "status", {"status": "returned"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_operation_status_transition")

    def test_claim_records_claimant(self):
        item = self.create_lf().data
        r = self.act(
            "lost-found", item["id"], "claim",
            {"claimed_by_name": "John Smith", "claimed_by_phone": "+90 555"},
        )
        self.assertEqual(r.data["status"], "claimed")
        self.assertEqual(r.data["claimed_by_name"], "John Smith")
        self.assertIsNotNone(r.data["claimed_at"])

    def test_claim_requires_claimant_or_guest(self):
        item = self.create_lf().data
        r = self.act("lost-found", item["id"], "claim", {})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claimant_required")

    def test_claim_with_linked_guest_allowed(self):
        guest = Guest.objects.create(hotel=self.hotel, full_name="G", email="gg@x.com")
        item = self.create_lf(guest=guest.id).data
        r = self.act("lost-found", item["id"], "claim", {})
        self.assertEqual(r.status_code, 200)

    def test_return_requires_claimant(self):
        item = self.create_lf().data
        r = self.act("lost-found", item["id"], "return", {})
        self.assertEqual(r.status_code, 422)
        r = self.act("lost-found", item["id"], "return", {"claimed_by_name": "Jane"})
        self.assertEqual(r.data["status"], "returned")
        self.assertIsNotNone(r.data["returned_at"])

    def test_dispose_requires_reason(self):
        item = self.create_lf().data
        r = self.act("lost-found", item["id"], "dispose", {})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "disposal_reason_required")
        r = self.act("lost-found", item["id"], "dispose", {"reason": "perishable"})
        self.assertEqual(r.data["status"], "disposed")

    def test_close_only_after_returned_or_disposed(self):
        item = self.create_lf().data
        r = self.act("lost-found", item["id"], "close", {})
        self.assertEqual(r.status_code, 400)
        self.act("lost-found", item["id"], "return", {"claimed_by_name": "Jane"})
        r = self.act("lost-found", item["id"], "close", {})
        self.assertEqual(r.data["status"], "closed")

    def test_status_log_created(self):
        item = self.create_lf().data
        self.act("lost-found", item["id"], "status", {"status": "stored"})
        detail = self.client.get(
            reverse("operations:lost-found-detail", args=[item["id"]]), **HDR(self.hotel)
        ).data
        transitions = [(l["previous_status"], l["new_status"]) for l in detail["status_logs"]]
        self.assertIn(("found", "stored"), transitions)

    def test_returned_item_not_editable(self):
        item = self.create_lf().data
        self.act("lost-found", item["id"], "return", {"claimed_by_name": "Jane"})
        r = self.client.patch(
            reverse("operations:lost-found-detail", args=[item["id"]]),
            {"title": "New"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "operation_not_editable")

    def test_no_delete_endpoint(self):
        item = self.create_lf().data
        r = self.client.delete(
            reverse("operations:lost-found-detail", args=[item["id"]]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 405)
        self.assertTrue(LostFoundItem.objects.filter(pk=item["id"]).exists())


# --------------------------------------------------------------------------- #
# Room status integration & regression                                          #
# --------------------------------------------------------------------------- #


class RoomStatusIntegrationTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel)
        self.client.force_authenticate(self.manager)

    def test_checkout_marks_room_dirty_and_creates_task(self):
        stay = make_stay(self.hotel, self.room)
        # The stay ends in two days, so today's check-out is an early
        # departure — the closure round made its reason mandatory.
        CheckOutService.execute(stay, checkout_reason="early", user=self.manager)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.DIRTY)
        tasks = HousekeepingTask.objects.filter(
            stay=stay, task_type=HousekeepingTaskType.CHECKOUT_CLEANING
        )
        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.first().status, HousekeepingStatus.PENDING)

    def test_checkout_task_is_idempotent(self):
        stay = make_stay(self.hotel, self.room)
        CheckOutService.execute(stay, checkout_reason="early", user=self.manager)
        self.assertIsNone(create_checkout_cleaning_task(stay, user=self.manager))
        self.assertEqual(
            HousekeepingTask.objects.filter(
                stay=stay, task_type=HousekeepingTaskType.CHECKOUT_CLEANING
            ).count(),
            1,
        )

    def test_no_occupied_room_status_exists(self):
        self.assertNotIn("occupied", {c for c, _ in RoomStatus.choices})

    def test_occupancy_still_derived_from_stay(self):
        stay = make_stay(self.hotel, self.room)
        self.room.refresh_from_db()
        # An in-house stay never touches the manual room status.
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)
        self.assertEqual(stay.status, StayStatus.IN_HOUSE)

    def test_room_apis_still_work_after_operations(self):
        self.create_hk()
        self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        )
        r = self.client.get(reverse("rooms:room-list"), **HDR(self.hotel))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)

    def test_overview_counters(self):
        room2 = Room.objects.create(
            hotel=self.hotel,
            floor=self.room.floor,
            room_type=self.room.room_type,
            number="102",
            status=RoomStatus.DIRTY,
        )
        self.create_hk(room=room2.id, priority="urgent")
        self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
            priority="urgent",
        )
        self.create_lf()
        data = self.client.get(reverse("operations:overview"), **HDR(self.hotel)).data
        self.assertEqual(data["dirty_rooms"], 1)
        self.assertEqual(data["hk_pending"], 1)
        self.assertEqual(data["open_maintenance"], 1)
        self.assertEqual(data["rooms_under_maintenance"], 1)
        self.assertEqual(data["lost_found_open"], 1)
        self.assertEqual(data["urgent_tasks"], 2)

    def test_no_out_of_scope_endpoints(self):
        for name in ("shifts", "daily-close", "inventory", "purchasing", "reports"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"operations:{name}-list")


# --------------------------------------------------------------------------- #
# Final closure round                                                          #
# --------------------------------------------------------------------------- #

from apps.hotels.models import HotelSettings
from apps.notifications.models import ActivityEvent
from apps.operations.services import create_checkout_cleaning_task as _auto_task
from apps.reservations.models import Reservation, ReservationRoomLine, ReservationStatus


def _enable_inspection(hotel, enabled=True):
    HotelSettings.objects.update_or_create(
        hotel=hotel, defaults={"housekeeping_inspection_required": enabled}
    )


class ActiveTaskCapTests(APITestCase, OperationsMixin):
    """A room may hold at most ONE active housekeeping task."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)
        self.client.force_authenticate(self.manager)

    def test_second_manual_task_refused(self):
        self.assertEqual(self.create_hk().status_code, 201)
        r = self.create_hk()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "duplicate_active_task")

    def test_auto_checkout_task_skips_when_room_busy(self):
        # A manual task is active on the room; check-out's auto task must
        # neither duplicate nor fail.
        self.create_hk()
        stay = make_stay(self.hotel, self.room)
        self.assertIsNone(_auto_task(stay, user=self.manager))
        active = HousekeepingTask.objects.filter(
            hotel=self.hotel, room=self.room,
            status__in=("pending", "assigned", "in_progress", "awaiting_inspection"),
        ).count()
        self.assertEqual(active, 1)

    def test_checkout_idempotency_preserved(self):
        stay = make_stay(self.hotel, self.room)
        first = _auto_task(stay, user=self.manager)
        self.assertIsNotNone(first)
        self.assertIsNone(_auto_task(stay, user=self.manager))

    def test_new_task_allowed_after_completion(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "complete", {"mark_room_available": False})
        self.assertEqual(self.create_hk().status_code, 201)

    def test_new_task_allowed_after_cancellation(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "cancel", {"reason": "test"})
        self.assertEqual(self.create_hk().status_code, 201)

    def test_cap_is_hotel_scoped(self):
        self.create_hk()
        other = make_hotel(slug="ocap")
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        oroom = make_room(other)
        self.client.force_authenticate(om)
        self.assertEqual(self.create_hk(hotel=other, room=oroom.id).status_code, 201)

    def test_awaiting_inspection_counts_as_active(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "complete", {"mark_room_available": True})
        r = self.create_hk()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "duplicate_active_task")


class AssignmentFlowTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.worker = add_member(self.hotel, "w@x.com", perms=["housekeeping.view"])
        self.worker2 = add_member(self.hotel, "w2@x.com", perms=["housekeeping.view"])
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)
        self.client.force_authenticate(self.manager)

    def _assign(self, task_id, user_id):
        return self.act("housekeeping", task_id, "assign", {"assigned_to": user_id})

    def test_assign_reassign_and_activities(self):
        task = self.create_hk().data
        r = self._assign(task["id"], self.worker.id)
        self.assertEqual(r.data["status"], "assigned")
        r = self._assign(task["id"], self.worker2.id)
        self.assertEqual(r.data["assigned_to"], self.worker2.id)
        events = set(
            ActivityEvent.objects.filter(hotel=self.hotel).values_list(
                "event_type", flat=True
            )
        )
        self.assertIn("housekeeping.task_assigned", events)
        self.assertIn("housekeeping.task_reassigned", events)

    def test_unassign_returns_to_pending(self):
        task = self.create_hk().data
        self._assign(task["id"], self.worker.id)
        r = self._assign(task["id"], None)
        self.assertEqual(r.data["status"], "pending")
        self.assertIsNone(r.data["assigned_to"])
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="housekeeping.task_unassigned"
            ).exists()
        )

    def test_mine_filter(self):
        t1 = self.create_hk().data
        room2 = make_room(self.hotel, number="102", status=RoomStatus.DIRTY)
        self.create_hk(room=room2.id)
        self._assign(t1["id"], self.worker.id)
        self.client.force_authenticate(self.worker)
        base = reverse("operations:housekeeping-list")
        mine = self.client.get(base + "?mine=true", **HDR(self.hotel)).data
        self.assertEqual(mine["count"], 1)
        self.assertEqual(mine["results"][0]["id"], t1["id"])

    def test_assign_cross_hotel_member_rejected(self):
        other = make_hotel(slug="oas")
        outsider = add_member(other, "out@x.com", kind=MembershipType.MANAGER)
        task = self.create_hk().data
        r = self._assign(task["id"], outsider.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "cross_tenant_reference")


class InspectionPolicyTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)
        self.client.force_authenticate(self.manager)

    def _inspect(self, task_id, action, body=None):
        return self.client.post(
            reverse(f"operations:housekeeping-inspect-{action}", args=[task_id]),
            body or {}, format="json", **HDR(self.hotel),
        )

    def test_policy_off_keeps_old_behavior(self):
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        r = self.act(
            "housekeeping", task["id"], "complete", {"mark_room_available": True}
        )
        self.assertEqual(r.data["status"], "completed")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)

    def test_policy_on_completion_parks_for_inspection(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        r = self.act(
            "housekeeping", task["id"], "complete", {"mark_room_available": True}
        )
        self.assertEqual(r.data["status"], "awaiting_inspection")
        self.room.refresh_from_db()
        # Room NOT released — still not check-in-ready.
        self.assertNotEqual(self.room.status, RoomStatus.AVAILABLE)

    def test_approve_completes_and_releases(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        self.act("housekeeping", task["id"], "complete", {})
        r = self._inspect(task["id"], "approve")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "completed")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="housekeeping.inspection_approved"
            ).exists()
        )

    def test_reject_requires_reason(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "complete", {})
        r = self._inspect(task["id"], "reject", {"reason": ""})
        self.assertEqual(r.status_code, 400)

    def test_reject_returns_room_dirty_and_task_in_progress(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        self.act("housekeeping", task["id"], "complete", {})
        r = self._inspect(task["id"], "reject", {"reason": "bathroom not clean"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "in_progress")
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.DIRTY)
        # The rejection reason is preserved in the status log.
        logs = self.client.get(
            reverse("operations:housekeeping-detail", args=[task["id"]]),
            **HDR(self.hotel),
        ).data["status_logs"]
        self.assertTrue(any("bathroom not clean" in (l["note"] or "") for l in logs))
        # The attendant can complete it again.
        again = self.act("housekeeping", task["id"], "complete", {})
        self.assertEqual(again.data["status"], "awaiting_inspection")

    def test_inspect_requires_permission(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        # Take the room through a real cleaning cycle (start -> cleaning) before
        # completion so approval can release it: WP1's fail-closed guard refuses
        # to release a still-DIRTY room even on the inspection-approval path
        # (this test only exercises the inspect *permission*, not that edge).
        self.act("housekeeping", task["id"], "status", {"status": "in_progress"})
        self.act("housekeeping", task["id"], "complete", {})
        staff = add_member(
            self.hotel, "s@x.com",
            perms=["housekeeping.view", "housekeeping.status_update"],
        )
        self.client.force_authenticate(staff)
        self.assertEqual(self._inspect(task["id"], "approve").status_code, 403)
        self.assertEqual(
            self._inspect(task["id"], "reject", {"reason": "x"}).status_code, 403
        )
        inspector = add_member(
            self.hotel, "i@x.com", perms=["housekeeping.inspect"]
        )
        self.client.force_authenticate(inspector)
        self.assertEqual(self._inspect(task["id"], "approve").status_code, 200)

    def test_maintenance_block_beats_approval(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        self.act("housekeeping", task["id"], "complete", {})
        # Blocking maintenance appears while awaiting inspection.
        self.create_mt(
            room=self.room.id,
            affects_room_availability=True,
            room_block_status="maintenance",
        )
        r = self._inspect(task["id"], "approve")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "room_blocked_by_maintenance")

    def test_generic_status_cannot_reach_awaiting_inspection(self):
        _enable_inspection(self.hotel)
        task = self.create_hk().data
        r = self.act(
            "housekeeping", task["id"], "status", {"status": "awaiting_inspection"}
        )
        self.assertEqual(r.status_code, 400)


class PriorityOrderingTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        # The mixin's create_hk touches self.room even with an override.
        self.room = make_room(self.hotel, number="299", status=RoomStatus.DIRTY)
        for i, prio in enumerate(["low", "urgent", "normal", "high"]):
            room = make_room(self.hotel, number=f"20{i}", status=RoomStatus.DIRTY)
            self.create_hk(room=room.id, priority=prio)

    def test_priority_ordering_by_severity(self):
        base = reverse("operations:housekeeping-list")
        rows = self.client.get(base + "?ordering=priority", **HDR(self.hotel)).data[
            "results"
        ]
        self.assertEqual(
            [r["priority"] for r in rows], ["urgent", "high", "normal", "low"]
        )
        rows = self.client.get(base + "?ordering=-priority", **HDR(self.hotel)).data[
            "results"
        ]
        self.assertEqual(
            [r["priority"] for r in rows], ["low", "normal", "high", "urgent"]
        )

    def test_priority_change_logged(self):
        base = reverse("operations:housekeeping-list")
        task = self.client.get(base, **HDR(self.hotel)).data["results"][0]
        r = self.client.patch(
            reverse("operations:housekeeping-detail", args=[task["id"]]),
            {"priority": "urgent"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="housekeeping.priority_changed"
        ).latest("id")
        self.assertIn("urgent", event.message)


class ArrivalsNotReadyTests(APITestCase, OperationsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD", base_capacity=2, max_capacity=2
        )
        self.floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")

    def _room(self, number, status=RoomStatus.DIRTY):
        return Room.objects.create(
            hotel=self.hotel, floor=self.floor, room_type=self.rtype,
            number=number, status=status,
        )

    def _arrival(self, room):
        today = timezone.localdate()
        res = Reservation.objects.create(
            hotel=self.hotel, reservation_number=f"RA{room.number}",
            status=ReservationStatus.CONFIRMED,
            check_in_date=today, check_out_date=today + timezone.timedelta(days=2),
            primary_guest_name="Arrival Guest",
        )
        ReservationRoomLine.objects.create(
            hotel=self.hotel, reservation=res, room_type=self.rtype,
            room=room, quantity=1,
        )
        return res

    def test_flags_dirty_arrival_room_only(self):
        dirty = self._room("301", RoomStatus.DIRTY)
        ready = self._room("302", RoomStatus.AVAILABLE)
        self._arrival(dirty)
        self._arrival(ready)
        r = self.client.get(
            reverse("operations:housekeeping-arrivals-not-ready"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        numbers = [row["room_number"] for row in r.data]
        self.assertEqual(numbers, ["301"])
        self.assertEqual(r.data[0]["room_status"], "dirty")

    def test_requires_view_permission(self):
        nobody = add_member(self.hotel, "n@x.com", perms=["rooms.view"])
        self.client.force_authenticate(nobody)
        r = self.client.get(
            reverse("operations:housekeeping-arrivals-not-ready"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 403)
