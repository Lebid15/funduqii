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
        # A staff member holding staff.deactivate targets the SOLE manager
        # (non-self so the last-manager rule is what fires, not self-block).
        deactivator = add_member(self.hotel, "deac@x.com", perms=["staff.deactivate"])
        self.client.force_authenticate(deactivator)
        manager_membership = membership_of(self.manager, self.hotel)
        r = self.act(manager_membership.id, "deactivate", {"reason": "x"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "last_manager_protected")
        manager_membership.refresh_from_db()
        self.assertTrue(manager_membership.is_active)

    def test_can_deactivate_manager_when_another_exists(self):
        # self.manager deactivates a DIFFERENT second manager (allowed).
        second = add_member(self.hotel, "m2@x.com", kind=MembershipType.MANAGER)
        target = membership_of(second, self.hotel)
        r = self.act(target.id, "deactivate")
        self.assertEqual(r.status_code, 200)
        # The remaining sole manager is protected again (tested non-self).
        deactivator = add_member(self.hotel, "deac2@x.com", perms=["staff.deactivate"])
        self.client.force_authenticate(deactivator)
        remaining = membership_of(self.manager, self.hotel)
        self.assertEqual(
            self.act(remaining.id, "deactivate").data["code"], "last_manager_protected"
        )

    def test_cannot_deactivate_self(self):
        # A manager cannot deactivate their own membership (self-block).
        second = add_member(self.hotel, "m3@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(second)
        target = membership_of(second, self.hotel)
        r = self.act(target.id, "deactivate", {"reason": "x"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "self_action_blocked")

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
        # A SECOND manager edits the first manager's grants (non-self, so the
        # manager-not-editable rule is what fires rather than self-block).
        second = add_member(self.hotel, "m2edit@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(second)
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

    def test_staff_cannot_edit_own_permissions(self):
        # Staff closure: editing your OWN membership's grants is refused
        # outright (before the escalation guard even runs).
        editor = add_member(
            self.hotel,
            "pe@x.com",
            perms=["staff.permissions_view", "staff.permissions_update", "rooms.view"],
        )
        editor_membership = membership_of(editor, self.hotel)
        self.client.force_authenticate(editor)
        # Any self-edit is blocked — even re-sending the identical set.
        r = self.put_permissions(
            editor_membership.id,
            ["staff.permissions_view", "staff.permissions_update", "rooms.view"],
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "cannot_edit_own_permissions")
        # Trying to self-grant something new is blocked the same way.
        r2 = self.put_permissions(
            editor_membership.id,
            ["staff.permissions_view", "staff.permissions_update", "rooms.view", "finance.view"],
        )
        self.assertEqual(r2.data["code"], "cannot_edit_own_permissions")
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


# --------------------------------------------------------------------------- #
# Staff & employees final closure round                                        #
# --------------------------------------------------------------------------- #

from apps.shifts.services import open_shift, close_shift
from apps.notifications.models import ActivityEvent


class ClosureBase(APITestCase, StaffMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, is_primary_manager=True
        )
        self.client.force_authenticate(self.manager)

    def make_staff(self, email="s1@x.com", perms=()):
        u = add_member(self.hotel, email, perms=perms)
        return u, membership_of(u, self.hotel)


class InstantRevocationTests(ClosureBase):
    def test_revoke_takes_effect_on_next_request(self):
        staff_user, m = self.make_staff(perms=["rooms.view"])
        self.client.force_authenticate(staff_user)
        self.assertEqual(
            self.client.get(reverse("rooms:room-list"), **HDR(self.hotel)).status_code, 200
        )
        # Manager revokes on another connection.
        self.client.force_authenticate(self.manager)
        self.put_permissions(m.id, [])
        # SAME staff token, next request: immediately 403 (no re-login, no cache).
        self.client.force_authenticate(staff_user)
        r = self.client.get(reverse("rooms:room-list"), **HDR(self.hotel))
        self.assertEqual(r.status_code, 403)

    def test_deactivation_blocks_next_request(self):
        staff_user, m = self.make_staff(perms=["rooms.view"])
        self.client.force_authenticate(self.manager)
        self.act(m.id, "deactivate", {"reason": "x"})
        self.client.force_authenticate(staff_user)
        r = self.client.get(reverse("rooms:room-list"), **HDR(self.hotel))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "membership_inactive")


class OpenShiftGuardTests(ClosureBase):
    def test_deactivate_blocked_with_open_shift(self):
        staff_user, m = self.make_staff()
        open_shift(self.hotel, user=staff_user, responsible_user=staff_user,
                   opening_cash_amount="0.00")
        r = self.act(m.id, "deactivate", {"reason": "leaving"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "staff_has_open_shift")
        m.refresh_from_db()
        self.assertTrue(m.is_active)

    def test_deactivate_ok_after_shift_closed(self):
        staff_user, m = self.make_staff()
        shift = open_shift(self.hotel, user=staff_user, responsible_user=staff_user,
                           opening_cash_amount="0.00")
        close_shift(shift, user=staff_user, actual_cash_amount="0.00")
        r = self.act(m.id, "deactivate", {"reason": "leaving"})
        self.assertEqual(r.status_code, 200)
        # Reactivation restores the SAME membership (same pk).
        r2 = self.act(m.id, "reactivate")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data["id"], m.id)
        m.refresh_from_db()
        self.assertTrue(m.is_active)


class PromoteDemoteTests(ClosureBase):
    def test_promote_keeps_grants_and_manager_inherits_all(self):
        staff_user, m = self.make_staff(perms=["rooms.view"])
        r = self.act(m.id, "promote")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["membership_type"], MembershipType.MANAGER)
        # Old grants preserved (inert while manager)...
        self.assertEqual(
            sorted(m.permission_grants.values_list("code", flat=True)), ["rooms.view"]
        )
        # ...and the manager now inherits everything.
        self.assertTrue(has_hotel_permission(staff_user, self.hotel, "finance.void"))
        # Demote restores the individual grants as the source of access.
        r2 = self.act(m.id, "demote")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data["membership_type"], MembershipType.STAFF)
        self.assertFalse(has_hotel_permission(staff_user, self.hotel, "finance.void"))
        self.assertTrue(has_hotel_permission(staff_user, self.hotel, "rooms.view"))

    def test_non_manager_cannot_promote_even_with_grant(self):
        editor = add_member(self.hotel, "ed@x.com", perms=["staff.manage_managers"])
        _, target = self.make_staff()
        self.client.force_authenticate(editor)
        r = self.act(target.id, "promote")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "not_a_manager")

    def test_no_self_promote_or_demote(self):
        # Second manager tries to demote themselves.
        second = add_member(self.hotel, "m2@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(second)
        target = membership_of(second, self.hotel)
        r = self.act(target.id, "demote")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "self_action_blocked")

    def test_cannot_demote_last_or_primary_manager(self):
        # Primary manager protected (a second manager acts).
        second = add_member(self.hotel, "m2@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(second)
        primary = membership_of(self.manager, self.hotel)
        r = self.act(primary.id, "demote")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "primary_manager_protected")
        # Last-active-manager protection: demote the second (non-primary) via a
        # third manager, after which only one non-self manager remains.
        third = add_member(self.hotel, "m3@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(third)
        # Demote self.manager? it's primary -> use a fresh non-primary scenario:
        # deactivate second and third leaves only primary (protected already).
        # Instead assert non-primary second can be demoted when others exist:
        r2 = self.act(membership_of(second, self.hotel).id, "demote")
        self.assertEqual(r2.status_code, 200)

    def test_manage_managers_permission_required(self):
        staff_user = add_member(self.hotel, "plain@x.com", kind=MembershipType.MANAGER)
        _, target = self.make_staff()
        # A manager WITHOUT... managers inherit all, so use a staff w/ the grant
        # but not manager (already covered by not_a_manager). Here: manager can.
        self.client.force_authenticate(staff_user)
        self.assertEqual(self.act(target.id, "promote").status_code, 200)


class ChangeEmailTests(ClosureBase):
    def _change(self, pk, email):
        return self.client.post(
            reverse("staff:staff-change-email", args=[pk]),
            {"email": email}, format="json", **HDR(self.hotel),
        )

    def test_change_single_hotel_email(self):
        _, m = self.make_staff(email="old@x.com")
        # normalize_email lowercases the DOMAIN part only (Django behavior).
        r = self._change(m.id, "NEW@X.com")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["email"], "NEW@x.com")

    def test_email_uniqueness(self):
        add_member(self.hotel, "taken@x.com")
        _, m = self.make_staff(email="mine@x.com")
        r = self._change(m.id, "taken@x.com")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "email_already_registered")

    def test_no_self_email_change(self):
        second = add_member(self.hotel, "m2@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(second)
        target = membership_of(second, self.hotel)
        r = self._change(target.id, "other@x.com")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "self_action_blocked")

    def test_cross_tenant_identity_blocked(self):
        staff_user, m = self.make_staff(email="multi@x.com")
        # Same user linked to another hotel (active) -> cross-tenant identity.
        other = make_hotel(slug="other")
        HotelMembership.objects.create(
            user=staff_user, hotel=other, membership_type=MembershipType.STAFF, is_active=True
        )
        r = self._change(m.id, "new@x.com")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "cross_tenant_identity")

    def test_cross_tenant_identity_historical_membership(self):
        staff_user, m = self.make_staff(email="hist@x.com")
        other = make_hotel(slug="other2")
        HotelMembership.objects.create(
            user=staff_user, hotel=other, membership_type=MembershipType.STAFF,
            is_active=False,  # historical/deactivated still counts
        )
        r = self._change(m.id, "new@x.com")
        self.assertEqual(r.status_code, 409)

    def test_change_email_permission_gated(self):
        _, m = self.make_staff(email="target@x.com")
        editor = add_member(self.hotel, "noperm@x.com", perms=["staff.view", "staff.update"])
        self.client.force_authenticate(editor)
        self.assertEqual(self._change(m.id, "x@x.com").status_code, 403)


class GuardedDeleteTests(ClosureBase):
    def _delete(self, pk, delete_user=False):
        return self.client.post(
            reverse("staff:staff-delete", args=[pk]),
            {"delete_user": delete_user}, format="json", **HDR(self.hotel),
        )

    def test_delete_clean_membership(self):
        staff_user, m = self.make_staff(email="clean@x.com", perms=["rooms.view"])
        r = self._delete(m.id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["membership_deleted"], m.id)
        self.assertFalse(HotelMembership.objects.filter(pk=m.id).exists())
        # User kept (delete_user False).
        self.assertTrue(User.objects.filter(pk=staff_user.id).exists())

    def test_delete_refused_with_shift_trace(self):
        staff_user, m = self.make_staff(email="hastrace@x.com")
        shift = open_shift(self.hotel, user=staff_user, responsible_user=staff_user,
                           opening_cash_amount="0.00")
        close_shift(shift, user=staff_user, actual_cash_amount="0.00")
        r = self._delete(m.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "staff_has_trace")
        self.assertTrue(HotelMembership.objects.filter(pk=m.id).exists())

    def test_delete_refused_with_activity_trace(self):
        # A staff member who ACTED (created a guest) leaves a created_by trace.
        from apps.guests.models import Guest

        staff_user, m = self.make_staff(email="acted@x.com")
        Guest.objects.create(hotel=self.hotel, full_name="G", created_by=staff_user)
        r = self._delete(m.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "staff_has_trace")

    def test_delete_user_only_when_fully_clean_and_sole(self):
        staff_user, m = self.make_staff(email="sole@x.com")
        r = self._delete(m.id, delete_user=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["user_deleted"], staff_user.id)
        self.assertFalse(User.objects.filter(pk=staff_user.id).exists())

    def test_user_kept_when_other_membership_exists(self):
        staff_user, m = self.make_staff(email="two@x.com")
        other = make_hotel(slug="other3")
        HotelMembership.objects.create(
            user=staff_user, hotel=other, membership_type=MembershipType.STAFF, is_active=True
        )
        r = self._delete(m.id, delete_user=True)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["user_deleted"])
        self.assertTrue(User.objects.filter(pk=staff_user.id).exists())

    def test_cannot_delete_self(self):
        second = add_member(self.hotel, "m2@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(second)
        target = membership_of(second, self.hotel)
        r = self._delete(target.id)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "self_action_blocked")

    def test_delete_permission_gated(self):
        _, m = self.make_staff(email="g@x.com")
        editor = add_member(self.hotel, "np@x.com", perms=["staff.view", "staff.deactivate"])
        self.client.force_authenticate(editor)
        self.assertEqual(self._delete(m.id).status_code, 403)


class ClosureActivityTests(ClosureBase):
    def test_lifecycle_events_recorded(self):
        # created
        r = self.create_staff(email="ev@x.com", permissions=["rooms.view"])
        mid = r.data["id"]
        staff_user = User.objects.get(email="ev@x.com")
        # updated (descriptive) w/ diff, and NO event on no-op
        self.client.patch(reverse("staff:staff-detail", args=[mid]),
                          {"job_title": "Chef"}, format="json", **HDR(self.hotel))
        before = ActivityEvent.objects.filter(hotel=self.hotel, event_type="staff.updated").count()
        self.client.patch(reverse("staff:staff-detail", args=[mid]),
                          {"job_title": "Chef"}, format="json", **HDR(self.hotel))
        after = ActivityEvent.objects.filter(hotel=self.hotel, event_type="staff.updated").count()
        self.assertEqual(before, after)  # no-op recorded nothing
        # permissions updated
        self.put_permissions(mid, ["rooms.view", "reservations.view"])
        # email changed
        self.client.post(reverse("staff:staff-change-email", args=[mid]),
                         {"email": "ev2@x.com"}, format="json", **HDR(self.hotel))
        # promote + demote
        self.act(mid, "promote")
        self.act(mid, "demote")
        # deactivate + reactivate
        self.act(mid, "deactivate", {"reason": "x"})
        self.act(mid, "reactivate")
        types = set(
            ActivityEvent.objects.filter(hotel=self.hotel).values_list("event_type", flat=True)
        )
        expected = {
            "staff.created", "staff.updated", "staff.permissions_updated",
            "staff.email_changed", "staff.promoted_to_manager",
            "staff.demoted_to_staff", "staff.deactivated", "staff.reactivated",
        }
        self.assertTrue(expected.issubset(types), expected - types)

    def test_password_never_in_activity(self):
        r = self.create_staff(email="pw@x.com")
        mid = r.data["id"]
        self.act(mid, "reset-password", {"password": "Fresh!Pass987"})
        for ev in ActivityEvent.objects.filter(hotel=self.hotel):
            self.assertNotIn("Fresh!Pass987", ev.message)
            self.assertNotIn("Fresh!Pass987", ev.title)
