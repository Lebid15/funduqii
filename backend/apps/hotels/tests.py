"""Tests for hotel settings & media (Phase 4).

Covers authorization + tenant isolation, settings CRUD + validation, the
suspended-hotel rule, media upload/replace/limit/validation rules, the
text-vs-media separation, and regressions (Phase 3 + auth + health intact, no
forbidden business routes).
"""
from __future__ import annotations

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.hotels.models import HotelMedia, HotelSettings, MediaKind
from apps.rbac.services import grant_permission
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

MEDIA_ROOT = tempfile.mkdtemp(prefix="funduqii-test-media-")

# Minimal valid image payloads (correct magic bytes).
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 24


def jpeg_file(name="logo.jpg", payload=JPEG, content_type="image/jpeg"):
    return SimpleUploadedFile(name, payload, content_type=content_type)


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=()):
    user = User.objects.create_user(
        email=email, password="StrongPass!234", full_name="Member"
    )
    membership = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True
    )
    for code in perms:
        grant_permission(membership, code)
    return user, membership


class SettingsAuthTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager, _ = add_member(self.hotel, "mgr@x.com", kind=MembershipType.MANAGER)
        self.headers = {"HTTP_X_HOTEL_ID": str(self.hotel.id)}

    def test_unauthenticated_denied(self):
        res = self.client.get(reverse("hotel:settings"), **self.headers)
        self.assertEqual(res.status_code, 401)

    def test_user_without_membership_denied(self):
        outsider = User.objects.create_user(
            email="out@x.com", password="StrongPass!234", full_name="Out"
        )
        self.client.force_authenticate(outsider)
        res = self.client.get(reverse("hotel:settings"), **self.headers)
        self.assertEqual(res.status_code, 403)

    def test_cannot_access_other_hotel(self):
        other = make_hotel(slug="other")
        self.client.force_authenticate(self.manager)
        res = self.client.get(
            reverse("hotel:settings"), HTTP_X_HOTEL_ID=str(other.id)
        )
        self.assertEqual(res.status_code, 403)

    def test_platform_owner_is_not_auto_member(self):
        owner = User.objects.create_platform_owner(
            email="owner@x.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(owner)
        res = self.client.get(reverse("hotel:settings"), **self.headers)
        self.assertEqual(res.status_code, 403)

    def test_manager_can_view_and_settings_autocreated(self):
        self.assertFalse(HotelSettings.objects.filter(hotel=self.hotel).exists())
        self.client.force_authenticate(self.manager)
        res = self.client.get(reverse("hotel:settings"), **self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(HotelSettings.objects.filter(hotel=self.hotel).exists())

    def test_manager_can_update(self):
        self.client.force_authenticate(self.manager)
        res = self.client.patch(
            reverse("hotel:settings"),
            {"display_name": "Sea View Hotel", "star_rating": 4},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["display_name"], "Sea View Hotel")

    def test_staff_with_view_can_view_but_not_update(self):
        staff, _ = add_member(self.hotel, "s1@x.com", perms=["settings.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("hotel:settings"), **self.headers).status_code, 200
        )
        res = self.client.patch(
            reverse("hotel:settings"), {"display_name": "X"}, format="json", **self.headers
        )
        self.assertEqual(res.status_code, 403)

    def test_staff_without_permission_denied(self):
        staff, _ = add_member(self.hotel, "s2@x.com")
        self.client.force_authenticate(staff)
        res = self.client.get(reverse("hotel:settings"), **self.headers)
        self.assertEqual(res.status_code, 403)

    def test_staff_with_update_can_update(self):
        staff, _ = add_member(self.hotel, "s3@x.com", perms=["settings.update"])
        self.client.force_authenticate(staff)
        res = self.client.patch(
            reverse("hotel:settings"), {"city": "Cairo"}, format="json", **self.headers
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["city"], "Cairo")

    def test_validation_errors(self):
        self.client.force_authenticate(self.manager)
        res = self.client.patch(
            reverse("hotel:settings"),
            {"latitude": "999", "star_rating": 9, "email": "not-an-email"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_suspended_hotel_can_view_but_not_update(self):
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("hotel:settings"), **self.headers).status_code, 200
        )
        res = self.client.patch(
            reverse("hotel:settings"), {"city": "X"}, format="json", **self.headers
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class MediaTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.hotel = make_hotel()
        self.manager, _ = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.headers = {"HTTP_X_HOTEL_ID": str(self.hotel.id)}

    def _upload(self, kind, file=None):
        return self.client.post(
            reverse("hotel:media-list"),
            {"kind": kind, "file": file or jpeg_file()},
            format="multipart",
            **self.headers,
        )

    def test_upload_logo_cover_gallery(self):
        for kind in ("logo", "cover", "gallery"):
            res = self._upload(kind, jpeg_file(name=f"{kind}.jpg"))
            self.assertEqual(res.status_code, 201, kind)
            self.assertEqual(res.data["kind"], kind)
            self.assertTrue(res.data["url"].endswith((".jpg", ".jpeg")))
            self.assertNotIn("file", res.data)  # no raw file / base64

    def test_response_has_no_base64(self):
        res = self._upload("logo")
        self.assertNotIn("base64", str(res.data))
        self.assertTrue(res.data["url"].startswith("http"))

    def test_only_one_active_logo(self):
        self._upload("logo", jpeg_file(name="a.jpg"))
        self._upload("logo", jpeg_file(name="b.jpg"))
        active = HotelMedia.objects.filter(
            hotel=self.hotel, kind=MediaKind.LOGO, is_active=True
        )
        self.assertEqual(active.count(), 1)
        self.assertEqual(
            HotelMedia.objects.filter(hotel=self.hotel, kind=MediaKind.LOGO).count(), 2
        )

    def test_only_one_active_cover(self):
        self._upload("cover", jpeg_file(name="a.jpg"))
        self._upload("cover", jpeg_file(name="b.jpg"))
        self.assertEqual(
            HotelMedia.objects.filter(
                hotel=self.hotel, kind=MediaKind.COVER, is_active=True
            ).count(),
            1,
        )

    @override_settings(HOTEL_MEDIA_GALLERY_MAX_COUNT=2, MEDIA_ROOT=MEDIA_ROOT)
    def test_gallery_count_limit(self):
        self.assertEqual(self._upload("gallery").status_code, 201)
        self.assertEqual(self._upload("gallery").status_code, 201)
        res = self._upload("gallery")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "media_limit_reached")

    def test_invalid_file_type_rejected(self):
        bad = SimpleUploadedFile("x.svg", b"<svg></svg>", content_type="image/svg+xml")
        res = self._upload("logo", bad)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_media_file")

    def test_bad_signature_rejected(self):
        # .jpg extension + image/jpeg type but wrong magic bytes.
        fake = SimpleUploadedFile("x.jpg", b"NOTIMAGE" * 4, content_type="image/jpeg")
        res = self._upload("logo", fake)
        self.assertEqual(res.status_code, 400)

    @override_settings(HOTEL_MEDIA_LOGO_MAX_BYTES=100, MEDIA_ROOT=MEDIA_ROOT)
    def test_oversized_file_rejected(self):
        big = jpeg_file(name="big.jpg", payload=JPEG + b"\x00" * 500)
        res = self._upload("logo", big)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_media_file")

    def test_delete_media(self):
        created = self._upload("gallery").data
        res = self.client.delete(
            reverse("hotel:media-detail", args=[created["id"]]), **self.headers
        )
        self.assertEqual(res.status_code, 204)
        self.assertFalse(HotelMedia.objects.filter(id=created["id"]).exists())

    def test_reorder_and_deactivate_gallery(self):
        a = self._upload("gallery").data
        res = self.client.patch(
            reverse("hotel:media-detail", args=[a["id"]]),
            {"sort_order": 5, "is_active": False},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["sort_order"], 5)
        self.assertFalse(res.data["is_active"])

    def test_media_isolation_between_hotels(self):
        other = make_hotel(slug="other")
        created = self._upload("gallery").data
        # Manager of `other` cannot touch this hotel's media.
        mgr2, _ = add_member(other, "mgr2@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr2)
        res = self.client.get(
            reverse("hotel:media-detail", args=[created["id"]]),
            HTTP_X_HOTEL_ID=str(other.id),
        )
        self.assertEqual(res.status_code, 404)

    def test_settings_patch_does_not_touch_media(self):
        logo = self._upload("logo").data
        before = HotelMedia.objects.get(id=logo["id"])
        self.client.patch(
            reverse("hotel:settings"),
            {"display_name": "Renamed", "phone": "+201234567"},
            format="json",
            **self.headers,
        )
        after = HotelMedia.objects.get(id=logo["id"])
        self.assertEqual(before.file.name, after.file.name)
        self.assertEqual(before.is_active, after.is_active)
        self.assertEqual(before.updated_at, after.updated_at)


class RegressionTests(APITestCase):
    def test_health_still_works(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)

    def test_platform_overview_still_owner_only(self):
        owner = User.objects.create_platform_owner(
            email="o@x.com", password="StrongPass!234", full_name="O"
        )
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(reverse("platform:overview")).status_code, 200
        )

    def test_auth_token_still_works(self):
        User.objects.create_user(
            email="u@x.com", password="StrongPass!234", full_name="U"
        )
        res = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "u@x.com", "password": "StrongPass!234"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

    def test_forbidden_business_routes_absent(self):
        for path in ("/api/v1/reservations/", "/api/v1/rooms/", "/api/v1/guests/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_no_guest_or_finance_models(self):
        # Rooms arrive in Phase 5 and reservations in Phase 6; guests/finance
        # (check-in, folio, payments, invoices) remain out of scope.
        from django.apps import apps as django_apps

        models = {m._meta.db_table for m in django_apps.get_models()}
        for forbidden in ("guests", "invoices", "folios", "payments", "expenses"):
            self.assertNotIn(forbidden, models)
