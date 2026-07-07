"""Permission registry, service, and permission-class tests (Phase 2)."""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.common.exceptions import UnknownPermission
from apps.rbac.models import HotelPermissionGrant
from apps.rbac.registry import ALL_PERMISSIONS
from apps.rbac.services import (
    get_hotel_permissions,
    grant_permission,
    has_hotel_permission,
)
from apps.tenancy.models import Hotel, HotelMembership, MembershipType


class PermissionServiceTests(TestCase):
    def setUp(self):
        self.hotel_a = Hotel.objects.create(name="Hotel A", slug="svc-a")
        self.hotel_b = Hotel.objects.create(name="Hotel B", slug="svc-b")

        self.manager = User.objects.create_user(
            email="mgr@example.com", password="x", full_name="Mgr"
        )
        self.manager_membership = HotelMembership.objects.create(
            user=self.manager, hotel=self.hotel_a, membership_type=MembershipType.MANAGER
        )

        self.staff = User.objects.create_user(
            email="stf@example.com", password="x", full_name="Stf"
        )
        self.staff_membership = HotelMembership.objects.create(
            user=self.staff, hotel=self.hotel_a, membership_type=MembershipType.STAFF
        )

    def test_manager_has_all_permissions_by_default(self):
        self.assertTrue(
            has_hotel_permission(self.manager, self.hotel_a, "reservations.create")
        )
        self.assertEqual(
            len(get_hotel_permissions(self.manager, self.hotel_a)),
            len(ALL_PERMISSIONS),
        )

    def test_staff_without_grant_is_denied(self):
        self.assertFalse(
            has_hotel_permission(self.staff, self.hotel_a, "reservations.view")
        )

    def test_staff_with_grant_is_allowed(self):
        grant_permission(self.staff_membership, "reservations.view")
        self.assertTrue(
            has_hotel_permission(self.staff, self.hotel_a, "reservations.view")
        )
        self.assertEqual(
            get_hotel_permissions(self.staff, self.hotel_a), ["reservations.view"]
        )

    def test_grant_unknown_permission_is_rejected(self):
        with self.assertRaises(UnknownPermission):
            grant_permission(self.staff_membership, "bogus.operation")

    def test_model_rejects_unknown_permission(self):
        grant = HotelPermissionGrant(membership=self.staff_membership, code="nope.nope")
        with self.assertRaises(ValidationError):
            grant.save()

    def test_check_unknown_permission_raises(self):
        with self.assertRaises(UnknownPermission):
            has_hotel_permission(self.manager, self.hotel_a, "does.not_exist")

    def test_permission_only_valid_in_correct_hotel(self):
        grant_permission(self.staff_membership, "reservations.view")
        # Staff has no membership in hotel B, so the grant does not apply there.
        self.assertFalse(
            has_hotel_permission(self.staff, self.hotel_b, "reservations.view")
        )

    def test_inactive_membership_holds_no_permissions(self):
        self.manager_membership.is_active = False
        self.manager_membership.save()
        self.assertFalse(
            has_hotel_permission(self.manager, self.hotel_a, "reservations.view")
        )


class PermissionClassTests(APITestCase):
    def setUp(self):
        self.hotel_a = Hotel.objects.create(name="Hotel A", slug="cls-a")
        self.hotel_b = Hotel.objects.create(name="Hotel B", slug="cls-b")
        self.url = reverse("foundation_require_permission")  # guarded by reports.view

        self.manager = User.objects.create_user(
            email="cmgr@example.com", password="x", full_name="CMgr"
        )
        HotelMembership.objects.create(
            user=self.manager, hotel=self.hotel_a, membership_type=MembershipType.MANAGER
        )

        self.staff = User.objects.create_user(
            email="cstf@example.com", password="x", full_name="CStf"
        )
        self.staff_membership = HotelMembership.objects.create(
            user=self.staff, hotel=self.hotel_a, membership_type=MembershipType.STAFF
        )

        self.staff_with_perm = User.objects.create_user(
            email="cstf2@example.com", password="x", full_name="CStf2"
        )
        m = HotelMembership.objects.create(
            user=self.staff_with_perm,
            hotel=self.hotel_a,
            membership_type=MembershipType.STAFF,
        )
        grant_permission(m, "reports.view")

    def test_denied_without_hotel_context(self):
        self.client.force_authenticate(self.manager)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "hotel_context_required")

    def test_manager_allowed(self):
        self.client.force_authenticate(self.manager)
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_a.id))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["required_permission"], "reports.view")

    def test_staff_without_permission_denied(self):
        self.client.force_authenticate(self.staff)
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_a.id))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "permission_denied")

    def test_staff_with_permission_allowed(self):
        self.client.force_authenticate(self.staff_with_perm)
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_a.id))
        self.assertEqual(res.status_code, 200)

    def test_permission_not_valid_in_other_hotel(self):
        # staff_with_perm only belongs to hotel A; hotel B must reject.
        self.client.force_authenticate(self.staff_with_perm)
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_b.id))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "no_hotel_membership")

    def test_requires_authentication(self):
        res = self.client.get(self.url, HTTP_X_HOTEL_ID=str(self.hotel_a.id))
        self.assertEqual(res.status_code, 401)
