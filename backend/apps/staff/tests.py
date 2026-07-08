"""Tests for staff & permissions management (Phase 11).

Covers access control, tenant isolation, the suspended-hotel read-only rule,
staff lifecycle (create / link / update / deactivate / reactivate), the
last-manager protection, bulk permission replacement with the escalation
guard, the registry endpoint, the my-permissions context for the sidebar, and
regression (job_title never grants access; no fixed roles).
"""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.rbac.models import HotelPermissionGrant
from apps.rbac.registry import ALL_PERMISSIONS, PERMISSIONS_BY_SECTION
from apps.rbac.services import grant_permission, has_hotel_permission
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

STRONG = "StrongPass!234"


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=(), **extra):
    user = User.objects.create_user(email=email, password=STRONG, full_name="Member")
    m = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True, **extra
    )
    for code in perms:
        grant_permission(m, code)
    return user


def membership_of(user, hotel) -> HotelMembership:
    return HotelMembership.objects.get(user=user, hotel=hotel)


class StaffMixin:
    def create_staff(self, hotel=None, **body):
        hotel = hotel or self.hotel
        payload = {
            "full_name": "New Staff",
            "email": "new.staff@x.com",
            "password": STRONG,
        }
        payload.update(body)
        return self.client.post(
            reverse("staff:staff-list"), payload, format="json", **HDR(hotel)
        )

    def act(self, pk, action, body=None, hotel=None):
        return self.client.post(
            reverse(f"staff:staff-{action}", args=[pk]),
            body or {},
            format="json",
            **HDR(hotel or self.hotel),
        )

    def put_permissions(self, pk, codes, hotel=None):
        return self.client.put(
            reverse("staff:staff-permissions", args=[pk]),
            {"permissions": codes},
            format="json",
            **HDR(hotel or self.hotel),
        )


# --------------------------------------------------------------------------- #
# Access / permissions                                                          #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase, StaffMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(reverse("staff:staff-list"), **HDR(self.hotel)).status_code,
            401,
        )

    def test_no_membership_denied(self):
        lonely = User.objects.create_user(email="l@x.com", password=STRONG, full_name="L")
        self.client.force_authenticate(lonely)
        self.assertEqual(
            self.client.get(reverse("staff:staff-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_platform_owner_without_membership_denied(self):
        owner = User.objects.create_user(email="p@x.com", password=STRONG, full_name="P")
        owner.account_type = AccountType.PLATFORM_OWNER
        owner.save(update_fields=["account_type"])
        self.client.force_authenticate(owner)
        for name in ("staff-list", "overview", "my-permissions"):
            self.assertEqual(
                self.client.get(reverse(f"staff:{name}"), **HDR(self.hotel)).status_code,
                403,
            )

    def test_hotel_a_cannot_access_hotel_b_staff(self):
        other = make_hotel(slug="o")
        other_manager = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        target = membership_of(self.manager, self.hotel)
        self.client.force_authenticate(other_manager)
        r = self.client.get(
            reverse("staff:staff-detail", args=[target.id]), **HDR(other)
        )
        self.assertEqual(r.status_code, 404)
        listed = self.client.get(reverse("staff:staff-list"), **HDR(other)).data
        emails = [row["email"] for row in listed["results"]]
        self.assertNotIn("m@x.com", emails)

    def test_manager_can_do_everything(self):
        self.client.force_authenticate(self.manager)
        r = self.create_staff(permissions=["rooms.view"])
        self.assertEqual(r.status_code, 201)
        mid = r.data["id"]
        self.assertEqual(
            self.client.patch(
                reverse("staff:staff-detail", args=[mid]),
                {"job_title": "Front desk"},
                format="json",
                **HDR(self.hotel),
            ).status_code,
            200,
        )
        self.assertEqual(self.put_permissions(mid, ["rooms.view", "guests.view"]).status_code, 200)
        self.assertEqual(self.act(mid, "deactivate", {"reason": "left"}).status_code, 200)
        self.assertEqual(self.act(mid, "reactivate").status_code, 200)

    def test_staff_view_only(self):
        viewer = add_member(self.hotel, "v@x.com", perms=["staff.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(
            self.client.get(reverse("staff:staff-list"), **HDR(self.hotel)).status_code,
            200,
        )
        self.assertEqual(self.create_staff().status_code, 403)

    def test_staff_without_view_denied(self):
        worker = add_member(self.hotel, "w@x.com", perms=["rooms.view"])
        self.client.force_authenticate(worker)
        self.assertEqual(
            self.client.get(reverse("staff:staff-list"), **HDR(self.hotel)).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("staff:overview"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_staff_with_create_can_create(self):
        creator = add_member(
            self.hotel, "c@x.com", perms=["staff.view", "staff.create"]
        )
        self.client.force_authenticate(creator)
        self.assertEqual(self.create_staff().status_code, 201)

    def test_permissions_view_vs_update_split(self):
        target = membership_of(
            add_member(self.hotel, "t@x.com", perms=["rooms.view"]), self.hotel
        )
        viewer = add_member(self.hotel, "pv@x.com", perms=["staff.permissions_view"])
        self.client.force_authenticate(viewer)
        r = self.client.get(
            reverse("staff:staff-permissions", args=[target.id]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.put_permissions(target.id, ["rooms.view"]).status_code, 403)

    def test_update_allows_descriptive_fields_only(self):
        editor = add_member(self.hotel, "e@x.com", perms=["staff.update"])
        target = membership_of(
            add_member(self.hotel, "t2@x.com", perms=[]), self.hotel
        )
        self.client.force_authenticate(editor)
        r = self.client.patch(
            reverse("staff:staff-detail", args=[target.id]),
            {"job_title": "Housekeeper", "membership_type": "manager", "is_active": False},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.job_title, "Housekeeper")
        # Dangerous fields silently ignored by the shape serializer.
        self.assertEqual(target.membership_type, MembershipType.STAFF)
        self.assertTrue(target.is_active)


class SuspendedHotelTests(APITestCase, StaffMixin):
    def setUp(self):
        self.hotel = make_hotel(status=HotelStatus.SUSPENDED)
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.staff = membership_of(
            add_member(self.hotel, "s@x.com", perms=["rooms.view"]), self.hotel
        )
        self.client.force_authenticate(self.manager)

    def test_view_allowed(self):
        for name in ("staff-list", "overview", "permission-registry", "my-permissions"):
            self.assertEqual(
                self.client.get(reverse(f"staff:{name}"), **HDR(self.hotel)).status_code,
                200,
            )

    def test_writes_blocked(self):
        self.assertEqual(self.create_staff().data["code"], "hotel_suspended")
        r = self.client.patch(
            reverse("staff:staff-detail", args=[self.staff.id]),
            {"job_title": "x"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.data["code"], "hotel_suspended")
        self.assertEqual(
            self.act(self.staff.id, "deactivate").data["code"], "hotel_suspended"
        )
        self.assertEqual(
            self.put_permissions(self.staff.id, []).data["code"], "hotel_suspended"
        )
        self.assertEqual(
            self.act(self.staff.id, "reset-password", {"password": STRONG}).data["code"],
            "hotel_suspended",
        )


# --------------------------------------------------------------------------- #
# Staff lifecycle                                                               #
# --------------------------------------------------------------------------- #


class LifecycleTests(APITestCase, StaffMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_create_staff_user(self):
        r = self.create_staff(
            job_title="Receptionist",
            staff_code="RC-01",
            phone="+90 555",
            permissions=["stays.view", "reservations.view"],
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["membership_type"], "staff")
        self.assertEqual(r.data["job_title"], "Receptionist")
        self.assertEqual(r.data["permissions"], ["reservations.view", "stays.view"])
        self.assertNotIn("password", r.data)
        user = User.objects.get(email="new.staff@x.com")
        self.assertTrue(user.check_password(STRONG))

    def test_duplicate_email_rejected(self):
        self.create_staff()
        r = self.create_staff()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "email_already_registered")

    def test_weak_password_rejected(self):
        r = self.create_staff(password="12345678")
        self.assertEqual(r.status_code, 400)
        # The transaction rolled back — no half-created user remains.
        self.assertFalse(User.objects.filter(email="new.staff@x.com").exists())

    def test_link_existing_user(self):
        existing = User.objects.create_user(
            email="exist@x.com", password=STRONG, full_name="Exist"
        )
        r = self.client.post(
            reverse("staff:link-existing-user"),
            {"email": "exist@x.com", "job_title": "Cleaner", "permissions": ["housekeeping.view"]},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["email"], "exist@x.com")
        self.assertTrue(
            has_hotel_permission(existing, self.hotel, "housekeeping.view")
        )

    def test_link_duplicate_membership_rejected(self):
        add_member(self.hotel, "dup@x.com", perms=[])
        r = self.client.post(
            reverse("staff:link-existing-user"),
            {"email": "dup@x.com"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "membership_already_exists")

    def test_link_platform_owner_rejected(self):
        owner = User.objects.create_user(email="po@x.com", password=STRONG, full_name="PO")
        owner.account_type = AccountType.PLATFORM_OWNER
        owner.save(update_fields=["account_type"])
        r = self.client.post(
            reverse("staff:link-existing-user"),
            {"email": "po@x.com"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "platform_owner_not_manageable")

    def test_link_unknown_email_404(self):
        r = self.client.post(
            reverse("staff:link-existing-user"),
            {"email": "ghost@x.com"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 404)

    def test_deactivate_and_reactivate(self):
        mid = self.create_staff().data["id"]
        r = self.act(mid, "deactivate", {"reason": "resigned"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["is_active"])
        self.assertEqual(r.data["deactivation_reason"], "resigned")
        self.assertIsNotNone(r.data["deactivated_at"])
        # History (the membership row + grants) survives — no hard delete.
        self.assertTrue(HotelMembership.objects.filter(pk=mid).exists())
        r = self.act(mid, "reactivate")
        self.assertTrue(r.data["is_active"])
        self.assertIsNone(r.data["deactivated_at"])

    def test_double_deactivate_rejected(self):
        mid = self.create_staff().data["id"]
        self.act(mid, "deactivate")
        r = self.act(mid, "deactivate")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "operation_not_editable")

    def test_deactivated_staff_cannot_access_hotel(self):
        r = self.create_staff(permissions=["rooms.view"])
        self.act(r.data["id"], "deactivate")
        staff_user = User.objects.get(email="new.staff@x.com")
        self.client.force_authenticate(staff_user)
        resp = self.client.get(reverse("rooms:room-list"), **HDR(self.hotel))
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "membership_inactive")

    def test_cannot_deactivate_last_active_manager(self):
        manager_membership = membership_of(self.manager, self.hotel)
        r = self.act(manager_membership.id, "deactivate", {"reason": "x"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "last_manager_protected")
        manager_membership.refresh_from_db()
        self.assertTrue(manager_membership.is_active)

    def test_can_deactivate_manager_when_another_exists(self):
        second = add_member(self.hotel, "m2@x.com", kind=MembershipType.MANAGER)
        target = membership_of(second, self.hotel)
        r = self.act(target.id, "deactivate")
        self.assertEqual(r.status_code, 200)
        # And now the remaining one is protected again.
        remaining = membership_of(self.manager, self.hotel)
        self.assertEqual(
            self.act(remaining.id, "deactivate").data["code"], "last_manager_protected"
        )

    def test_no_hard_delete_route(self):
        mid = self.create_staff().data["id"]
        r = self.client.delete(
            reverse("staff:staff-detail", args=[mid]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 405)

    def test_reset_password_local(self):
        mid = self.create_staff().data["id"]
        r = self.act(mid, "reset-password", {"password": "Fresh!Pass987"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("password", r.data)
        user = User.objects.get(email="new.staff@x.com")
        self.assertTrue(user.check_password("Fresh!Pass987"))

    def test_list_search_and_filters(self):
        self.create_staff(job_title="Receptionist", staff_code="RC-01")
        self.act(
            self.create_staff(email="two@x.com", full_name="Two").data["id"],
            "deactivate",
        )
        base = reverse("staff:staff-list")
        self.assertEqual(
            self.client.get(base + "?search=RC-01", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?is_active=false", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?membership_type=manager", **HDR(self.hotel)).data["count"],
            1,
        )

    def test_overview_counts(self):
        self.create_staff(permissions=["rooms.view"])
        self.create_staff(email="none@x.com")
        data = self.client.get(reverse("staff:overview"), **HDR(self.hotel)).data
        self.assertEqual(data["total_staff"], 3)
        self.assertEqual(data["active_staff"], 3)
        self.assertEqual(data["managers"], 1)
        self.assertEqual(data["staff_with_permissions"], 1)
        self.assertEqual(data["staff_without_permissions"], 1)


# --------------------------------------------------------------------------- #
# Permission registry & grants                                                  #
# --------------------------------------------------------------------------- #


class PermissionTests(APITestCase, StaffMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.staff_user = add_member(self.hotel, "s@x.com", perms=["rooms.view"])
        self.staff = membership_of(self.staff_user, self.hotel)
        self.client.force_authenticate(self.manager)

    def test_registry_endpoint_grouped(self):
        r = self.client.get(reverse("staff:permission-registry"), **HDR(self.hotel))
        self.assertEqual(r.status_code, 200)
        sections = {row["section"]: row for row in r.data["sections"]}
        self.assertEqual(set(sections), set(PERMISSIONS_BY_SECTION))
        self.assertIn("staff.permissions_update", sections["staff"]["codes"])
        all_codes = {c for row in r.data["sections"] for c in row["codes"]}
        self.assertEqual(all_codes, set(ALL_PERMISSIONS))

    def test_permissions_get_payload(self):
        r = self.client.get(
            reverse("staff:staff-permissions", args=[self.staff.id]), **HDR(self.hotel)
        )
        self.assertEqual(r.data["granted"], ["rooms.view"])
        self.assertEqual(r.data["effective"], ["rooms.view"])
        self.assertFalse(r.data["is_manager"])
        self.assertTrue(r.data["editable"])
        self.assertFalse(r.data["is_self"])
        self.assertTrue(len(r.data["registry"]) > 5)

    def test_bulk_replace(self):
        r = self.put_permissions(self.staff.id, ["guests.view", "guests.create", "rooms.view"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["granted"], ["guests.create", "guests.view", "rooms.view"])
        r = self.put_permissions(self.staff.id, ["guests.view"])
        self.assertEqual(r.data["granted"], ["guests.view"])
        self.assertFalse(
            has_hotel_permission(self.staff_user, self.hotel, "rooms.view")
        )

    def test_unknown_permission_rejected(self):
        r = self.put_permissions(self.staff.id, ["rooms.view", "superpowers.all"])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "unknown_permission")
        # Nothing changed.
        self.assertEqual(
            sorted(self.staff.permission_grants.values_list("code", flat=True)),
            ["rooms.view"],
        )

    def test_duplicate_grants_avoided(self):
        self.put_permissions(self.staff.id, ["rooms.view", "rooms.view", "rooms.view"])
        self.assertEqual(
            HotelPermissionGrant.objects.filter(
                membership=self.staff, code="rooms.view"
            ).count(),
            1,
        )

    def test_manager_grants_not_editable(self):
        manager_membership = membership_of(self.manager, self.hotel)
        r = self.put_permissions(manager_membership.id, ["rooms.view"])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "manager_permissions_not_editable")

    def test_manager_effective_is_all(self):
        manager_membership = membership_of(self.manager, self.hotel)
        r = self.client.get(
            reverse("staff:staff-permissions", args=[manager_membership.id]),
            **HDR(self.hotel),
        )
        self.assertTrue(r.data["is_manager"])
        self.assertFalse(r.data["editable"])
        self.assertEqual(set(r.data["effective"]), set(ALL_PERMISSIONS))

    def test_staff_cannot_escalate_self(self):
        editor = add_member(
            self.hotel,
            "pe@x.com",
            perms=["staff.permissions_view", "staff.permissions_update", "rooms.view"],
        )
        editor_membership = membership_of(editor, self.hotel)
        self.client.force_authenticate(editor)
        # Granting themselves finance.view (which they do not hold) is blocked.
        r = self.put_permissions(
            editor_membership.id,
            ["staff.permissions_view", "staff.permissions_update", "rooms.view", "finance.view"],
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "permission_escalation_blocked")
        self.assertFalse(has_hotel_permission(editor, self.hotel, "finance.view"))

    def test_staff_cannot_grant_others_what_they_lack(self):
        editor = add_member(
            self.hotel,
            "pe2@x.com",
            perms=["staff.permissions_view", "staff.permissions_update"],
        )
        self.client.force_authenticate(editor)
        r = self.put_permissions(self.staff.id, ["rooms.view", "finance.void"])
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "permission_escalation_blocked")

    def test_staff_can_remove_permissions_freely(self):
        editor = add_member(
            self.hotel,
            "pe3@x.com",
            perms=["staff.permissions_view", "staff.permissions_update"],
        )
        self.client.force_authenticate(editor)
        # Pure removal (subset of current) needs no escalation rights.
        r = self.put_permissions(self.staff.id, [])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["granted"], [])

    def test_job_title_grants_nothing(self):
        r = self.create_staff(job_title="Accountant / Finance Manager")
        user = User.objects.get(email="new.staff@x.com")
        self.assertEqual(r.data["job_title"], "Accountant / Finance Manager")
        self.assertFalse(has_hotel_permission(user, self.hotel, "finance.view"))
        self.assertEqual(r.data["permissions"], [])


# --------------------------------------------------------------------------- #
# Sidebar / context                                                             #
# --------------------------------------------------------------------------- #


class MyPermissionsContextTests(APITestCase, StaffMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_manager_context(self):
        self.client.force_authenticate(self.manager)
        r = self.client.get(reverse("staff:my-permissions"), **HDR(self.hotel))
        self.assertTrue(r.data["is_manager"])
        self.assertEqual(set(r.data["permissions"]), set(ALL_PERMISSIONS))

    def test_staff_context_explicit_only(self):
        worker = add_member(self.hotel, "w@x.com", perms=["stays.view", "guests.view"])
        self.client.force_authenticate(worker)
        r = self.client.get(reverse("staff:my-permissions"), **HDR(self.hotel))
        self.assertFalse(r.data["is_manager"])
        self.assertEqual(r.data["permissions"], ["guests.view", "stays.view"])

    def test_api_blocks_regardless_of_hidden_links(self):
        worker = add_member(self.hotel, "w2@x.com", perms=["stays.view"])
        self.client.force_authenticate(worker)
        # Hidden sidebar links are cosmetic — the APIs themselves refuse.
        for url_name in (
            ("finance:folio-list",),
            ("services:order-list",),
            ("operations:housekeeping-list",),
            ("staff:staff-list",),
        ):
            r = self.client.get(reverse(url_name[0]), **HDR(self.hotel))
            self.assertEqual(r.status_code, 403, url_name)

    def test_operations_any_view_reflected(self):
        worker = add_member(self.hotel, "w3@x.com", perms=["maintenance.view"])
        self.client.force_authenticate(worker)
        r = self.client.get(
            reverse("operations:maintenance-list"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        r = self.client.get(
            reverse("operations:housekeeping-list"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 403)


# --------------------------------------------------------------------------- #
# Regression                                                                    #
# --------------------------------------------------------------------------- #


class RegressionTests(APITestCase, StaffMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_health_still_works(self):
        self.client.force_authenticate()  # anonymous
        self.assertEqual(self.client.get("/api/health/").status_code, 200)

    def test_existing_phase_endpoints_reachable_by_manager(self):
        for name in (
            "rooms:room-list",
            "reservations:reservation-list",
            "guests:guest-list",
            "stays:stay-list",
            "finance:folio-list",
            "services:order-list",
            "operations:housekeeping-list",
        ):
            r = self.client.get(reverse(name), **HDR(self.hotel))
            self.assertEqual(r.status_code, 200, name)

    def test_granting_phase10_codes_still_works(self):
        staff = add_member(self.hotel, "hk@x.com", perms=["housekeeping.view"])
        self.assertTrue(
            has_hotel_permission(staff, self.hotel, "housekeeping.view")
        )

    def test_no_out_of_scope_endpoints(self):
        for name in ("shifts-list", "payroll-list", "attendance-list", "daily-close"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"staff:{name}")
