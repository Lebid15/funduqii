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

    # --- B2: every aggregate is scoped to the OPEN folio --------------------

    def _stay_with_a_closed_and_an_open_folio(self):
        """A stay carrying a CLOSED folio (with money on it) BESIDE its open one.

        ``unique_open_folio_per_stay`` constrains OPEN folios only, so this state
        is permitted by the schema. The close is done with a direct ``update()``
        so the fixture builds the state without going through the check-out
        preconditions (a zero balance would defeat the point of the test)."""
        from apps.finance.services import record_payment

        stay = self._resident(1)
        closed = Folio.objects.get(stay=stay, status=FolioStatus.OPEN)
        add_charge(
            closed, charge_type=ChargeType.SERVICE, description="old svc",
            quantity=1, unit_amount="500.00", tax_rate="0.00",
            source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        record_payment(closed, amount=Decimal("200.00"), method="cash")
        Folio.objects.filter(pk=closed.pk).update(status=FolioStatus.CLOSED)

        open_folio = ensure_stay_folio(stay)
        self.assertNotEqual(open_folio.pk, closed.pk)
        add_charge(
            open_folio, charge_type=ChargeType.SERVICE, description="new svc",
            quantity=1, unit_amount="30.00", tax_rate="0.00",
            source=ChargeSource.GUEST_EXTRA_SERVICE,
        )
        record_payment(open_folio, amount=Decimal("10.00"), method="cash")
        return stay, closed, open_folio

    def test_directory_row_reflects_only_the_open_folio(self):
        stay, closed, open_folio = self._stay_with_a_closed_and_an_open_folio()
        r = self._get(self.finance_user)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        row = r.data["results"][0]
        self.assertEqual(row["stay_id"], stay.id)
        # ONLY the open folio: 1 service line of 30.00, paid 10.00 -> balance 20.00.
        # (Across both folios it would have been 2 lines / 530.00 / 320.00.)
        self.assertEqual(row["service_count"], 1)
        self.assertEqual(Decimal(row["service_total"]), Decimal("30.00"))
        self.assertEqual(Decimal(row["total_payments"]), Decimal("10.00"))
        self.assertEqual(Decimal(row["balance"]), Decimal("20.00"))
        # ...and the status/currency come from that SAME folio.
        self.assertEqual(row["folio_status"], FolioStatus.OPEN)
        self.assertEqual(row["currency"], open_folio.currency)

    def test_directory_agrees_with_the_service_lines_modal(self):
        """The card and the View-services modal must never disagree: the modal
        lists the OPEN folio only, so the card's count must match it."""
        stay, _closed, _open = self._stay_with_a_closed_and_an_open_folio()
        self.client.force_authenticate(self.finance_user)
        card = self.client.get(
            reverse("guest_services:folio-directory"), **HDR(self.hotel)
        ).data["results"][0]
        modal = self.client.get(
            reverse("guest_services:stay-service-lines", args=[stay.id]),
            **HDR(self.hotel),
        ).data
        self.assertEqual(card["service_count"], len(modal))
        self.assertEqual(
            Decimal(card["service_total"]),
            sum(Decimal(row["total_amount"]) for row in modal),
        )

    # --- B1: server-side search (guest name OR room number) -----------------

    def test_search_matches_guest_name_and_room_number(self):
        from apps.common.pagination import DefaultPagination

        a = self._resident(1)  # room 201, "Guest 201"
        b = self._resident(2)  # room 202, "Guest 202"
        Guest.objects.filter(pk=a.primary_guest_id).update(full_name="Alice Walker")
        Guest.objects.filter(pk=b.primary_guest_id).update(full_name="Bob Stone")
        self.client.force_authenticate(self.finance_user)
        url = reverse("guest_services:folio-directory")

        def ids(**params):
            r = self.client.get(url, params, **HDR(self.hotel))
            self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
            return [row["stay_id"] for row in r.data["results"]]

        # By guest name, case-insensitive + partial.
        self.assertEqual(ids(search="alice"), [a.id])
        self.assertEqual(ids(search="WALK"), [a.id])
        # By room number.
        self.assertEqual(ids(search="202"), [b.id])
        # No match -> empty, not everything.
        self.assertEqual(ids(search="zzzz"), [])
        # Blank / absent behaves exactly as today.
        self.assertEqual(sorted(ids(search="")), sorted([a.id, b.id]))
        self.assertEqual(sorted(ids(search="   ")), sorted([a.id, b.id]))
        self.assertEqual(sorted(ids()), sorted([a.id, b.id]))
        self.assertLessEqual(2, DefaultPagination.page_size)

    def test_search_finds_a_stay_that_is_not_on_page_one(self):
        """B1 — the whole point: filtering happens in the DB BEFORE pagination.

        A client-side filter over page 1 could only ever see the first
        ``page_size`` rows, so this resident would appear to not exist."""
        from apps.common.pagination import DefaultPagination

        page_size = DefaultPagination.page_size
        # Fill more than one full page. Ordering is by room number, so a high
        # room number is guaranteed to sort onto a later page.
        for n in range(page_size + 3):
            make_stay(
                self.hotel, room_number=f"3{n:03d}", floor=self.floor,
                room_type=self.rtype,
            )
        target = make_stay(
            self.hotel, room_number="9999", floor=self.floor, room_type=self.rtype
        )
        Guest.objects.filter(pk=target.primary_guest_id).update(
            full_name="Zenobia Farthing"
        )
        self.client.force_authenticate(self.finance_user)
        url = reverse("guest_services:folio-directory")

        # It is genuinely NOT on page 1.
        page1 = self.client.get(url, **HDR(self.hotel)).data
        self.assertEqual(len(page1["results"]), page_size)
        self.assertNotIn(target.id, [row["stay_id"] for row in page1["results"]])

        # ...yet a search from page 1 finds it, by name and by room number.
        for term in ("zenobia", "9999"):
            r = self.client.get(url, {"search": term}, **HDR(self.hotel))
            self.assertEqual(r.status_code, status.HTTP_200_OK)
            self.assertEqual(r.data["count"], 1, term)
            self.assertEqual(r.data["results"][0]["stay_id"], target.id, term)

    def test_search_is_hotel_scoped(self):
        mine = self._resident(1)
        Guest.objects.filter(pk=mine.primary_guest_id).update(full_name="Shared Name")
        other = make_hotel(slug="other-search")
        other_stay = make_stay(other, room_number="201")
        Guest.objects.filter(pk=other_stay.primary_guest_id).update(
            full_name="Shared Name"
        )
        self.client.force_authenticate(self.finance_user)
        r = self.client.get(
            reverse("guest_services:folio-directory"),
            {"search": "Shared Name"},
            **HDR(self.hotel),
        )
        self.assertEqual(r.data["count"], 1)
        self.assertEqual(r.data["results"][0]["stay_id"], mine.id)

    def test_search_does_not_introduce_an_n_plus_one(self):
        for n in (1, 2, 3):
            self._resident(n)
        self.client.force_authenticate(self.finance_user)
        url = reverse("guest_services:folio-directory")
        with CaptureQueriesContext(connection) as ctx1:
            r1 = self.client.get(url, {"search": "Guest"}, **HDR(self.hotel))
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.data["count"], 3)
        for n in (4, 5, 6):
            self._resident(n)
        with CaptureQueriesContext(connection) as ctx2:
            r2 = self.client.get(url, {"search": "Guest"}, **HDR(self.hotel))
        self.assertEqual(r2.data["count"], 6)
        self.assertEqual(
            len(ctx2.captured_queries), len(ctx1.captured_queries),
            "the search path added a per-row query",
        )
        # A searched row still carries the same shape as an unsearched one.
        self.assertEqual(
            set(r2.data["results"][0]),
            set(self.client.get(url, **HDR(self.hotel)).data["results"][0]),
        )

    def test_money_subqueries_are_skipped_without_finance_view(self):
        """C7 — a caller without ``finance.view`` must not even PAY for the money
        aggregates whose keys are stripped from its payload."""
        self._stay_with_a_closed_and_an_open_folio()
        op_user = add_member(self.hotel, "op-c7@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(op_user)
        url = reverse("guest_services:folio-directory")
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url, **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        directory_sql = [
            q["sql"] for q in ctx.captured_queries
            if "stays" in q["sql"] and "guest_extra_service" in q["sql"]
        ]
        self.assertTrue(directory_sql, "directory query not captured")
        for sql in directory_sql:
            self.assertNotIn(
                '"payments"', sql,
                "the payments aggregate is still computed without finance.view",
            )
        # The finance caller DOES get it (the annotation is not dead code).
        self.client.force_authenticate(self.finance_user)
        with CaptureQueriesContext(connection) as ctx2:
            self.client.get(url, **HDR(self.hotel))
        self.assertTrue(
            any('"payments"' in q["sql"] for q in ctx2.captured_queries),
            "the payments aggregate vanished for a finance.view caller",
        )


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
        # A1 — a PLAIN ARRAY, not a {count,next,previous,results} envelope.
        names = [row["name"] for row in r.data]
        # Ordered by display_order.
        self.assertEqual(names, ["A svc", "B svc", "Old svc"])
        # Active filter.
        r_active = self.client.get(
            self.list_url + "?is_active=true", **HDR(self.hotel)
        )
        active_names = [row["name"] for row in r_active.data]
        self.assertNotIn("Old svc", active_names)
        r_inactive = self.client.get(
            self.list_url + "?is_active=false", **HDR(self.hotel)
        )
        self.assertEqual([row["name"] for row in r_inactive.data], ["Old svc"])
        self.assertEqual(inactive.is_active, False)

    def test_catalog_list_is_a_plain_array(self):
        """A1 CONTRACT — the picker must see EVERY active service.

        The response is a LIST, never a paginated dict, and it is NOT truncated at
        the global ``DefaultPagination.page_size``. Seeding one more than a full
        page proves both at once: under the inherited pagination the last entries
        were unreachable, so a service past the page boundary could never be added.
        """
        from apps.common.pagination import DefaultPagination

        page_size = DefaultPagination.page_size
        total = page_size + 5
        for i in range(total):
            make_service(
                self.hotel, name=f"Svc {i:03d}", display_order=i, category="other"
            )
        self._auth("services.view")
        r = self.client.get(self.list_url, **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsInstance(r.data, list)
        self.assertNotIsInstance(r.data, dict)
        for envelope_key in ("count", "next", "previous", "results"):
            self.assertNotIn(envelope_key, r.data)
        self.assertEqual(len(r.data), total)
        # The entry PAST the page boundary is present (the whole point).
        self.assertIn(f"Svc {total - 1:03d}", [row["name"] for row in r.data])

    def test_list_denied_without_any_read_permission(self):
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
        names = [row["name"] for row in r.data]
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


# --- A2: the catalog must be readable by the persona that ADDS services -----


class CatalogReadPersonaTests(AddServiceMixin, APITestCase):
    """A2 — the catalog READ is the AddServiceModal's picker. Gating it on
    ``services.view`` alone locked the primary operational persona
    (``service_orders.create``) out of the very flow it is authorized to run."""

    def setUp(self):
        self.hotel = make_hotel()
        self.stay = make_stay(self.hotel)
        self.service = make_service(self.hotel, name="Laundry", price="50.00")
        self.list_url = reverse("guest_services:catalog-list")

    def test_service_orders_create_only_can_list_catalog_and_add_end_to_end(self):
        user = add_member(self.hotel, "so@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        # 1. The picker loads...
        r = self.client.get(self.list_url, **HDR(self.hotel))
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
        self.assertIsInstance(r.data, list)
        picked = [row for row in r.data if row["id"] == self.service.id]
        self.assertEqual(len(picked), 1, "the service is missing from the picker")
        # 2. ...the detail loads...
        d = self.client.get(
            reverse("guest_services:catalog-detail", args=[self.service.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(d.status_code, status.HTTP_200_OK)
        # 3. ...and the service can actually be added (end to end).
        add = self._add(
            self.hotel, self.stay, service=picked[0]["id"], quantity="1"
        )
        self.assertEqual(add.status_code, status.HTTP_201_CREATED, add.data)
        self.assertEqual(GuestServicePosting.objects.count(), 1)

    def test_catalog_read_open_to_each_of_the_three_codes(self):
        for code in ("service_orders.create", "services.view", "finance.view"):
            user = add_member(self.hotel, f"cat-{code}@x.com", perms=(code,))
            self.client.force_authenticate(user)
            r = self.client.get(self.list_url, **HDR(self.hotel))
            self.assertEqual(r.status_code, status.HTTP_200_OK, code)
            d = self.client.get(
                reverse("guest_services:catalog-detail", args=[self.service.id]),
                **HDR(self.hotel),
            )
            self.assertEqual(d.status_code, status.HTTP_200_OK, code)

    def test_catalog_writes_are_unchanged_by_the_widened_read(self):
        """The widened READ must not widen CREATE / UPDATE / DEACTIVATE."""
        user = add_member(self.hotel, "ro@x.com", perms=("service_orders.create",))
        self.client.force_authenticate(user)
        create = self.client.post(
            self.list_url, {"name": "New", "currency": "USD"}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        patch = self.client.patch(
            reverse("guest_services:catalog-detail", args=[self.service.id]),
            {"unit_price": "99.00"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)
        deact = self.client.post(
            reverse("guest_services:catalog-deactivate", args=[self.service.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(deact.status_code, status.HTTP_403_FORBIDDEN)
        self.service.refresh_from_db()
        self.assertEqual(self.service.unit_price, Decimal("50.00"))
        self.assertTrue(self.service.is_active)
        self.assertEqual(GuestExtraService.objects.count(), 1)


# --- A5: the REAL snapshot-immutability invariant ---------------------------


class SnapshotImmutabilityTests(AddServiceMixin, APITestCase):
    """A5 — repricing/renaming the CATALOG must never move an ALREADY-POSTED
    charge.

    This lives here, not in ``apps.finance``, because proving it requires mutating
    a real ``GuestExtraService`` row after posting — a dependency finance is
    forbidden to have (``test_no_fk_from_charge_to_guest_services``). The finance
    side can only assert that ``add_charge`` persists what it is handed; the
    invariant itself is only observable from this layer."""

    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(
            self.hotel, "adder@x.com",
            perms=("service_orders.create", "finance.charge_create", "finance.view"),
        )
        self.client.force_authenticate(self.user)
        self.stay = make_stay(self.hotel)
        self.service = make_service(
            self.hotel, name="Spa session", price="50.00", tax="10.00"
        )

    def test_catalog_rename_reprice_and_retax_never_move_a_posted_charge(self):
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="2")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        charge = FolioCharge.objects.get(source=ChargeSource.GUEST_EXTRA_SERVICE)
        before = {
            "unit_amount": charge.unit_amount,
            "amount": charge.amount,
            "tax_rate": charge.tax_rate,
            "tax_amount": charge.tax_amount,
            "total_amount": charge.total_amount,
            "description": charge.description,
            "service_name_snapshot": charge.service_name_snapshot,
            "unit_price_snapshot": charge.unit_price_snapshot,
            "tax_rate_snapshot": charge.tax_rate_snapshot,
            "currency_snapshot": charge.currency_snapshot,
        }
        self.assertEqual(before["unit_price_snapshot"], Decimal("50.00"))
        self.assertEqual(before["tax_rate_snapshot"], Decimal("10.00"))
        self.assertEqual(before["total_amount"], Decimal("110.00"))

        # MUTATE THE ACTUAL CATALOG ROW IN THE DB — rename AND reprice AND retax.
        GuestExtraService.objects.filter(pk=self.service.pk).update(
            name="Spa session (renamed)",
            name_normalized="spa session (renamed)",
            unit_price=Decimal("75.00"),
            tax_rate=Decimal("25.00"),
        )
        self.service.refresh_from_db()
        self.assertEqual(self.service.unit_price, Decimal("75.00"))
        self.assertEqual(self.service.tax_rate, Decimal("25.00"))
        self.assertEqual(self.service.name, "Spa session (renamed)")

        # The posted charge is UNCHANGED in every money and snapshot field.
        charge.refresh_from_db()
        for field, original in before.items():
            self.assertEqual(
                getattr(charge, field), original,
                f"{field} moved when the catalog was repriced",
            )
        # ...and so is the folio balance derived from it.
        from apps.finance.services import folio_balance

        folio = Folio.objects.get(
            hotel=self.hotel, stay=self.stay, status=FolioStatus.OPEN
        )
        self.assertEqual(folio_balance(folio)["balance"], Decimal("110.00"))

    def test_deactivating_the_catalog_entry_does_not_touch_a_posted_charge(self):
        r = self._add(self.hotel, self.stay, service=self.service.id, quantity="1")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        charge = FolioCharge.objects.get(source=ChargeSource.GUEST_EXTRA_SERVICE)
        self.service.is_active = False
        self.service.save(update_fields=["is_active", "updated_at"])
        charge.refresh_from_db()
        self.assertEqual(charge.total_amount, Decimal("55.00"))
        self.assertEqual(charge.status, PostingStatus.POSTED)
        self.assertEqual(charge.service_name_snapshot, "Spa session")


# --- B3 / B5 / B10: override audit, replay ordering, bounds -----------------


class VariablePriceAuditTests(AddServiceMixin, APITestCase):
    """B3 — the mandatory justification for a variable-price override is PERSISTED
    (it used to be validated and then discarded, leaving no audit trail)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(
            self.hotel, "adder@x.com",
            perms=("service_orders.create", "finance.charge_create", "finance.view"),
        )
        self.client.force_authenticate(self.user)
        self.stay = make_stay(self.hotel)
        self.fixed = make_service(self.hotel, name="Laundry", price="50.00", tax="0.00")
        # A NON-ZERO catalog price: a variable service billed without an override
        # still has to produce a positive amount (add_charge rejects a zero total).
        self.var = make_service(
            self.hotel, name="Damage", pricing_mode=PricingMode.VARIABLE,
            price="10.00", tax="0.00", category="damages",
        )

    def test_override_reason_is_persisted_on_the_posting(self):
        r = self._add(
            self.hotel, self.stay, service=self.var.id, quantity="1",
            unit_price_override="120.00", reason="  Broken bedside lamp  ",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
        posting = GuestServicePosting.objects.get()
        self.assertEqual(posting.price_override_reason, "Broken bedside lamp")

    def test_reason_not_stored_when_no_override_actually_applied(self):
        # FIXED service: the sent price/reason are ignored, so nothing to audit.
        r1 = self._add(
            self.hotel, self.stay, service=self.fixed.id, quantity="1",
            unit_price_override="999.00", reason="ignored on fixed",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        # VARIABLE service billed at the CATALOG price: no override, no reason.
        r2 = self._add(
            self.hotel, self.stay, service=self.var.id, quantity="1",
            reason="not an override",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.data)
        self.assertEqual(
            list(
                GuestServicePosting.objects.values_list(
                    "price_override_reason", flat=True
                )
            ),
            ["", ""],
        )

    def test_override_reason_is_exposed_on_the_service_lines_row(self):
        self._add(
            self.hotel, self.stay, service=self.var.id, quantity="1",
            unit_price_override="120.00", reason="Broken lamp",
        )
        self._add(self.hotel, self.stay, service=self.fixed.id, quantity="1")
        r = self.client.get(
            reverse("guest_services:stay-service-lines", args=[self.stay.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        by_name = {row["service_name_snapshot"]: row for row in r.data}
        self.assertEqual(by_name["Damage"]["price_override_reason"], "Broken lamp")
        # Stable shape: null (never missing) on an ordinary line.
        self.assertIn("price_override_reason", by_name["Laundry"])
        self.assertIsNone(by_name["Laundry"]["price_override_reason"])


class ReplayAfterDeactivationTests(AddServiceMixin, APITestCase):
    """B5 — a legitimate retry of an ALREADY-COMMITTED request must still replay
    after the catalog entry is deactivated. The ``is_active`` gate guards NEW
    postings only, so it runs after the idempotency fast path."""

    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(
            self.hotel, "adder@x.com", perms=("service_orders.create",)
        )
        self.client.force_authenticate(self.user)
        self.stay = make_stay(self.hotel)
        self.service = make_service(self.hotel, price="50.00", tax="0.00")

    def test_replay_survives_deactivation_and_creates_nothing(self):
        r1 = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="1",
            idempotency_key="retry-me",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)

        self.service.is_active = False
        self.service.save(update_fields=["is_active", "updated_at"])

        r2 = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="1",
            idempotency_key="retry-me",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.data)
        self.assertEqual(r2.data["id"], r1.data["id"])
        self.assertEqual(GuestServicePosting.objects.count(), 1)
        self.assertEqual(
            FolioCharge.objects.filter(
                source=ChargeSource.GUEST_EXTRA_SERVICE
            ).count(),
            1,
        )

    def test_a_new_key_on_a_deactivated_service_is_still_refused(self):
        """The relaxation is scoped to REPLAY only — a genuinely new posting of a
        deactivated service is still a 409 with no side effect."""
        self.service.is_active = False
        self.service.save(update_fields=["is_active", "updated_at"])
        r = self._add(
            self.hotel, self.stay, service=self.service.id, quantity="1",
            idempotency_key="brand-new",
        )
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(r.data["code"], "guest_service_inactive")
        self.assertEqual(GuestServicePosting.objects.count(), 0)
        self.assertEqual(FolioCharge.objects.count(), 0)


class QuantityAndFingerprintBoundsTests(AddServiceMixin, APITestCase):
    """B10 — the QA-identified gaps: the QUANTITY_MAX boundary and the exact
    sensitivity of the idempotency fingerprint."""

    def setUp(self):
        self.hotel = make_hotel()
        self.user = add_member(
            self.hotel, "adder@x.com",
            perms=("service_orders.create", "finance.charge_create", "finance.view"),
        )
        self.client.force_authenticate(self.user)
        self.stay = make_stay(self.hotel)
        self.cheap = make_service(self.hotel, name="Cheap", price="0.01", tax="0.00")
        self.fixed = make_service(self.hotel, name="Laundry", price="50.00", tax="0.00")
        self.var = make_service(
            self.hotel, name="Damage", pricing_mode=PricingMode.VARIABLE,
            price="10.00", tax="0.00", category="damages",
        )

    def test_quantity_at_max_is_accepted_and_above_max_is_refused(self):
        from apps.guest_services.services import QUANTITY_MAX

        # Reachable through the serializer (max_digits=8, decimal_places=2 ->
        # 100000.00 fits) and accepted exactly AT the bound.
        at_max = self._add(
            self.hotel, self.stay, service=self.cheap.id, quantity=str(QUANTITY_MAX)
        )
        self.assertEqual(at_max.status_code, status.HTTP_201_CREATED, at_max.data)
        charge = FolioCharge.objects.get(source=ChargeSource.GUEST_EXTRA_SERVICE)
        self.assertEqual(charge.quantity, QUANTITY_MAX)
        self.assertEqual(charge.total_amount, Decimal("1000.00"))

        # One cent over the bound is refused, with NO second charge.
        over = self._add(
            self.hotel, self.stay, service=self.cheap.id,
            quantity=str(QUANTITY_MAX + Decimal("0.01")),
        )
        self.assertEqual(over.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(GuestServicePosting.objects.count(), 1)

    def test_fingerprint_sensitive_to_override_price_on_variable(self):
        r1 = self._add(
            self.hotel, self.stay, service=self.var.id, quantity="1",
            unit_price_override="120.00", reason="broken lamp",
            idempotency_key="k-var",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        r2 = self._add(
            self.hotel, self.stay, service=self.var.id, quantity="1",
            unit_price_override="500.00", reason="broken lamp",
            idempotency_key="k-var",
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT, r2.data)
        self.assertEqual(r2.data["code"], "idempotency_key_conflict")
        self.assertEqual(GuestServicePosting.objects.count(), 1)

    def test_fingerprint_ignores_price_on_a_fixed_service(self):
        """INTENTIONAL rule: a FIXED service ignores the client price, so the price
        is excluded from the fingerprint and a differing one still REPLAYS."""
        r1 = self._add(
            self.hotel, self.stay, service=self.fixed.id, quantity="1",
            unit_price_override="70.00", reason="", idempotency_key="k-fixed",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        r2 = self._add(
            self.hotel, self.stay, service=self.fixed.id, quantity="1",
            unit_price_override="999.00", reason="", idempotency_key="k-fixed",
        )
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED, r2.data)
        self.assertEqual(r2.data["id"], r1.data["id"])
        self.assertEqual(GuestServicePosting.objects.count(), 1)
        # The catalog price won on both calls.
        self.assertEqual(
            FolioCharge.objects.get(
                source=ChargeSource.GUEST_EXTRA_SERVICE
            ).unit_amount,
            Decimal("50.00"),
        )

    def test_fingerprint_sensitive_to_reason(self):
        r1 = self._add(
            self.hotel, self.stay, service=self.var.id, quantity="1",
            unit_price_override="120.00", reason="broken lamp",
            idempotency_key="k-reason",
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED, r1.data)
        r2 = self._add(
            self.hotel, self.stay, service=self.var.id, quantity="1",
            unit_price_override="120.00", reason="stained carpet",
            idempotency_key="k-reason",
        )
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT, r2.data)
        self.assertEqual(r2.data["code"], "idempotency_key_conflict")
        self.assertEqual(GuestServicePosting.objects.count(), 1)
        # And the stored audit reason is the FIRST one (the replay changed nothing).
        self.assertEqual(
            GuestServicePosting.objects.get().price_override_reason, "broken lamp"
        )


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
