"""Tests for the public website + public booking (Phase 15).

Covers publishing visibility (unlisted/suspended hidden), the public-safe
hotel/room-type payloads (no internal leaks, no room numbers), availability
through the SAME engine as the console, the booking lifecycle (held+72h hold
by default, confirmed only when confirmation is disabled, future-only, no
money/stay side effects, overbooking refused), manage-token security (hashed
storage, constant-time match, indistinguishable 404s), the cancellation
REQUEST (never a direct cancel), internal reservations integration, and
regression.
"""
from __future__ import annotations

import datetime
import hashlib

from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.models import Folio, Invoice, Payment
from apps.hotels.models import HotelSettings
from apps.notifications.models import ActivityEvent
from apps.rbac.services import grant_permission
from apps.reservations.models import Reservation, ReservationStatus
from apps.rooms.models import Floor, Room, RoomType
from apps.stays.models import Stay
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

STRONG = "StrongPass!234"
HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731


def make_public_hotel(slug="grand-hotel", *, listed=True, booking=True,
                      status=HotelStatus.ACTIVE, requires_confirmation=True,
                      rooms=2, **settings_kw):
    hotel = Hotel.objects.create(name=f"Hotel {slug}", slug=f"tenant-{slug}", status=status)
    settings_obj = HotelSettings.objects.create(
        hotel=hotel,
        display_name=f"Grand {slug}",
        short_description="Sea view boutique hotel",
        city="Istanbul",
        country="TR",
        default_currency="USD",
        public_is_listed=listed,
        public_slug=slug,
        allow_public_booking=booking,
        public_booking_requires_confirmation=requires_confirmation,
        **settings_kw,
    )
    floor = Floor.objects.create(hotel=hotel, name="G", number="0")
    room_type = RoomType.objects.create(
        hotel=hotel, name="Standard", code="STD", base_capacity=2, max_capacity=3,
        base_rate="80.00", public_is_visible=True, public_name="Standard Room",
        public_description="Cozy room",
    )
    for i in range(rooms):
        Room.objects.create(
            hotel=hotel, floor=floor, room_type=room_type, number=f"10{i + 1}"
        )
    return hotel, settings_obj, room_type


def dates(days_ahead=7, nights=2):
    check_in = timezone.localdate() + datetime.timedelta(days=days_ahead)
    return check_in, check_in + datetime.timedelta(days=nights)


class PublicMixin:
    def book(self, slug, room_type, **overrides):
        check_in, check_out = dates()
        body = {
            "check_in": str(check_in),
            "check_out": str(check_out),
            "room_type": room_type.id,
            "rooms_count": 1,
            "adults": 2,
            "children": 0,
            "guest_name": "Web Guest",
            "guest_phone": "+90 555 000",
            "guest_email": "guest@example.com",
            "accept_terms": True,
        }
        body.update(overrides)
        return self.client.post(
            reverse("public_site:booking-create", args=[slug]), body, format="json"
        )


# --------------------------------------------------------------------------- #
# Publishing / hotel display                                                    #
# --------------------------------------------------------------------------- #


class PublicHotelsTests(APITestCase, PublicMixin):
    def test_unlisted_hotel_hidden(self):
        make_public_hotel("hidden", listed=False)
        r = self.client.get(reverse("public_site:hotel-list"))
        self.assertEqual(r.data["count"], 0)
        r = self.client.get(reverse("public_site:hotel-detail", args=["hidden"]))
        self.assertEqual(r.status_code, 404)

    def test_inactive_media_never_served(self):
        # Phase 17: the list prefetches ACTIVE media only and the detail path
        # keeps its filtered query — inactive images must never appear.
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.hotels.models import HotelMedia, MediaKind

        hotel, _, _ = make_public_hotel("media-h")
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
            b"\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc"
            b"\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        for name, active in (("on.png", True), ("off.png", False)):
            HotelMedia.objects.create(
                hotel=hotel,
                kind=MediaKind.GALLERY,
                file=SimpleUploadedFile(name, png, content_type="image/png"),
                alt_text=name,
                is_active=active,
            )
        detail = self.client.get(
            reverse("public_site:hotel-detail", args=["media-h"])
        ).data
        self.assertEqual([g["alt"] for g in detail["gallery"]], ["on.png"])
        listed = self.client.get(reverse("public_site:hotel-list")).data
        self.assertNotIn("off.png", str(listed))

    def test_suspended_hotel_hidden(self):
        make_public_hotel("susp", status=HotelStatus.SUSPENDED)
        self.assertEqual(
            self.client.get(reverse("public_site:hotel-list")).data["count"], 0
        )
        self.assertEqual(
            self.client.get(
                reverse("public_site:hotel-detail", args=["susp"])
            ).status_code,
            404,
        )

    def test_published_hotel_listed_and_detail(self):
        make_public_hotel("grand")
        listed = self.client.get(reverse("public_site:hotel-list")).data
        self.assertEqual(listed["count"], 1)
        card = listed["results"][0]
        self.assertEqual(card["slug"], "grand")
        self.assertEqual(card["name"], "Grand grand")
        self.assertTrue(card["booking_enabled"])
        detail = self.client.get(
            reverse("public_site:hotel-detail", args=["grand"])
        ).data
        self.assertEqual(len(detail["room_types"]), 1)
        self.assertEqual(detail["room_types"][0]["name"], "Standard Room")
        self.assertEqual(detail["room_types"][0]["base_price"], "80.00")

    def test_invalid_slug_404(self):
        self.assertEqual(
            self.client.get(
                reverse("public_site:hotel-detail", args=["nope"])
            ).status_code,
            404,
        )

    def test_no_internal_data_leaked(self):
        hotel, _, _ = make_public_hotel("clean")
        # A manager exists — must never leak.
        user = User.objects.create_user(email="m@x.com", password=STRONG, full_name="Boss")
        HotelMembership.objects.create(
            user=user, hotel=hotel, membership_type=MembershipType.MANAGER
        )
        detail = self.client.get(reverse("public_site:hotel-detail", args=["clean"]))
        blob = str(detail.data).lower()
        for forbidden in ("m@x.com", "boss", "staff", "folio", "manager",
                          "default_booking_status", "require_guest_document"):
            self.assertNotIn(forbidden, blob, forbidden)

    def test_hidden_room_type_not_shown(self):
        hotel, _, _ = make_public_hotel("rt")
        RoomType.objects.create(
            hotel=hotel, name="Secret Suite", code="SEC", base_capacity=2,
            max_capacity=2, public_is_visible=False,
        )
        detail = self.client.get(reverse("public_site:hotel-detail", args=["rt"])).data
        names = [row["name"] for row in detail["room_types"]]
        self.assertNotIn("Secret Suite", names)

    def test_search_filters(self):
        make_public_hotel("istanbul-inn")
        _, s2, _ = make_public_hotel("ankara-inn")
        s2.city = "Ankara"
        s2.save(update_fields=["city"])
        base = reverse("public_site:hotel-list")
        self.assertEqual(self.client.get(base + "?city=Ankara").data["count"], 1)
        self.assertEqual(self.client.get(base + "?q=istanbul").data["count"], 1)


# --------------------------------------------------------------------------- #
# Availability                                                                  #
# --------------------------------------------------------------------------- #


class PublicAvailabilityTests(APITestCase, PublicMixin):
    def setUp(self):
        self.hotel, self.settings_obj, self.room_type = make_public_hotel("avail")

    def get_availability(self, **params):
        check_in, check_out = dates()
        params.setdefault("check_in", str(check_in))
        params.setdefault("check_out", str(check_out))
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.get(
            reverse("public_site:availability", args=["avail"]) + f"?{query}"
        )

    def test_counts_come_from_the_engine(self):
        r = self.get_availability()
        self.assertEqual(r.status_code, 200)
        row = r.data["room_types"][0]
        self.assertEqual(row["available_quantity"], 2)
        self.assertTrue(row["can_book"])
        # Booking one room drops the public count — same engine, no bypass.
        self.book("avail", self.room_type)
        row = self.get_availability().data["room_types"][0]
        self.assertEqual(row["available_quantity"], 1)

    def test_invalid_dates_rejected(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        r = self.get_availability(check_in=str(yesterday))
        self.assertEqual(r.status_code, 400)
        check_in, _ = dates()
        r = self.get_availability(check_out=str(check_in))  # out == in
        self.assertEqual(r.status_code, 400)

    def test_min_max_nights_enforced(self):
        self.settings_obj.public_min_nights = 3
        self.settings_obj.save(update_fields=["public_min_nights"])
        r = self.get_availability()  # 2 nights
        self.assertEqual(r.status_code, 400)

    def test_no_room_numbers_exposed(self):
        blob = str(self.get_availability().data)
        self.assertNotIn("101", blob)
        self.assertNotIn("102", blob)

    def test_foreign_room_type_filtered_out(self):
        _, _, other_rt = make_public_hotel("other")
        r = self.get_availability(room_type=other_rt.id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["room_types"], [])


# --------------------------------------------------------------------------- #
# Public booking                                                                #
# --------------------------------------------------------------------------- #


class PublicBookingTests(APITestCase, PublicMixin):
    def setUp(self):
        self.hotel, self.settings_obj, self.room_type = make_public_hotel("bookme")

    def test_create_held_future_with_token(self):
        r = self.book("bookme", self.room_type, special_requests="High floor please")
        self.assertEqual(r.status_code, 201)
        self.assertIn("manage_token", r.data)
        self.assertTrue(r.data["requires_confirmation"])
        reservation = Reservation.objects.get(
            reservation_number=r.data["reference"]
        )
        self.assertEqual(reservation.source, "public_website")
        self.assertEqual(reservation.booking_kind, "future")
        self.assertEqual(reservation.status, ReservationStatus.HELD)
        self.assertIsNotNone(reservation.hold_expires_at)
        self.assertEqual(reservation.special_requests, "High floor please")
        # Token stored HASHED only.
        token = r.data["manage_token"]
        self.assertNotEqual(reservation.public_manage_token_hash, token)
        self.assertEqual(
            reservation.public_manage_token_hash,
            hashlib.sha256(token.encode()).hexdigest(),
        )

    def test_confirmed_when_confirmation_disabled(self):
        self.settings_obj.public_booking_requires_confirmation = False
        self.settings_obj.save(update_fields=["public_booking_requires_confirmation"])
        r = self.book("bookme", self.room_type)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], ReservationStatus.CONFIRMED)
        self.assertFalse(r.data["requires_confirmation"])

    def test_no_money_or_stay_side_effects(self):
        self.book("bookme", self.room_type)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(Folio.objects.count(), 0)
        self.assertEqual(Stay.objects.count(), 0)

    def test_overbooking_refused(self):
        self.assertEqual(
            self.book("bookme", self.room_type, rooms_count=2).status_code, 201
        )
        r = self.book("bookme", self.room_type)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "no_availability")

    def test_booking_disabled_rejected(self):
        self.settings_obj.allow_public_booking = False
        self.settings_obj.save(update_fields=["allow_public_booking"])
        self.assertEqual(self.book("bookme", self.room_type).status_code, 403)

    def test_suspended_hotel_rejected(self):
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save(update_fields=["status"])
        self.assertEqual(self.book("bookme", self.room_type).status_code, 404)

    def test_invalid_guest_data_rejected(self):
        self.assertEqual(
            self.book("bookme", self.room_type, guest_name="").status_code, 400
        )
        self.assertEqual(
            self.book("bookme", self.room_type, guest_phone="").status_code, 400
        )
        self.assertEqual(
            self.book("bookme", self.room_type, accept_terms=False).status_code, 400
        )

    def test_past_checkin_rejected(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        r = self.book("bookme", self.room_type, check_in=str(yesterday))
        self.assertEqual(r.status_code, 400)

    def test_uninterpretable_local_phone_is_clean_400_invalid_phone(self):
        # Decision 1 — the hotel has no default_phone_country, so a LOCAL number
        # cannot be canonicalized and is NOT guessed. The public path returns a
        # CLEAN 400 with the stable code `invalid_phone` (the frontend maps it to a
        # "enter the number with the country code" message); nothing about a prior
        # guest / VIP / ban is ever leaked, and no reservation is created.
        self.assertEqual(self.settings_obj.default_phone_country, "")
        r = self.book("bookme", self.room_type, guest_phone="0555 000 111")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["details"]["phone"][0].code, "invalid_phone")
        self.assertEqual(Reservation.objects.filter(hotel=self.hotel).count(), 0)

    def test_international_phone_accepted(self):
        # Decision 1 — an international (+country) number is always accepted; only
        # an uninterpretable one is refused.
        r = self.book("bookme", self.room_type, guest_phone="+90 555 000 1122")
        self.assertEqual(r.status_code, 201)

    def test_foreign_room_type_rejected(self):
        _, _, other_rt = make_public_hotel("elsewhere")
        r = self.book("bookme", other_rt)
        self.assertEqual(r.status_code, 404)

    def test_hidden_room_type_rejected(self):
        self.room_type.public_is_visible = False
        self.room_type.save(update_fields=["public_is_visible"])
        self.assertEqual(self.book("bookme", self.room_type).status_code, 404)

    def test_activity_recorded_via_existing_hook(self):
        self.book("bookme", self.room_type)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="reservation.created"
            ).exists()
        )

    def test_tokens_unique_and_long(self):
        # Two DISTINCT bookings with NO idempotency key (Decision 3) are independent
        # submissions, so each gets its own unique manage token.
        t1 = self.book(
            "bookme", self.room_type, guest_phone="+90 555 111"
        ).data["manage_token"]
        t2 = self.book(
            "bookme", self.room_type, guest_phone="+90 555 222"
        ).data["manage_token"]
        self.assertNotEqual(t1, t2)
        self.assertGreaterEqual(len(t1), 32)


# --------------------------------------------------------------------------- #
# Manage booking                                                                #
# --------------------------------------------------------------------------- #


class ManageBookingTests(APITestCase, PublicMixin):
    def setUp(self):
        self.hotel, self.settings_obj, self.room_type = make_public_hotel("manage")
        response = self.book("manage", self.room_type)
        self.reference = response.data["reference"]
        self.token = response.data["manage_token"]

    def manage(self, reference=None, token=None):
        return self.client.get(
            reverse("public_site:booking-manage", args=[reference or self.reference])
            + f"?token={token or self.token}"
        )

    def test_valid_token_returns_public_safe_payload(self):
        r = self.manage()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["reference"], self.reference)
        self.assertEqual(r.data["status"], "held")
        blob = str(r.data).lower()
        for forbidden in ("notes", "folio", "staff", "token_hash", "internal"):
            self.assertNotIn(forbidden, blob, forbidden)

    def test_wrong_token_404(self):
        self.assertEqual(self.manage(token="wrong-token").status_code, 404)

    def test_another_bookings_token_404(self):
        # A genuinely DIFFERENT booking (no idempotency key -> an independent
        # submission, so it is not collapsed onto setUp's booking).
        other = self.book("manage", self.room_type, guest_phone="+90 555 999")
        self.assertEqual(
            self.manage(
                reference=other.data["reference"],
                token=other.data["manage_token"],
            ).status_code,
            200,
        )
        self.assertEqual(
            self.manage(
                reference=other.data["reference"], token=self.token
            ).status_code,
            404,
        )

    def test_internal_reservation_not_manageable(self):
        internal = Reservation.objects.create(
            hotel=self.hotel, reservation_number="RESX9999",
            primary_guest_name="Internal",
            check_in_date=timezone.localdate(),
            check_out_date=timezone.localdate() + datetime.timedelta(days=1),
        )
        self.assertEqual(
            self.manage(reference=internal.reservation_number).status_code, 404
        )

    def test_cancel_request_is_a_request_only(self):
        r = self.client.post(
            reverse("public_site:booking-cancel-request", args=[self.reference]),
            {"token": self.token, "reason": "Change of plans"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.data["cancel_requested_at"])
        reservation = Reservation.objects.get(reservation_number=self.reference)
        # Still held — the request never cancels, voids or deletes anything.
        self.assertEqual(reservation.status, ReservationStatus.HELD)
        self.assertEqual(reservation.public_cancel_reason, "Change of plans")

    def test_repeated_cancel_request_idempotent(self):
        url = reverse("public_site:booking-cancel-request", args=[self.reference])
        first = self.client.post(url, {"token": self.token, "reason": "A"}, format="json")
        second = self.client.post(url, {"token": self.token, "reason": "B"}, format="json")
        self.assertEqual(second.status_code, 200)
        reservation = Reservation.objects.get(reservation_number=self.reference)
        self.assertEqual(reservation.public_cancel_reason, "A")
        self.assertEqual(
            first.data["cancel_requested_at"], second.data["cancel_requested_at"]
        )

    def test_cancel_request_wrong_token_404(self):
        r = self.client.post(
            reverse("public_site:booking-cancel-request", args=[self.reference]),
            {"token": "bad", "reason": "x"},
            format="json",
        )
        self.assertEqual(r.status_code, 404)


# --------------------------------------------------------------------------- #
# Internal integration + security + regression                                  #
# --------------------------------------------------------------------------- #


class InternalIntegrationTests(APITestCase, PublicMixin):
    def setUp(self):
        self.hotel, self.settings_obj, self.room_type = make_public_hotel("internal")
        self.manager = User.objects.create_user(
            email="mgr@x.com", password=STRONG, full_name="Mgr"
        )
        HotelMembership.objects.create(
            user=self.manager, hotel=self.hotel,
            membership_type=MembershipType.MANAGER,
        )
        response = self.book("internal", self.room_type)
        self.reference = response.data["reference"]
        self.token = response.data["manage_token"]

    def test_staff_sees_public_booking_with_source(self):
        self.client.force_authenticate(self.manager)
        listed = self.client.get(
            reverse("reservations:reservation-list") + "?source=public_website",
            **HDR(self.hotel),
        ).data
        self.assertEqual(listed["count"], 1)
        pk = listed["results"][0]["id"]
        detail = self.client.get(
            reverse("reservations:reservation-detail", args=[pk]), **HDR(self.hotel)
        ).data
        self.assertEqual(detail["source"], "public_website")
        self.assertEqual(detail["booking_channel_name"], "Funduqii Public")
        self.assertIn("public_cancel_requested_at", detail)
        # The token hash never reaches the hotel console either.
        self.assertNotIn("public_manage_token_hash", detail)

    def test_staff_confirms_via_existing_workflow(self):
        self.client.force_authenticate(self.manager)
        pk = Reservation.objects.get(reservation_number=self.reference).id
        r = self.client.post(
            reverse("reservations:reservation-confirm", args=[pk]),
            {},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "confirmed")
        # The visitor sees the new status through manage.
        manage = self.client.get(
            reverse("public_site:booking-manage", args=[self.reference])
            + f"?token={self.token}"
        )
        self.assertEqual(manage.data["status"], "confirmed")

    def test_cancel_request_visible_internally(self):
        self.client.post(
            reverse("public_site:booking-cancel-request", args=[self.reference]),
            {"token": self.token, "reason": "visitor changed plans"},
            format="json",
        )
        self.client.force_authenticate(self.manager)
        pk = Reservation.objects.get(reservation_number=self.reference).id
        detail = self.client.get(
            reverse("reservations:reservation-detail", args=[pk]), **HDR(self.hotel)
        ).data
        self.assertIsNotNone(detail["public_cancel_requested_at"])
        self.assertEqual(detail["public_cancel_reason"], "visitor changed plans")


class SecurityTests(APITestCase, PublicMixin):
    def test_throttling_configured(self):
        from apps.public_site import views

        self.assertEqual(views.PublicHotelListView.throttle_scope, "public")
        self.assertEqual(views.PublicBookingCreateView.throttle_scope, "public_booking")
        from django.conf import settings as dj_settings

        rates = dj_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertIn("public", rates)
        self.assertIn("public_booking", rates)

    def test_no_payment_or_customer_auth_endpoints(self):
        for name in ("payment", "checkout", "customer-login", "customer-register"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"public_site:{name}")

    def test_public_write_is_booking_only(self):
        # The list/detail/availability endpoints refuse POST.
        make_public_hotel("readonly")
        self.assertEqual(
            self.client.post(reverse("public_site:hotel-list"), {}).status_code, 405
        )
        self.assertEqual(
            self.client.post(
                reverse("public_site:hotel-detail", args=["readonly"]), {}
            ).status_code,
            405,
        )


class RegressionTests(APITestCase):
    def setUp(self):
        self.hotel = Hotel.objects.create(name="H", slug="h", status=HotelStatus.ACTIVE)
        self.manager = User.objects.create_user(
            email="m@x.com", password=STRONG, full_name="M"
        )
        membership = HotelMembership.objects.create(
            user=self.manager, hotel=self.hotel,
            membership_type=MembershipType.MANAGER,
        )
        grant_permission(membership, "reservations.view")
        self.client.force_authenticate(self.manager)

    def test_health_still_works(self):
        self.client.force_authenticate()
        self.assertEqual(self.client.get("/api/health/").status_code, 200)

    def test_console_endpoints_reachable(self):
        for name in (
            "rooms:room-list", "reservations:reservation-list",
            "finance:folio-list", "shifts:shift-list", "reports:overview",
            "notifications:notification-list", "staff:staff-list",
        ):
            self.assertEqual(
                self.client.get(reverse(name), **HDR(self.hotel)).status_code,
                200,
                name,
            )

    def test_public_apis_do_not_require_hotel_header(self):
        self.client.force_authenticate()
        self.assertEqual(
            self.client.get(reverse("public_site:hotel-list")).status_code, 200
        )


# --------------------------------------------------------------------------- #
# Guests central identity (W3) — public submission (Decision 10)                #
# --------------------------------------------------------------------------- #


class PublicCentralIdentityTests(APITestCase, PublicMixin):
    """A public booking passes ``allow_create=False`` down to create_reservation:
    NO central guest is created (pure snapshot, linked later), the identity is
    ban-checked WITHOUT leaking the reason, and a deterministic idempotency key
    collapses duplicate submissions onto the ORIGINAL booking."""

    def setUp(self):
        self.hotel, self.settings_obj, self.room_type = make_public_hotel("pci")

    def _guest_count(self):
        from apps.guests.models import Guest

        return Guest.objects.filter(hotel=self.hotel).count()

    def test_public_booking_creates_no_central_guest_and_stays_pending(self):
        before = self._guest_count()
        r = self.book("pci", self.room_type)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self._guest_count(), before)  # no guest created
        reservation = Reservation.objects.get(
            reservation_number=r.data["reference"]
        )
        self.assertIsNone(reservation.primary_guest_id)  # snapshot only
        self.assertEqual(reservation.status, ReservationStatus.HELD)  # stays pending

    def test_duplicate_submission_is_idempotent(self):
        # Decision 3 — idempotency is now driven by an EXPLICIT client key. A retry
        # reusing the SAME key with the SAME payload replays the ORIGINAL booking.
        key = "11111111-1111-4111-8111-111111111111"
        first = self.book("pci", self.room_type, idempotency_key=key)
        second = self.book("pci", self.room_type, idempotency_key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["reference"], second.data["reference"])
        # Exactly ONE reservation exists — the retry did not create a second.
        self.assertEqual(Reservation.objects.filter(hotel=self.hotel).count(), 1)

    def test_public_banned_booking_is_generic_and_indistinguishable(self):
        # SEC (public-booking ban is INDISTINGUISHABLE): a public booking refused
        # because the identity matches a BLOCKED guest must NOT reveal that a ban,
        # the guest, or a reason exists. The internal ``guest_blocked`` (409) is
        # translated at the public boundary into the generic
        # ``booking_cannot_be_completed`` (409) — the SAME status as the public
        # site's other generic booking failure (``no_availability``), so neither
        # status nor code discloses the ban.
        from apps.guests.models import Guest
        from apps.guests.services import block_guest

        blocked = Guest.objects.create(
            hotel=self.hotel, full_name="Banned", phone="+905550000000"
        )
        block_guest(blocked, reason="fraud", user=None)
        r = self.book("pci", self.room_type, guest_phone="+905550000000")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "booking_cannot_be_completed")
        self.assertNotEqual(r.data["code"], "guest_blocked")
        # Nothing about a ban / the guest / the reason leaks anywhere in the body.
        blob = str(r.data).lower()
        for forbidden in ("fraud", "guest_blocked", "blocked", "banned"):
            self.assertNotIn(forbidden, blob, forbidden)
        # The refused booking created nothing (the enclosing atomic rolled back).
        self.assertEqual(Reservation.objects.filter(hotel=self.hotel).count(), 0)
        self.assertEqual(Guest.objects.filter(hotel=self.hotel, is_blocked=False).count(), 0)

    def test_generic_public_failure_shares_status_with_no_availability(self):
        # Indistinguishability check: a banned booking and an ordinary
        # no-availability booking BOTH return HTTP 409, so the ban cannot be told
        # apart from a generic failure by status. The codes differ, but neither
        # code names a ban.
        from apps.guests.models import Guest
        from apps.guests.services import block_guest

        blocked = Guest.objects.create(
            hotel=self.hotel, full_name="Banned2", phone="+905550000001"
        )
        block_guest(blocked, reason="fraud", user=None)
        banned = self.book("pci", self.room_type, guest_phone="+905550000001")
        # Exhaust inventory (2 rooms) with a clean guest, then overbook -> 409.
        self.book("pci", self.room_type, rooms_count=2, guest_phone="+905550000009")
        no_avail = self.book("pci", self.room_type, guest_phone="+905550000008")
        self.assertEqual(banned.status_code, 409)
        self.assertEqual(no_avail.status_code, 409)
        self.assertEqual(banned.status_code, no_avail.status_code)
        self.assertEqual(banned.data["code"], "booking_cannot_be_completed")
        self.assertEqual(no_avail.data["code"], "no_availability")

    def test_internal_reservation_path_still_raises_guest_blocked(self):
        # The internal hotel-panel path (authenticated create/check-in) for the
        # SAME banned identity keeps raising the specific ``guest_blocked`` (409) so
        # authorized staff can see the block (and its reason on the guest profile).
        # Only the PUBLIC boundary is genericized.
        import datetime

        from apps.common.exceptions import GuestBlocked
        from apps.guests.models import Guest
        from apps.guests.services import block_guest
        from apps.reservations.models import BookingKind, ReservationStatus
        from apps.reservations.services import create_reservation

        blocked = Guest.objects.create(
            hotel=self.hotel, full_name="Banned", phone="+905550000000"
        )
        block_guest(blocked, reason="fraud", user=None)
        check_in = timezone.localdate() + datetime.timedelta(days=7)
        with self.assertRaises(GuestBlocked) as ctx:
            create_reservation(
                self.hotel,
                lines=[{"room_type": self.room_type, "quantity": 1}],
                status=ReservationStatus.CONFIRMED,
                user=None,
                allow_create=True,
                primary_guest_name="Banned",
                primary_guest_phone="+905550000000",
                adults=1,
                children=0,
                check_in_date=check_in,
                check_out_date=check_in + datetime.timedelta(days=2),
                booking_kind=BookingKind.FUTURE,
            )
        self.assertEqual(ctx.exception.default_code, "guest_blocked")


# --------------------------------------------------------------------------- #
# Explicit public idempotency key (Decision 3)                                  #
# --------------------------------------------------------------------------- #


class PublicExplicitIdempotencyTests(APITestCase, PublicMixin):
    """Decision 3 — the public idempotency key is an EXPLICIT client value carried
    in the request BODY (not the payload content hash). Same key + same payload
    replays the ORIGINAL booking; same key + a materially different payload is a 409
    conflict; a new key is always a new booking; keys are isolated per hotel; an
    omitted key means no idempotency (each submission is independent)."""

    def setUp(self):
        self.hotel, self.settings_obj, self.room_type = make_public_hotel("idem")

    def _count(self, hotel=None):
        return Reservation.objects.filter(hotel=hotel or self.hotel).count()

    def test_same_key_same_payload_replays_prior_booking(self):
        key = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        first = self.book("idem", self.room_type, idempotency_key=key)
        second = self.book("idem", self.room_type, idempotency_key=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["reference"], second.data["reference"])
        self.assertEqual(self._count(), 1)

    def test_same_key_different_payload_is_409_conflict(self):
        key = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        first = self.book("idem", self.room_type, idempotency_key=key, adults=2)
        self.assertEqual(first.status_code, 201)
        # Same key, materially different payload (adults 2 -> 1) -> 409, and NO
        # second booking is created (the original is never silently returned as the
        # result of a different request).
        second = self.book("idem", self.room_type, idempotency_key=key, adults=1)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data["code"], "idempotency_key_conflict")
        self.assertEqual(self._count(), 1)

    def test_two_different_keys_same_payload_are_two_bookings(self):
        # Identical payload, two DIFFERENT keys -> two intentional bookings
        # (rooms=2 so both fit inventory).
        first = self.book("idem", self.room_type, idempotency_key="key-one")
        second = self.book("idem", self.room_type, idempotency_key="key-two")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["reference"], second.data["reference"])
        self.assertEqual(self._count(), 2)

    def test_key_is_isolated_between_hotels(self):
        hotel_b, _, room_type_b = make_public_hotel("idem-b")
        key = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        a = self.book("idem", self.room_type, idempotency_key=key)
        b = self.book("idem-b", room_type_b, idempotency_key=key)
        self.assertEqual(a.status_code, 201)
        self.assertEqual(b.status_code, 201)
        # The SAME key value in hotel A and hotel B are INDEPENDENT bookings: each
        # hotel got exactly one reservation carrying that key (B did NOT replay A's).
        # (reservation_number is a per-hotel sequence, so both may read "R00001" —
        # isolation is proven by two distinct rows scoped to their own hotel.)
        self.assertEqual(self._count(), 1)
        self.assertEqual(self._count(hotel_b), 1)
        res_a = Reservation.objects.get(
            hotel=self.hotel, creation_idempotency_key=key
        )
        res_b = Reservation.objects.get(
            hotel=hotel_b, creation_idempotency_key=key
        )
        self.assertNotEqual(res_a.pk, res_b.pk)

    def test_omitted_key_makes_each_submission_new(self):
        # Contract fallback: no key -> no idempotency, so two identical resubmits
        # are independent bookings (the frontend always sends a key in practice).
        first = self.book("idem", self.room_type)
        second = self.book("idem", self.room_type)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data["reference"], second.data["reference"])
        self.assertEqual(self._count(), 2)
