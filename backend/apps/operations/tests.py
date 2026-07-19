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

    def test_priority_tie_break_is_deterministic(self):
        # Regression: after moving HK to the shared helper the within-priority
        # tie-break stays deterministic. Same priority across separate rooms,
        # identical requested_at -> the order falls through to the final -id
        # (newest first / strictly descending id).
        for i in range(3):
            room = make_room(self.hotel, number=f"31{i}", status=RoomStatus.DIRTY)
            self.create_hk(room=room.id, priority="high")
        HousekeepingTask.objects.filter(hotel=self.hotel, priority="high").update(
            requested_at=timezone.now()
        )
        base = reverse("operations:housekeeping-list")
        rows = self.client.get(
            base + "?ordering=priority&priority=high", **HDR(self.hotel)
        ).data["results"]
        returned = [r["id"] for r in rows]
        self.assertEqual(returned, sorted(returned, reverse=True))
        self.assertGreaterEqual(len(returned), 3)


class MaintenancePriorityOrderingTests(APITestCase, OperationsMixin):
    """Maintenance list must sort priority by SEVERITY (urgent → high → normal
    → low), matching housekeeping, not the raw CharField (which is alphabetical:
    high < low < normal < urgent)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def _seed(self, priorities):
        """One maintenance request per priority; return {priority: id}. Seeded
        in a scrambled order so id order differs from severity order."""
        ids = {}
        for prio in priorities:
            resp = self.create_mt(priority=prio, title=f"Fix {prio}")
            self.assertEqual(resp.status_code, 201)
            ids[prio] = resp.data["id"]
        return ids

    def test_priority_ordering_by_severity(self):
        ids = self._seed(["low", "urgent", "normal", "high"])
        base = reverse("operations:maintenance-list")
        rows = self.client.get(
            base + "?ordering=priority", **HDR(self.hotel)
        ).data["results"]
        self.assertEqual(
            [r["priority"] for r in rows], ["urgent", "high", "normal", "low"]
        )
        self.assertEqual(
            [r["id"] for r in rows],
            [ids["urgent"], ids["high"], ids["normal"], ids["low"]],
        )

    def test_priority_ordering_reversed(self):
        ids = self._seed(["low", "urgent", "normal", "high"])
        base = reverse("operations:maintenance-list")
        rows = self.client.get(
            base + "?ordering=-priority", **HDR(self.hotel)
        ).data["results"]
        self.assertEqual(
            [r["priority"] for r in rows], ["low", "normal", "high", "urgent"]
        )
        self.assertEqual(
            [r["id"] for r in rows],
            [ids["low"], ids["normal"], ids["high"], ids["urgent"]],
        )

    def test_priority_tie_break_is_deterministic(self):
        # Four requests, SAME priority, identical reported_at -> the order falls
        # through to the final -id tie-break (newest first / descending id).
        ids = [
            self.create_mt(priority="high", title=f"Fix {i}").data["id"]
            for i in range(4)
        ]
        MaintenanceRequest.objects.filter(hotel=self.hotel).update(
            reported_at=timezone.now()
        )
        base = reverse("operations:maintenance-list")
        asc = self.client.get(
            base + "?ordering=priority", **HDR(self.hotel)
        ).data["results"]
        self.assertEqual([r["id"] for r in asc], sorted(ids, reverse=True))
        # -priority keeps the SAME within-priority tie-break.
        desc = self.client.get(
            base + "?ordering=-priority", **HDR(self.hotel)
        ).data["results"]
        self.assertEqual([r["id"] for r in desc], sorted(ids, reverse=True))


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

    # --- WP6 goal B: full reservation_number disclosure gate ----------------

    def test_reservation_number_hidden_from_housekeeping_only_caller(self):
        # A housekeeping-only caller (no reservations.view) still sees the
        # operational info (room + arrival date) but NOT the full number.
        import json

        dirty = self._room("401", RoomStatus.DIRTY)
        res = self._arrival(dirty)
        hk_only = add_member(self.hotel, "hkonly@x.com", perms=["housekeeping.view"])
        self.client.force_authenticate(hk_only)
        r = self.client.get(
            reverse("operations:housekeeping-arrivals-not-ready"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        row = r.data[0]
        self.assertEqual(row["room_number"], "401")
        # Operational arrival info is retained.
        self.assertEqual(row["arrival_date"], timezone.localdate().isoformat())
        # The full reservation number is absent — nowhere in the payload.
        self.assertNotIn("reservation_number", row)
        self.assertNotIn(res.reservation_number, json.dumps(r.data))

    def test_reservation_number_visible_with_reservations_view(self):
        dirty = self._room("402", RoomStatus.DIRTY)
        res = self._arrival(dirty)
        caller = add_member(
            self.hotel,
            "resview@x.com",
            perms=["housekeeping.view", "reservations.view"],
        )
        self.client.force_authenticate(caller)
        r = self.client.get(
            reverse("operations:housekeeping-arrivals-not-ready"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        row = r.data[0]
        self.assertEqual(row["arrival_date"], timezone.localdate().isoformat())
        self.assertEqual(row["reservation_number"], res.reservation_number)


# --------------------------------------------------------------------------- #
# WP5 — Housekeeping cleaning-card enrichment (unit context + occupancy +      #
# upcoming-arrival hint), page-level batch maps, no N+1, hotel-scoped.         #
# --------------------------------------------------------------------------- #


class HousekeepingCardEnrichmentTests(APITestCase, OperationsMixin):
    """The HK LIST payload feeds the cleaning card: real unit type / floor,
    derived occupancy, and a COMPACT upcoming-arrival hint (presence + date/time
    ONLY, never the reservation number). Occupancy + arrival are page-level batch
    maps, so the query count stays constant regardless of how many tasks a page
    holds."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.floor = Floor.objects.create(
            hotel=self.hotel, name="First Floor", number="1"
        )
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Deluxe Suite", code="DLX",
            base_capacity=2, max_capacity=2,
        )

    def _room(self, number, status=RoomStatus.DIRTY):
        return Room.objects.create(
            hotel=self.hotel, floor=self.floor, room_type=self.rtype,
            number=number, status=status,
        )

    def _task(self, room):
        return HousekeepingTask.objects.create(
            hotel=self.hotel, task_number=f"HK{room.number}", room=room,
        )

    def _in_house_stay(self, room, *, hotel=None):
        hotel = hotel or self.hotel
        guest = Guest.objects.create(
            hotel=hotel, full_name="Guest", email=f"g{room.number}@{hotel.slug}.com"
        )
        return Stay.objects.create(
            hotel=hotel, room=room, primary_guest=guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=timezone.localdate(),
            planned_check_out_date=timezone.localdate() + timezone.timedelta(days=2),
            actual_check_in_at=timezone.now(),
        )

    def _arrival(self, room, *, arrival_time=None, days_ahead=0, hotel=None,
                 room_type=None, number_suffix=""):
        hotel = hotel or self.hotel
        room_type = room_type or self.rtype
        today = timezone.localdate()
        res = Reservation.objects.create(
            hotel=hotel, reservation_number=f"RSV-{room.number}{number_suffix}",
            status=ReservationStatus.CONFIRMED,
            check_in_date=today + timezone.timedelta(days=days_ahead),
            check_out_date=today + timezone.timedelta(days=days_ahead + 2),
            expected_arrival_time=arrival_time,
            primary_guest_name="Arrival Guest",
        )
        ReservationRoomLine.objects.create(
            hotel=hotel, reservation=res, room_type=room_type,
            room=room, quantity=1,
        )
        return res

    def _list(self, hotel=None):
        return self.client.get(
            reverse("operations:housekeeping-list"), **HDR(hotel or self.hotel)
        )

    def test_list_exposes_unit_and_context_fields(self):
        room = self._room("101")
        self._task(room)
        rows = self._list().data["results"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["room_number"], "101")
        self.assertEqual(row["room_type_name"], "Deluxe Suite")
        self.assertEqual(row["floor_name"], "First Floor")
        self.assertEqual(row["floor_number"], "1")
        # Additive: the pre-existing fields survive.
        self.assertIn("assigned_to_name", row)
        self.assertIn("requested_at", row)
        # Derived context is present with the documented shapes.
        self.assertIn("is_occupied", row)
        self.assertIsInstance(row["is_occupied"], bool)
        self.assertEqual(
            set(row["upcoming_arrival"]),
            {"has_upcoming", "arrival_date", "arrival_time"},
        )

    def test_is_occupied_true_only_for_in_house_stay(self):
        occupied = self._room("201")
        vacant = self._room("202")
        departed = self._room("203")
        for r in (occupied, vacant, departed):
            self._task(r)
        self._in_house_stay(occupied)
        # A CHECKED-OUT stay is NOT occupancy.
        gone = Guest.objects.create(hotel=self.hotel, full_name="Gone", email="gone@x.com")
        Stay.objects.create(
            hotel=self.hotel, room=departed, primary_guest=gone,
            status=StayStatus.CHECKED_OUT,
            planned_check_in_date=timezone.localdate() - timezone.timedelta(days=1),
            planned_check_out_date=timezone.localdate(),
            actual_check_in_at=timezone.now() - timezone.timedelta(days=1),
            actual_check_out_at=timezone.now(),
        )
        rows = {r["room_number"]: r for r in self._list().data["results"]}
        self.assertTrue(rows["201"]["is_occupied"])
        self.assertFalse(rows["202"]["is_occupied"])
        self.assertFalse(rows["203"]["is_occupied"])

    def test_upcoming_arrival_reflects_near_arrival_and_hides_reservation_number(self):
        import datetime
        import json

        arriving = self._room("301")
        quiet = self._room("302")
        self._task(arriving)
        self._task(quiet)
        res = self._arrival(arriving, arrival_time=datetime.time(14, 30))
        rows = {r["room_number"]: r for r in self._list().data["results"]}

        ua = rows["301"]["upcoming_arrival"]
        self.assertTrue(ua["has_upcoming"])
        self.assertEqual(ua["arrival_date"], timezone.localdate().isoformat())
        self.assertEqual(ua["arrival_time"], "14:30:00")
        self.assertFalse(rows["302"]["upcoming_arrival"]["has_upcoming"])
        self.assertIsNone(rows["302"]["upcoming_arrival"]["arrival_date"])

        # HK-only privacy: the full reservation number appears NOWHERE — neither
        # as a task field nor inside the arrival hint.
        blob = json.dumps(rows)
        self.assertNotIn(res.reservation_number, blob)
        self.assertNotIn("reservation_number", rows["301"])
        self.assertNotIn("reservation_number", ua)

    def test_arrival_outside_near_window_is_not_flagged(self):
        room = self._room("305")
        self._task(room)
        # A far-future arrival (beyond today + UPCOMING_ARRIVAL_WINDOW_DAYS) must
        # not surface on the card.
        self._arrival(room, days_ahead=10)
        rows = self._list().data["results"]
        self.assertFalse(rows[0]["upcoming_arrival"]["has_upcoming"])

    def test_query_count_is_constant_regardless_of_task_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def seed(start, end):
            for i in range(start, end):
                room = self._room(f"4{i:02d}")
                self._task(room)
                # Exercise BOTH batch maps for every row.
                self._in_house_stay(room)
                self._arrival(room, days_ahead=0)

        # ONE task on the page.
        seed(0, 1)
        # Warm up so any one-time setup query does not skew the baseline.
        self._list()
        with CaptureQueriesContext(connection) as ctx:
            resp1 = self._list()
        self.assertEqual(len(resp1.data["results"]), 1)
        baseline = len(ctx.captured_queries)

        # Grow the page to FOUR tasks/rooms/stays/arrivals: the count must NOT
        # grow with the number of rows (batch maps prove no N+1).
        seed(1, 4)
        with self.assertNumQueries(baseline):
            resp4 = self._list()
        self.assertEqual(len(resp4.data["results"]), 4)

    def test_maps_are_hotel_scoped(self):
        room = self._room("501")
        self._task(room)
        # Another hotel with its OWN occupied room + near arrival on the SAME
        # room number: neither may leak into this hotel's card.
        other = make_hotel(slug="oiso")
        ofloor = Floor.objects.create(hotel=other, name="OF", number="9")
        otype = RoomType.objects.create(
            hotel=other, name="OStd", code="OSTD", base_capacity=2, max_capacity=2
        )
        oroom = Room.objects.create(
            hotel=other, floor=ofloor, room_type=otype, number="501",
            status=RoomStatus.DIRTY,
        )
        self._in_house_stay(oroom, hotel=other)
        self._arrival(oroom, hotel=other, room_type=otype, number_suffix="X")

        rows = self._list().data["results"]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_occupied"])
        self.assertFalse(rows[0]["upcoming_arrival"]["has_upcoming"])


# --------------------------------------------------------------------------- #
# WP6 — closure safety: initial-assign permission gate (goal A) + restricted    #
# disclosure of internal_notes / full reservation_number / phone (goal B),      #
# all within the EXISTING RBAC, fail-closed.                                    #
# --------------------------------------------------------------------------- #


class InitialAssignPermissionTests(APITestCase, OperationsMixin):
    """Goal A: supplying an assignee at CREATE time requires the domain's
    ``.assign`` permission IN ADDITION to ``.create`` — otherwise 403 (never a
    silent drop, never accepted). Without an assignee, ``.create`` alone still
    creates the item unassigned. Reassignment already requires ``.assign``."""

    def setUp(self):
        self.hotel = make_hotel()
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)
        # An active same-hotel member who is a valid assignee target.
        self.worker = add_member(self.hotel, "w@x.com", perms=["housekeeping.view"])

    # -- Housekeeping --------------------------------------------------------

    def test_hk_create_with_assignee_without_assign_is_403(self):
        creator = add_member(self.hotel, "c@x.com", perms=["housekeeping.create"])
        self.client.force_authenticate(creator)
        r = self.create_hk(assigned_to=self.worker.id)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "permission_denied")
        # The item was NOT created (assignee not silently dropped, not accepted).
        self.assertEqual(HousekeepingTask.objects.filter(hotel=self.hotel).count(), 0)

    def test_hk_create_with_assignee_and_assign_is_201(self):
        creator = add_member(
            self.hotel,
            "c2@x.com",
            perms=["housekeeping.create", "housekeeping.assign"],
        )
        self.client.force_authenticate(creator)
        r = self.create_hk(assigned_to=self.worker.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["assigned_to"], self.worker.id)
        self.assertEqual(r.data["status"], "assigned")

    def test_hk_create_without_assignee_only_needs_create(self):
        creator = add_member(self.hotel, "c3@x.com", perms=["housekeeping.create"])
        self.client.force_authenticate(creator)
        r = self.create_hk()
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.data["assigned_to"])

    def test_hk_create_with_explicit_null_assignee_only_needs_create(self):
        creator = add_member(self.hotel, "c4@x.com", perms=["housekeeping.create"])
        self.client.force_authenticate(creator)
        r = self.create_hk(assigned_to=None)
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.data["assigned_to"])

    # -- Maintenance ---------------------------------------------------------

    def test_mt_create_with_assignee_without_assign_is_403(self):
        creator = add_member(self.hotel, "cm@x.com", perms=["maintenance.create"])
        self.client.force_authenticate(creator)
        r = self.create_mt(assigned_to=self.worker.id)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "permission_denied")
        self.assertEqual(
            MaintenanceRequest.objects.filter(hotel=self.hotel).count(), 0
        )

    def test_mt_create_with_assignee_and_assign_is_201(self):
        creator = add_member(
            self.hotel,
            "cm2@x.com",
            perms=["maintenance.create", "maintenance.assign"],
        )
        self.client.force_authenticate(creator)
        r = self.create_mt(assigned_to=self.worker.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["assigned_to"], self.worker.id)

    def test_mt_create_without_assignee_only_needs_create(self):
        creator = add_member(self.hotel, "cm3@x.com", perms=["maintenance.create"])
        self.client.force_authenticate(creator)
        r = self.create_mt()
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.data["assigned_to"])

    def test_reassignment_still_requires_assign_permission(self):
        # A .create-only caller creates unassigned, then cannot reassign via the
        # dedicated assign endpoint (which is gated on .assign) — 403.
        creator = add_member(
            self.hotel, "c5@x.com", perms=["housekeeping.create", "housekeeping.view"]
        )
        self.client.force_authenticate(creator)
        task = self.create_hk().data
        r = self.act("housekeeping", task["id"], "assign", {"assigned_to": self.worker.id})
        self.assertEqual(r.status_code, 403)


class DisclosureGateTests(APITestCase, OperationsMixin):
    """Goal B: internal_notes / claimed_by_phone are disclosed only within the
    existing RBAC and never leak into lists/cards; fail-closed without a request
    context."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel, status=RoomStatus.DIRTY)

    # -- internal_notes ------------------------------------------------------

    def test_hk_internal_notes_gated_detail_and_absent_from_list(self):
        self.client.force_authenticate(self.manager)
        task = self.create_hk(internal_notes="staff only note").data
        detail_url = reverse("operations:housekeeping-detail", args=[task["id"]])
        list_url = reverse("operations:housekeeping-list")

        # Actor with status_update sees internal_notes.
        actor = add_member(
            self.hotel,
            "a@x.com",
            perms=["housekeeping.view", "housekeeping.status_update"],
        )
        self.client.force_authenticate(actor)
        self.assertEqual(
            self.client.get(detail_url, **HDR(self.hotel)).data["internal_notes"],
            "staff only note",
        )

        # Actor with update (also view to read) sees it too.
        updater = add_member(
            self.hotel,
            "u@x.com",
            perms=["housekeeping.view", "housekeeping.update"],
        )
        self.client.force_authenticate(updater)
        self.assertEqual(
            self.client.get(detail_url, **HDR(self.hotel)).data["internal_notes"],
            "staff only note",
        )

        # A view-only caller: internal_notes dropped.
        viewer = add_member(self.hotel, "v@x.com", perms=["housekeeping.view"])
        self.client.force_authenticate(viewer)
        self.assertNotIn(
            "internal_notes", self.client.get(detail_url, **HDR(self.hotel)).data
        )

        # The list/card never carries internal_notes, even for the manager.
        self.client.force_authenticate(self.manager)
        rows = self.client.get(list_url, **HDR(self.hotel)).data["results"]
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("internal_notes", row)

    def test_mt_internal_notes_gated_detail_and_absent_from_list(self):
        self.client.force_authenticate(self.manager)
        req = self.create_mt(internal_notes="mt secret").data
        detail_url = reverse("operations:maintenance-detail", args=[req["id"]])

        viewer = add_member(self.hotel, "mv@x.com", perms=["maintenance.view"])
        self.client.force_authenticate(viewer)
        self.assertNotIn(
            "internal_notes", self.client.get(detail_url, **HDR(self.hotel)).data
        )
        rows = self.client.get(
            reverse("operations:maintenance-list"), **HDR(self.hotel)
        ).data["results"]
        for row in rows:
            self.assertNotIn("internal_notes", row)

        actor = add_member(
            self.hotel,
            "ma@x.com",
            perms=["maintenance.view", "maintenance.status_update"],
        )
        self.client.force_authenticate(actor)
        self.assertEqual(
            self.client.get(detail_url, **HDR(self.hotel)).data["internal_notes"],
            "mt secret",
        )

    # -- Lost & Found: internal_notes + claimant phone -----------------------

    def test_lf_internal_notes_and_phone_gated(self):
        self.client.force_authenticate(self.manager)
        item = self.create_lf(internal_notes="lf secret").data
        # Capture a claimant phone through the claim flow.
        self.act(
            "lost-found",
            item["id"],
            "claim",
            {"claimed_by_name": "John Smith", "claimed_by_phone": "+90 555 111"},
        )
        detail_url = reverse("operations:lost-found-detail", args=[item["id"]])
        list_url = reverse("operations:lost-found-list")

        # A view-only caller sees NEITHER the internal notes NOR the phone,
        # but the claimant NAME may remain (not over-restricted).
        viewer = add_member(self.hotel, "lv@x.com", perms=["lost_found.view"])
        self.client.force_authenticate(viewer)
        d = self.client.get(detail_url, **HDR(self.hotel)).data
        self.assertNotIn("internal_notes", d)
        self.assertNotIn("claimed_by_phone", d)
        self.assertEqual(d["claimed_by_name"], "John Smith")

        # The list/card never carries the phone (or internal_notes).
        rows = self.client.get(list_url, **HDR(self.hotel)).data["results"]
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("claimed_by_phone", row)
            self.assertNotIn("internal_notes", row)

        # A holder of lost_found.status_update (the claim/return actor) sees both.
        actor = add_member(
            self.hotel,
            "la@x.com",
            perms=["lost_found.view", "lost_found.status_update"],
        )
        self.client.force_authenticate(actor)
        d = self.client.get(detail_url, **HDR(self.hotel)).data
        self.assertEqual(d["claimed_by_phone"], "+90 555 111")
        self.assertEqual(d["internal_notes"], "lf secret")

    def test_lf_claim_response_shows_phone_to_actor(self):
        # The claim/return path itself: the actor holds lost_found.status_update,
        # so the phone captured in that flow is visible in the action response.
        actor = add_member(
            self.hotel,
            "lca@x.com",
            perms=[
                "lost_found.view",
                "lost_found.create",
                "lost_found.status_update",
            ],
        )
        self.client.force_authenticate(actor)
        item = self.create_lf().data
        r = self.act(
            "lost-found",
            item["id"],
            "claim",
            {"claimed_by_name": "Jane", "claimed_by_phone": "+1 222"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["claimed_by_phone"], "+1 222")

    def test_lf_serializer_fail_closed_without_request_context(self):
        # Fail-closed: a serializer used WITHOUT a request context drops the
        # gated sensitive fields entirely (never shown as a fallback).
        from apps.operations.serializers import LostFoundItemSerializer

        self.client.force_authenticate(self.manager)
        item_data = self.create_lf(internal_notes="secret").data
        item = LostFoundItem.objects.get(pk=item_data["id"])
        item.claimed_by_phone = "+90 000"
        item.save(update_fields=["claimed_by_phone"])
        data = LostFoundItemSerializer(item).data  # no context
        self.assertNotIn("internal_notes", data)
        self.assertNotIn("claimed_by_phone", data)


# --------------------------------------------------------------------------- #
# WP7 — sensitive lost & found proof-of-ownership on handover                    #
# --------------------------------------------------------------------------- #


class SensitiveClaimProofTests(APITestCase, OperationsMixin):
    """WP7: money / jewelry / documents require a recipient name, a phone OR a
    linked guest, and a proof type + reference on claim/return; normal
    categories keep the existing minimum. The proof REFERENCE is bounded,
    privacy-validated (identity_last4 <= 4) and gated on read like the phone."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.room = make_room(self.hotel)
        self.client.force_authenticate(self.manager)

    def _proof(self, **extra):
        body = {
            "claimed_by_name": "John Smith",
            "claimed_by_phone": "+90 555 111",
            "claim_proof_type": "receipt_reference",
            "claim_proof_reference": "RCP-9910",
        }
        body.update(extra)
        return body

    # -- Enforcement on the SENSITIVE set ------------------------------------

    def test_sensitive_claim_without_proof_rejected(self):
        item = self.create_lf(category="money").data
        r = self.act(
            "lost-found", item["id"], "claim",
            {"claimed_by_name": "John", "claimed_by_phone": "+90 555"},
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claim_proof_required")
        self.assertEqual(r.data["details"]["reason"], "proof_type_required")

    def test_sensitive_claim_without_name_rejected(self):
        item = self.create_lf(category="jewelry").data
        r = self.act(
            "lost-found", item["id"], "claim",
            self._proof(claimed_by_name=""),
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claim_proof_required")
        self.assertEqual(r.data["details"]["reason"], "recipient_name_required")

    def test_sensitive_claim_without_phone_or_guest_rejected(self):
        item = self.create_lf(category="documents").data
        r = self.act(
            "lost-found", item["id"], "claim",
            self._proof(claimed_by_phone=""),
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claim_proof_required")
        self.assertEqual(r.data["details"]["reason"], "phone_or_guest_required")

    def test_sensitive_claim_missing_reference_rejected(self):
        item = self.create_lf(category="money").data
        r = self.act(
            "lost-found", item["id"], "claim",
            self._proof(claim_proof_reference=""),
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claim_proof_required")
        self.assertEqual(r.data["details"]["reason"], "proof_reference_required")

    def test_sensitive_claim_with_all_fields_succeeds_and_stores(self):
        item = self.create_lf(category="money").data
        r = self.act("lost-found", item["id"], "claim", self._proof())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "claimed")
        self.assertEqual(r.data["claim_proof_type"], "receipt_reference")
        # The manager holds status_update, so the reference is visible here.
        self.assertEqual(r.data["claim_proof_reference"], "RCP-9910")
        obj = LostFoundItem.objects.get(pk=item["id"])
        self.assertEqual(obj.claim_proof_type, "receipt_reference")
        self.assertEqual(obj.claim_proof_reference, "RCP-9910")

    def test_sensitive_claim_with_guest_and_no_phone_ok(self):
        guest = Guest.objects.create(hotel=self.hotel, full_name="G", email="gg@x.com")
        item = self.create_lf(category="jewelry", guest=guest.id).data
        r = self.act(
            "lost-found", item["id"], "claim",
            {
                "claimed_by_name": "John",
                "claim_proof_type": "ownership_description",
                "claim_proof_reference": "gold ring, engraved 2019",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "claimed")

    def test_sensitive_return_requires_proof(self):
        item = self.create_lf(category="money").data
        r = self.act(
            "lost-found", item["id"], "return",
            {"claimed_by_name": "John", "claimed_by_phone": "+90 555"},
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claim_proof_required")
        r = self.act("lost-found", item["id"], "return", self._proof())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "returned")

    def test_sensitive_return_reuses_stored_claim_proof(self):
        # Claim with proof, then return WITHOUT re-supplying it: the return
        # reuses the stored name/phone/proof (like the name/phone fallback).
        item = self.create_lf(category="documents").data
        self.act("lost-found", item["id"], "claim", self._proof())
        r = self.act("lost-found", item["id"], "return", {})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "returned")

    # -- NORMAL categories keep the existing minimum -------------------------

    def test_normal_category_claim_needs_no_proof(self):
        item = self.create_lf(category="clothing").data
        r = self.act("lost-found", item["id"], "claim", {"claimed_by_name": "John"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "claimed")

    def test_normal_category_return_needs_no_proof(self):
        item = self.create_lf(category="electronics").data
        r = self.act("lost-found", item["id"], "return", {"claimed_by_name": "Jane"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "returned")

    def test_normal_category_still_requires_claimant(self):
        item = self.create_lf(category="clothing").data
        r = self.act("lost-found", item["id"], "claim", {})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claimant_required")

    # -- Proof-type specific validation --------------------------------------

    def test_identity_last4_rejects_long_value(self):
        item = self.create_lf(category="money").data
        r = self.act(
            "lost-found", item["id"], "claim",
            self._proof(
                claim_proof_type="identity_last4",
                claim_proof_reference="123456789",
            ),
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claim_proof_required")
        self.assertEqual(r.data["details"]["reason"], "identity_last4_too_long")

    def test_identity_last4_four_chars_ok(self):
        item = self.create_lf(category="money").data
        r = self.act(
            "lost-found", item["id"], "claim",
            self._proof(
                claim_proof_type="identity_last4", claim_proof_reference="4321"
            ),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            LostFoundItem.objects.get(pk=item["id"]).claim_proof_reference, "4321"
        )

    def test_ownership_description_requires_nonempty(self):
        item = self.create_lf(category="documents").data
        r = self.act(
            "lost-found", item["id"], "claim",
            self._proof(
                claim_proof_type="ownership_description",
                claim_proof_reference="",
            ),
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "claim_proof_required")

    # -- Privacy: the reference is gated / never leaks -----------------------

    def test_reference_absent_from_list(self):
        item = self.create_lf(category="money").data
        self.act("lost-found", item["id"], "claim", self._proof())
        rows = self.client.get(
            reverse("operations:lost-found-list"), **HDR(self.hotel)
        ).data["results"]
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("claim_proof_reference", row)
            self.assertNotIn("claim_proof_type", row)

    def test_reference_gated_to_status_update_in_detail(self):
        item = self.create_lf(category="money").data
        self.act(
            "lost-found", item["id"], "claim",
            self._proof(claim_proof_reference="RCP-SECRET"),
        )
        detail_url = reverse("operations:lost-found-detail", args=[item["id"]])

        # A view-only caller: the reference is dropped, but the (non-sensitive)
        # proof TYPE is still visible.
        viewer = add_member(self.hotel, "lv@x.com", perms=["lost_found.view"])
        self.client.force_authenticate(viewer)
        d = self.client.get(detail_url, **HDR(self.hotel)).data
        self.assertNotIn("claim_proof_reference", d)
        self.assertEqual(d["claim_proof_type"], "receipt_reference")

        # A lost_found.status_update holder (the claim/return actor) sees it.
        actor = add_member(
            self.hotel, "la@x.com",
            perms=["lost_found.view", "lost_found.status_update"],
        )
        self.client.force_authenticate(actor)
        d = self.client.get(detail_url, **HDR(self.hotel)).data
        self.assertEqual(d["claim_proof_reference"], "RCP-SECRET")

    def test_reference_fail_closed_without_request_context(self):
        from apps.operations.serializers import LostFoundItemSerializer

        item_data = self.create_lf(category="money").data
        item = LostFoundItem.objects.get(pk=item_data["id"])
        item.claim_proof_type = "receipt_reference"
        item.claim_proof_reference = "RCP-NOCTX"
        item.save(update_fields=["claim_proof_type", "claim_proof_reference"])
        data = LostFoundItemSerializer(item).data  # no context
        self.assertNotIn("claim_proof_reference", data)
        # The type marker is not sensitive and remains present.
        self.assertEqual(data["claim_proof_type"], "receipt_reference")

    def test_reference_never_in_status_log_or_activity(self):
        from apps.notifications.models import ActivityEvent

        secret = "RCP-DO-NOT-LEAK-42"
        item = self.create_lf(category="money").data
        self.act(
            "lost-found", item["id"], "claim",
            self._proof(claim_proof_reference=secret),
        )
        self.act("lost-found", item["id"], "return", {})  # reuses stored proof
        detail_url = reverse("operations:lost-found-detail", args=[item["id"]])
        d = self.client.get(detail_url, **HDR(self.hotel)).data
        for log in d["status_logs"]:
            self.assertNotIn(secret, (log.get("note") or ""))
        # The reference must not appear in any activity event payload either.
        for ev in ActivityEvent.objects.filter(hotel=self.hotel):
            self.assertNotIn(secret, ev.title)
            self.assertNotIn(secret, ev.message)
