"""Tests for the guest extra-services flow (GUEST-FOLIO-EXTRA-SERVICES-CLOSURE).

Covers: P1 catalog validations + normalized-name uniqueness + deactivate-not-delete
+ no DELETE endpoint + hotel isolation; P3 the add-service flow (happy path, every
refusal, idempotency replay/409, no direct payment); P6 the folio directory (no
N+1, floor joined, source-allowlist + voided exclusion, money gated on finance.view);
and the access matrix (#7). The PostgreSQL-only check-out race lives in
``tests_concurrency.py``.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.constants import ChargeSource
from apps.finance.models import (
    ChargeType,
    Folio,
    FolioCharge,
    FolioStatus,
    Payment,
    PostingStatus,
)
from apps.finance.services import add_charge, ensure_stay_folio, void_charge
from apps.guest_services.models import (
    GuestExtraService,
    GuestServicePosting,
    PricingMode,
    normalize_service_name,
)
from apps.guests.models import Guest
from apps.rbac.services import grant_permission
from apps.rooms.models import Floor, Room, RoomType
from apps.stays.models import Stay, StayStatus
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731


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


def make_service(hotel, *, name="Laundry", price="50.00", currency="USD",
                 tax="10.00", pricing_mode=PricingMode.FIXED, is_active=True,
                 category="laundry", display_order=0):
    return GuestExtraService.objects.create(
        hotel=hotel,
        name=name,
        category=category,
        unit_price=Decimal(price),
        currency=currency,
        tax_rate=Decimal(tax),
        pricing_mode=pricing_mode,
        is_active=is_active,
        display_order=display_order,
    )


def make_stay(hotel, *, room_number="101", floor=None, room_type=None,
              with_folio=True, days=2):
    floor = floor or Floor.objects.create(
        hotel=hotel, name="Ground", number="0"
    )
    room_type = room_type or RoomType.objects.create(
        hotel=hotel, name="Standard", code=f"S{room_number}",
        base_capacity=2, max_capacity=3,
    )
    room = Room.objects.create(
        hotel=hotel, floor=floor, room_type=room_type, number=room_number
    )
    guest = Guest.objects.create(hotel=hotel, full_name=f"Guest {room_number}")
    stay = Stay.objects.create(
        hotel=hotel,
        room=room,
        primary_guest=guest,
        status=StayStatus.IN_HOUSE,
        planned_check_in_date=timezone.localdate(),
        planned_check_out_date=timezone.localdate() + timezone.timedelta(days=days),
        actual_check_in_at=timezone.now(),
    )
    if with_folio:
        ensure_stay_folio(stay)
    return stay


# --- P1: catalog ------------------------------------------------------------


class GuestServiceCatalogTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()

    def test_unit_price_must_be_non_negative(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GuestExtraService.objects.create(
                    hotel=self.hotel, name="Bad", unit_price=Decimal("-1.00"),
                    currency="USD",
                )

    def test_tax_rate_must_be_within_0_100(self):
        for bad in (Decimal("-0.01"), Decimal("100.01")):
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    GuestExtraService.objects.create(
                        hotel=self.hotel, name=f"T{bad}", unit_price=Decimal("1.00"),
                        currency="USD", tax_rate=bad,
                    )

    def test_display_order_non_negative_via_clean(self):
        svc = GuestExtraService(
            hotel=self.hotel, name="X", unit_price=Decimal("1.00"), currency="USD",
        )
        svc.display_order = -1
        # PositiveIntegerField + the DB check both reject; clean() gives a typed msg.
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            svc.full_clean()

    def test_name_required_after_trim(self):
        from django.core.exceptions import ValidationError

        svc = GuestExtraService(
            hotel=self.hotel, name="   ", unit_price=Decimal("1.00"), currency="USD",
        )
        with self.assertRaises(ValidationError):
            svc.full_clean()
        # DB backstop: a whitespace-only name normalizes to "" -> constraint.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GuestExtraService.objects.create(
                    hotel=self.hotel, name="   ", unit_price=Decimal("1.00"),
                    currency="USD",
                )

    def test_currency_shape_validated(self):
        from django.core.exceptions import ValidationError

        svc = GuestExtraService(
            hotel=self.hotel, name="X", unit_price=Decimal("1.00"), currency="US",
        )
        with self.assertRaises(ValidationError):
            svc.full_clean()

    def test_name_unique_after_normalization(self):
        make_service(self.hotel, name="Extra Bed", category="extra_bed")
        self.assertEqual(normalize_service_name("  EXTRA   bed "), "extra bed")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_service(self.hotel, name="  extra   BED ", category="extra_bed")

    def test_same_name_allowed_across_hotels(self):
        other = make_hotel(slug="other")
        make_service(self.hotel, name="Parking", category="parking")
        # Different hotel -> no conflict (per-hotel uniqueness).
        make_service(other, name="Parking", category="parking")
        self.assertEqual(
            GuestExtraService.objects.filter(name="Parking").count(), 2
        )

    def test_deactivate_not_delete(self):
        svc = make_service(self.hotel)
        svc.is_active = False
        svc.save(update_fields=["is_active", "updated_at"])
        svc.refresh_from_db()
        self.assertFalse(svc.is_active)
        # Row still exists (deactivated, not deleted).
        self.assertTrue(GuestExtraService.objects.filter(pk=svc.pk).exists())

    def test_admin_forbids_delete(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from apps.guest_services.admin import (
            GuestExtraServiceAdmin,
            GuestServicePostingAdmin,
        )

        site = AdminSite()
        cat_admin = GuestExtraServiceAdmin(GuestExtraService, site)
        post_admin = GuestServicePostingAdmin(GuestServicePosting, site)
        request = RequestFactory().get("/admin/")
        request.user = add_member(self.hotel, "admin@x.com", kind=MembershipType.MANAGER)
        self.assertFalse(cat_admin.has_delete_permission(request))
        self.assertFalse(post_admin.has_delete_permission(request))
        # No bulk delete action on either (filtered out because delete is denied).
        self.assertNotIn("delete_selected", cat_admin.get_actions(request))
        self.assertNotIn("delete_selected", post_admin.get_actions(request))
        # Postings are fully read-only in the admin.
        self.assertFalse(post_admin.has_add_permission(request))
        self.assertFalse(post_admin.has_change_permission(request))

    def test_no_delete_endpoint(self):
        """The app exposes NO delete route: DELETE on either endpoint is 405."""
        user = add_member(
            self.hotel, "u@x.com", perms=("service_orders.create", "finance.view")
        )
        self.client.force_authenticate(user)
        stay = make_stay(self.hotel)
        r1 = self.client.delete(
            reverse("guest_services:folio-directory"), **HDR(self.hotel)
        )
        r2 = self.client.delete(
            reverse("guest_services:stay-add-service", args=[stay.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r1.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(r2.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# --- P3: add-service flow ---------------------------------------------------


class AddServiceMixin:
    def _add(self, hotel, stay, **body):
        return self.client.post(
            reverse("guest_services:stay-add-service", args=[stay.id]),
            body,
            format="json",
            **HDR(hotel),
        )


class GuestServiceAddFlowTests(AddServiceMixin, APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(
            self.hotel,
            "adder@x.com",
            perms=("service_orders.create", "finance.charge_create", "finance.view"),
        )
        self.client.force_authenticate(self.user)
        self.stay = make_stay(self.hotel)
        self.service = make_service(self.hotel, price="50.00", tax="10.00")

    def _folio(self):
        return Folio.objects.get(hotel=self.hotel, stay=self.stay, status=FolioStatus.OPEN)

    def test_happy_path_fixed_creates_one_charge_with_snapshots(self):
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="2")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        self.assertEqual(GuestServicePosting.objects.count(), 1)
        charges = FolioCharge.objects.filter(
            folio=self._folio(), source=ChargeSource.GUEST_EXTRA_SERVICE
        )
        self.assertEqual(charges.count(), 1)
        charge = charges.get()
        self.assertEqual(charge.type, ChargeType.SERVICE)
        self.assertEqual(charge.source, ChargeSource.GUEST_EXTRA_SERVICE)
        self.assertEqual(charge.quantity, Decimal("2.00"))
        self.assertEqual(charge.unit_amount, Decimal("50.00"))
        self.assertEqual(charge.amount, Decimal("100.00"))
        self.assertEqual(charge.tax_amount, Decimal("10.00"))
        self.assertEqual(charge.total_amount, Decimal("110.00"))
        # Frozen snapshots.
        self.assertEqual(charge.currency_snapshot, "USD")
        self.assertEqual(charge.service_name_snapshot, "Laundry")
        self.assertEqual(charge.unit_price_snapshot, Decimal("50.00"))
        self.assertEqual(charge.tax_rate_snapshot, Decimal("10.00"))
        # No direct payment ever created on this flow.
        self.assertEqual(Payment.objects.count(), 0)

    def test_refuse_not_in_house(self):
        self.stay.status = StayStatus.CHECKED_OUT
        self.stay.save(update_fields=["status", "updated_at"])
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r.data["code"], "stay_not_in_house")
        self.assertEqual(GuestServicePosting.objects.count(), 0)

    def test_refuse_inactive_service(self):
        self.service.is_active = False
        self.service.save(update_fields=["is_active", "updated_at"])
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r.data["code"], "guest_service_inactive")
        self.assertEqual(FolioCharge.objects.count(), 0)

    def test_refuse_quantity_non_positive(self):
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="0")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(GuestServicePosting.objects.count(), 0)

    def test_currency_mismatch_rejected(self):
        eur = make_service(self.hotel, name="EUR svc", currency="EUR", category="other")
        r = self._add(self.hotel, self.stay, service=eur.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r.data["code"], "folio_currency_mismatch")
        self.assertEqual(FolioCharge.objects.count(), 0)

    def test_client_price_on_fixed_is_ignored(self):
        r = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="1",
            unit_price_override="999.00", reason="try to override",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        charge = FolioCharge.objects.get(source=ChargeSource.GUEST_EXTRA_SERVICE)
        # Catalog price wins; the client override is ignored on a FIXED service.
        self.assertEqual(charge.unit_amount, Decimal("50.00"))

    def test_variable_override_without_finance_charge_create_refused(self):
        var = make_service(
            self.hotel, name="Damage", pricing_mode=PricingMode.VARIABLE,
            price="0.00", category="damages",
        )
        limited = add_member(
            self.hotel, "limited@x.com", perms=("service_orders.create",)
        )
        self.client.force_authenticate(limited)
        r = self._add(
            self.hotel, self.stay, service=var.id, quantity="1",
            unit_price_override="120.00", reason="broken lamp",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FolioCharge.objects.count(), 0)

    def test_variable_override_requires_reason(self):
        var = make_service(
            self.hotel, name="Damage", pricing_mode=PricingMode.VARIABLE,
            price="0.00", category="damages",
        )
        r = self._add(
            self.hotel, self.stay, service=var.id, quantity="1",
            unit_price_override="120.00",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(r.data["code"], "variable_price_reason_required")
        self.assertEqual(FolioCharge.objects.count(), 0)

    def test_variable_override_applied_with_permission_and_reason(self):
        var = make_service(
            self.hotel, name="Damage", pricing_mode=PricingMode.VARIABLE,
            price="0.00", tax="0.00", category="damages",
        )
        r = self._add(
            self.hotel, self.stay, service=var.id, quantity="1",
            unit_price_override="120.00", reason="broken lamp",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        charge = FolioCharge.objects.get(source=ChargeSource.GUEST_EXTRA_SERVICE)
        self.assertEqual(charge.unit_amount, Decimal("120.00"))
        self.assertEqual(charge.unit_price_snapshot, Decimal("120.00"))

    def test_variable_without_override_uses_catalog_price(self):
        var = make_service(
            self.hotel, name="Late checkout", pricing_mode=PricingMode.VARIABLE,
            price="30.00", tax="0.00", category="other",
        )
        limited = add_member(
            self.hotel, "op@x.com", perms=("service_orders.create",)
        )
        self.client.force_authenticate(limited)
        r = self._add(self.hotel, self.stay, service=var.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        charge = FolioCharge.objects.get(source=ChargeSource.GUEST_EXTRA_SERVICE)
        self.assertEqual(charge.unit_amount, Decimal("30.00"))

    def test_cross_hotel_service_is_404(self):
        other = make_hotel(slug="other")
        other_service = make_service(other, name="Foreign", category="other")
        r = self._add(self.hotel, self.stay, service=other_service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_hotel_stay_is_404(self):
        other = make_hotel(slug="other")
        other_stay = make_stay(other, room_number="900")
        r = self._add(self.hotel, other_stay, service=self.service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_idempotency_replay_returns_original_no_new_charge(self):
        r1 = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="1",
            idempotency_key="abc-123",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        r2 = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="1",
            idempotency_key="abc-123",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.data)
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(GuestServicePosting.objects.count(), 1)
        self.assertEqual(
            FolioCharge.objects.filter(
                source=ChargeSource.GUEST_EXTRA_SERVICE
            ).count(),
            1,
        )

    def test_different_body_same_key_conflicts_no_side_effect(self):
        r1 = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="1",
            idempotency_key="dup-key",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        r2 = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="3",
            idempotency_key="dup-key",
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r2.data["code"], "idempotency_key_conflict")
        # No second charge / posting created.
        self.assertEqual(GuestServicePosting.objects.count(), 1)
        self.assertEqual(
            FolioCharge.objects.filter(
                source=ChargeSource.GUEST_EXTRA_SERVICE
            ).count(),
            1,
        )

    def test_after_checkout_closed_folio_refused(self):
        from apps.stays.services import CheckOutService

        CheckOutService.execute(
            self.stay, checkout_reason="test departure", user=self.user
        )
        self.stay.refresh_from_db()
        self.assertEqual(self.stay.status, StayStatus.CHECKED_OUT)
        # Folio is now CLOSED and the stay is not in-house: no new charge.
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r.data["code"], "stay_not_in_house")
        self.assertEqual(
            FolioCharge.objects.filter(
                source=ChargeSource.GUEST_EXTRA_SERVICE
            ).count(),
            0,
        )


# --- P6: folio directory ----------------------------------------------------


class GuestFolioDirectoryTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.floor = Floor.objects.create(hotel=self.hotel, name="Ground", number="0")
        self.rtype = RoomType.objects.create(
            hotel=self.hotel, name="Standard", code="STD",
            base_capacity=2, max_capacity=3,
        )
        self.finance_user = add_member(
            self.hotel, "fin@x.com", perms=("finance.view", "service_orders.create")
        )

    def _resident(self, n):
        return make_stay(
            self.hotel, room_number=f"20{n}", floor=self.floor, room_type=self.rtype
        )

    def _get(self, user):
        self.client.force_authenticate(user)
        return self.client.get(
            reverse("guest_services:folio-directory"), **HDR(self.hotel)
        )

    def test_no_n_plus_one_constant_queries(self):
        self._resident(1)
        self.client.force_authenticate(self.finance_user)
        url = reverse("guest_services:folio-directory")
        with CaptureQueriesContext(connection) as ctx1:
            r1 = self.client.get(url, **HDR(self.hotel))
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        base = len(ctx1.captured_queries)
        # Add more residents in the SAME hotel/floor/type.
        self._resident(2)
        self._resident(3)
        self._resident(4)
        with CaptureQueriesContext(connection) as ctx2:
            r2 = self.client.get(url, **HDR(self.hotel))
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(ctx2.captured_queries), base, "directory has an N+1")
        self.assertEqual(r2.data["count"], 4)

    def test_floor_joined_and_operational_fields(self):
        stay = self._resident(1)
        r = self._get(self.finance_user)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        row = r.data["results"][0]
        self.assertEqual(row["stay_id"], stay.id)
        self.assertEqual(row["floor_name"], "Ground")
        self.assertEqual(row["room_number"], "201")
        self.assertEqual(row["room_type_name"], "Standard")
        self.assertEqual(row["folio_status"], "open")

    def test_service_count_total_source_allowlist_excludes_voided(self):
        stay = self._resident(1)
        folio = Folio.objects.get(stay=stay, status=FolioStatus.OPEN)
        # A guest_extra_service charge (counts), a service_order charge (counts),
        # a voided guest_extra_service charge (excluded), a manual charge (excluded
        # by the SOURCE allowlist even though its type is SERVICE).
        add_charge(
            folio, charge_type=ChargeType.SERVICE, description="svc1", quantity=1,
            unit_amount="20.00", source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        add_charge(
            folio, charge_type=ChargeType.SERVICE, description="order", quantity=1,
            unit_amount="30.00", source=ChargeSource.SERVICE_ORDER,
        )
        voided = add_charge(
            folio, charge_type=ChargeType.SERVICE, description="void me", quantity=1,
            unit_amount="99.00", source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        void_charge(voided, reason="mistake")
        add_charge(
            folio, charge_type=ChargeType.SERVICE, description="manual", quantity=1,
            unit_amount="15.00", source=ChargeSource.MANUAL,
        )
        r = self._get(self.finance_user)
        row = r.data["results"][0]
        # 2 counted lines (guest_extra_service + service_order); voided + manual out.
        self.assertEqual(row["service_count"], 2)
        self.assertEqual(Decimal(row["service_total"]), Decimal("50.00"))

    def test_money_hidden_without_finance_view(self):
        stay = self._resident(1)
        folio = Folio.objects.get(stay=stay, status=FolioStatus.OPEN)
        add_charge(
            folio, charge_type=ChargeType.SERVICE, description="svc", quantity=1,
            unit_amount="20.00", source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        op_user = add_member(
            self.hotel, "op@x.com", perms=("service_orders.create",)
        )
        r = self._get(op_user)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        row = r.data["results"][0]
        # Operational count shown; money keys OMITTED entirely (not zeroed/nulled).
        self.assertEqual(row["service_count"], 1)
        for money_key in ("service_total", "balance", "total_payments", "currency"):
            self.assertNotIn(money_key, row)

    def test_money_shown_with_finance_view(self):
        stay = self._resident(1)
        folio = Folio.objects.get(stay=stay, status=FolioStatus.OPEN)
        add_charge(
            folio, charge_type=ChargeType.SERVICE, description="svc", quantity=1,
            unit_amount="20.00", tax_rate="0.00",
            source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        r = self._get(self.finance_user)
        row = r.data["results"][0]
        self.assertEqual(Decimal(row["service_total"]), Decimal("20.00"))
        self.assertEqual(Decimal(row["balance"]), Decimal("20.00"))
        self.assertEqual(Decimal(row["total_payments"]), Decimal("0.00"))
        self.assertEqual(row["currency"], "USD")


# --- Access matrix (#7) -----------------------------------------------------


class AccessMatrixTests(AddServiceMixin, APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.stay = make_stay(self.hotel)
        self.service = make_service(self.hotel)
        self.var_service = make_service(
            self.hotel, name="Damage", pricing_mode=PricingMode.VARIABLE,
            price="0.00", category="damages",
        )

    def test_service_orders_create_only_can_add_fixed(self):
        user = add_member(self.hotel, "so@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

    def test_service_orders_create_only_cannot_variable_override(self):
        user = add_member(self.hotel, "so@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        r = self._add(
            self.hotel, self.stay, service=self.var_service.id, quantity="1",
            unit_price_override="80.00", reason="damage",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_finance_view_only_cannot_add(self):
        user = add_member(self.hotel, "fv@x.com", perms=("finance.view",))
        self.client.force_authenticate(user)
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_directory_any_of_three_grants_access(self):
        for code in ("service_orders.create", "services.view", "finance.view"):
            user = add_member(self.hotel, f"{code}@x.com", perms=(code,))
            self.client.force_authenticate(user)
            r = self.client.get(
                reverse("guest_services:folio-directory"), **HDR(self.hotel)
            )
            self.assertEqual(r.status_code, status.HTTP_200_OK, code)

    def test_directory_denied_without_any_of_three(self):
        user = add_member(self.hotel, "none@x.com", perms=("stays.view",))
        self.client.force_authenticate(user)
        r = self.client.get(
            reverse("guest_services:folio-directory"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        # And add is denied too (no service_orders.create).
        r2 = self._add(self.hotel, self.stay, service=self.service.id, quantity="1")
        self.assertEqual(r2.status_code, status.HTTP_403_FORBIDDEN)


# --- P9: catalog ("Services & Prices") API ----------------------------------


class CatalogAPITests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.list_url = reverse("guest_services:catalog-list")

    def _auth(self, *perms, email=None):
        user = add_member(
            self.hotel, email or f"{'_'.join(perms) or 'none'}@x.com", perms=perms
        )
        self.client.force_authenticate(user)
        return user

    def _detail(self, pk):
        return reverse("guest_services:catalog-detail", args=[pk])

    def test_list_requires_services_view_and_filters_and_orders(self):
        make_service(self.hotel, name="B svc", display_order=2)
        make_service(self.hotel, name="A svc", display_order=1, category="parking")
        inactive = make_service(
            self.hotel, name="Old svc", display_order=3, is_active=False,
            category="other",
        )
        self._auth("services.view")
        r = self.client.get(self.list_url, **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        names = [row["name"] for row in r.data["results"]]
        # Ordered by display_order.
        self.assertEqual(names, ["A svc", "B svc", "Old svc"])
        # Active filter.
        r_active = self.client.get(
            self.list_url + "?is_active=true", **HDR(self.hotel)
        )
        active_names = [row["name"] for row in r_active.data["results"]]
        self.assertNotIn("Old svc", active_names)
        r_inactive = self.client.get(
            self.list_url + "?is_active=false", **HDR(self.hotel)
        )
        self.assertEqual(
            [row["name"] for row in r_inactive.data["results"]], ["Old svc"]
        )
        self.assertEqual(inactive.is_active, False)

    def test_list_denied_without_services_view(self):
        self._auth("stays.view")
        r = self.client.get(self.list_url, **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_with_services_create(self):
        self._auth("services.create")
        body = {
            "name": "Airport transfer",
            "category": "transport",
            "unit_price": "80.00",
            "currency": "usd",  # normalized to uppercase
            "tax_rate": "5.00",
            "pricing_mode": "fixed",
            "display_order": 4,
        }
        r = self.client.post(self.list_url, body, format="json", **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        svc = GuestExtraService.objects.get(hotel=self.hotel, name="Airport transfer")
        self.assertEqual(svc.currency, "USD")
        self.assertTrue(svc.is_active)

    def test_create_denied_with_only_view(self):
        self._auth("services.view")
        r = self.client.post(
            self.list_url, {"name": "X", "currency": "USD"}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(GuestExtraService.objects.filter(name="X").exists())

    def test_update_with_services_update(self):
        svc = make_service(self.hotel, name="Laundry", price="50.00")
        self._auth("services.update")
        r = self.client.patch(
            self._detail(svc.id), {"unit_price": "65.00"}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        svc.refresh_from_db()
        self.assertEqual(svc.unit_price, Decimal("65.00"))

    def test_update_denied_with_only_view(self):
        svc = make_service(self.hotel, name="Laundry")
        self._auth("services.view")
        r = self.client.patch(
            self._detail(svc.id), {"unit_price": "65.00"}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_cannot_toggle_is_active(self):
        svc = make_service(self.hotel, name="Laundry")
        self._auth("services.update")
        r = self.client.patch(
            self._detail(svc.id), {"is_active": False}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        svc.refresh_from_db()
        # is_active is read-only on update; deactivation needs its own endpoint.
        self.assertTrue(svc.is_active)

    def test_deactivate_and_activate_with_services_delete(self):
        svc = make_service(self.hotel, name="Laundry")
        self._auth("services.delete")
        r = self.client.post(
            reverse("guest_services:catalog-deactivate", args=[svc.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        svc.refresh_from_db()
        self.assertFalse(svc.is_active)
        # Row is NOT deleted.
        self.assertTrue(GuestExtraService.objects.filter(pk=svc.pk).exists())
        # Reactivate counterpart.
        r2 = self.client.post(
            reverse("guest_services:catalog-activate", args=[svc.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        svc.refresh_from_db()
        self.assertTrue(svc.is_active)

    def test_deactivate_denied_without_services_delete(self):
        svc = make_service(self.hotel, name="Laundry")
        self._auth("services.update")
        r = self.client.post(
            reverse("guest_services:catalog-deactivate", args=[svc.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        svc.refresh_from_db()
        self.assertTrue(svc.is_active)

    def test_validation_rejections(self):
        self._auth("services.create")
        cases = [
            {"name": "Neg", "currency": "USD", "unit_price": "-1.00"},
            {"name": "Tax", "currency": "USD", "tax_rate": "150.00"},
            {"name": "Order", "currency": "USD", "display_order": -1},
            {"name": "Cur", "currency": "US"},
            {"name": "   ", "currency": "USD"},
        ]
        for body in cases:
            r = self.client.post(
                self.list_url, body, format="json", **HDR(self.hotel)
            )
            self.assertEqual(
                r.status_code, status.HTTP_400_BAD_REQUEST, f"{body} -> {r.data}"
            )
        self.assertEqual(GuestExtraService.objects.count(), 0)

    def test_duplicate_normalized_name_400(self):
        make_service(self.hotel, name="Extra Bed", category="extra_bed")
        self._auth("services.create")
        r = self.client.post(
            self.list_url,
            {"name": "  extra   BED ", "currency": "USD", "category": "extra_bed"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", r.data.get("details", r.data))
        self.assertEqual(GuestExtraService.objects.count(), 1)

    def test_hotel_isolation(self):
        other = make_hotel(slug="other")
        mine = make_service(self.hotel, name="Mine")
        theirs = make_service(other, name="Theirs")
        self._auth("services.view", "services.update")
        r = self.client.get(self.list_url, **HDR(self.hotel))
        names = [row["name"] for row in r.data["results"]]
        self.assertEqual(names, ["Mine"])
        # A cross-hotel detail is a 404.
        r2 = self.client.get(self._detail(theirs.id), **HDR(self.hotel))
        self.assertEqual(r2.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(mine.id)

    def test_no_delete_method_405(self):
        svc = make_service(self.hotel, name="Laundry")
        self._auth("services.view", "services.create", "services.update", "services.delete")
        r_list = self.client.delete(self.list_url, **HDR(self.hotel))
        r_detail = self.client.delete(self._detail(svc.id), **HDR(self.hotel))
        self.assertEqual(r_list.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(r_detail.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(GuestExtraService.objects.filter(pk=svc.pk).exists())


# --- Per-stay service line items (operational, money-safe) ------------------


class StayServiceLinesTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.stay = make_stay(self.hotel)
        self.folio = Folio.objects.get(
            hotel=self.hotel, stay=self.stay, status=FolioStatus.OPEN
        )

    def _url(self, stay=None):
        return reverse(
            "guest_services:stay-service-lines", args=[(stay or self.stay).id]
        )

    def _seed_lines(self):
        # Two counted service lines (guest_extra_service + service_order)...
        gx = add_charge(
            self.folio, charge_type=ChargeType.SERVICE, description="Laundry",
            quantity=1, unit_amount="20.00", tax_rate="0.00",
            source=ChargeSource.GUEST_EXTRA_SERVICE,
            service_name_snapshot="Laundry",
        )
        so = add_charge(
            self.folio, charge_type=ChargeType.SERVICE, description="Order ORD1",
            quantity=1, unit_amount="30.00", tax_rate="0.00",
            source=ChargeSource.SERVICE_ORDER,
        )
        # ...a voided guest_extra_service line (void history is operational)...
        voided = add_charge(
            self.folio, charge_type=ChargeType.SERVICE, description="Cancelled spa",
            quantity=1, unit_amount="99.00", tax_rate="0.00",
            source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        void_charge(voided, reason="guest complaint")
        # ...and EXCLUDED lines: a room night, an adjustment, a manual charge.
        add_charge(
            self.folio, charge_type=ChargeType.ROOM, description="night",
            quantity=1, unit_amount="100.00", source=ChargeSource.STAY_ROOM,
            room_night=timezone.localdate(),
        )
        add_charge(
            self.folio, charge_type=ChargeType.ADJUSTMENT, description="adj",
            quantity=1, unit_amount="-5.00", tax_rate="0.00",
            source=ChargeSource.ADJUSTMENT,
        )
        add_charge(
            self.folio, charge_type=ChargeType.SERVICE, description="manual",
            quantity=1, unit_amount="15.00", tax_rate="0.00",
            source=ChargeSource.MANUAL,
        )
        return gx, so, voided

    def test_returns_only_allowlisted_sources_including_voided(self):
        gx, so, voided = self._seed_lines()
        user = add_member(self.hotel, "so@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        r = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        by_id = {row["id"]: row for row in r.data}
        # Only the 3 service-source lines (incl. the voided one) are present.
        self.assertEqual(set(by_id), {gx.id, so.id, voided.id})
        self.assertEqual(
            {row["source"] for row in r.data},
            {"guest_extra_service", "service_order"},
        )
        # The FolioCharge id is exposed (so the FE can reuse the existing void).
        self.assertEqual(by_id[gx.id]["id"], gx.id)
        # Voided line carries its status + reason.
        self.assertEqual(by_id[voided.id]["status"], "voided")
        self.assertEqual(by_id[voided.id]["void_reason"], "guest complaint")
        # A posted line has no void metadata.
        self.assertIsNone(by_id[gx.id]["void_reason"])
        self.assertIsNone(by_id[gx.id]["voided_by"])
        # snapshot fallback + currency = folio currency; NO balance/payments keys.
        self.assertEqual(by_id[gx.id]["service_name_snapshot"], "Laundry")
        self.assertEqual(by_id[so.id]["service_name_snapshot"], "Order ORD1")
        self.assertEqual(by_id[gx.id]["currency"], self.folio.currency)
        for row in r.data:
            for forbidden in ("balance", "total_payments", "payments", "deposit"):
                self.assertNotIn(forbidden, row)

    def test_reachable_by_each_of_the_three_permissions(self):
        self._seed_lines()
        for code in ("service_orders.create", "services.view", "finance.view"):
            user = add_member(self.hotel, f"{code}@x.com", perms=(code,))
            self.client.force_authenticate(user)
            r = self.client.get(self._url(), **HDR(self.hotel))
            self.assertEqual(r.status_code, status.HTTP_200_OK, code)
            self.assertEqual(len(r.data), 3, code)

    def test_denied_without_any_of_three(self):
        user = add_member(self.hotel, "none@x.com", perms=("stays.view",))
        self.client.force_authenticate(user)
        r = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_hotel_stay_404(self):
        other = make_hotel(slug="other")
        other_stay = make_stay(other, room_number="900")
        user = add_member(self.hotel, "so@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        r = self.client.get(self._url(other_stay), **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_empty_or_no_open_folio_returns_empty_list(self):
        # A stay with no folio at all -> [] (200), not an error.
        no_folio_stay = make_stay(self.hotel, room_number="777", with_folio=False)
        user = add_member(self.hotel, "so@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        r = self.client.get(self._url(no_folio_stay), **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, [])
        # An open folio with no service lines -> also [].
        r2 = self.client.get(self._url(), **HDR(self.hotel))
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.data, [])

    def test_no_n_plus_one(self):
        user = add_member(self.hotel, "so@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        url = self._url()
        add_charge(
            self.folio, charge_type=ChargeType.SERVICE, description="l1",
            quantity=1, unit_amount="10.00", tax_rate="0.00",
            source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        with CaptureQueriesContext(connection) as ctx1:
            r1 = self.client.get(url, **HDR(self.hotel))
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        base = len(ctx1.captured_queries)
        for i in range(4):
            add_charge(
                self.folio, charge_type=ChargeType.SERVICE, description=f"l{i}",
                quantity=1, unit_amount="10.00", tax_rate="0.00",
                source=ChargeSource.SERVICE_ORDER,
            )
        with CaptureQueriesContext(connection) as ctx2:
            r2 = self.client.get(url, **HDR(self.hotel))
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r2.data), 5)
        self.assertEqual(len(ctx2.captured_queries), base, "service-lines has an N+1")
