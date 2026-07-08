"""Tests for internal finance (Phase 8): access/permissions, folios, charges,
payments, invoices, expenses, numbering, overview, and regression."""
from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.models import (
    Expense,
    Folio,
    FolioCharge,
    Invoice,
    Payment,
)
from apps.rbac.services import grant_permission
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

ALL_FINANCE = [
    "finance.view", "finance.create", "finance.update", "finance.close",
    "finance.void", "finance.charge_create", "finance.charge_void",
    "finance.payment_create", "finance.payment_void", "finance.invoice_create",
    "finance.invoice_issue", "finance.invoice_void",
    "expenses.view", "expenses.create", "expenses.update", "expenses.void",
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


class FinanceMixin:
    def create_folio(self, **body):
        return self.client.post(
            reverse("finance:folio-list"), body, format="json", **HDR(self.hotel)
        )

    def add_charge(self, fid, **body):
        body.setdefault("type", "service")
        body.setdefault("description", "Room service")
        body.setdefault("quantity", "1")
        body.setdefault("unit_amount", "100.00")
        return self.client.post(
            reverse("finance:folio-charge-create", args=[fid]), body, format="json", **HDR(self.hotel)
        )

    def add_payment(self, fid, **body):
        body.setdefault("amount", "100.00")
        body.setdefault("method", "cash")
        return self.client.post(
            reverse("finance:folio-payment-create", args=[fid]), body, format="json", **HDR(self.hotel)
        )


# --------------------------------------------------------------------------- #
# Access / permissions                                                         #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase, FinanceMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(reverse("finance:folio-list"), **HDR(self.hotel)).status_code, 401
        )

    def test_other_hotel_denied(self):
        other = make_hotel(slug="o")
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.get(reverse("finance:folio-list"), **HDR(other)).status_code, 403
        )

    def test_platform_owner_denied(self):
        owner = User.objects.create_platform_owner(
            email="o@x.com", password="StrongPass!234", full_name="Owner"
        )
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(reverse("finance:folio-list"), **HDR(self.hotel)).status_code, 403
        )

    def test_staff_view_permission(self):
        staff = add_member(self.hotel, "s@x.com", perms=["finance.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("finance:folio-list"), **HDR(self.hotel)).status_code, 200
        )

    def test_staff_without_permission_denied(self):
        staff = add_member(self.hotel, "s2@x.com")
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(reverse("finance:folio-list"), **HDR(self.hotel)).status_code, 403
        )

    def test_staff_payment_create_permission(self):
        self.client.force_authenticate(self.manager)
        fid = self.create_folio(customer_name="Walk in").data["id"]
        staff = add_member(self.hotel, "s3@x.com", perms=["finance.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(self.add_payment(fid).status_code, 403)
        staff2 = add_member(self.hotel, "s4@x.com", perms=["finance.payment_create"])
        self.client.force_authenticate(staff2)
        self.assertEqual(self.add_payment(fid).status_code, 201)

    def test_staff_invoice_issue_permission(self):
        self.client.force_authenticate(self.manager)
        fid = self.create_folio(customer_name="X").data["id"]
        self.add_charge(fid)
        inv = self.client.post(reverse("finance:folio-invoice-create", args=[fid]), {}, format="json", **HDR(self.hotel)).data["id"]
        staff = add_member(self.hotel, "s5@x.com", perms=["finance.view"])
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.post(reverse("finance:invoice-issue", args=[inv]), {}, format="json", **HDR(self.hotel)).status_code, 403
        )
        staff2 = add_member(self.hotel, "s6@x.com", perms=["finance.invoice_issue"])
        self.client.force_authenticate(staff2)
        self.assertEqual(
            self.client.post(reverse("finance:invoice-issue", args=[inv]), {}, format="json", **HDR(self.hotel)).status_code, 200
        )

    def test_suspended_hotel_read_only(self):
        self.client.force_authenticate(self.manager)
        fid = self.create_folio(customer_name="X").data["id"]
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save()
        self.assertEqual(
            self.client.get(reverse("finance:folio-list"), **HDR(self.hotel)).status_code, 200
        )
        res = self.add_charge(fid)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")


# --------------------------------------------------------------------------- #
# Folios                                                                        #
# --------------------------------------------------------------------------- #


class FolioTests(APITestCase, FinanceMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)

    def test_create_folio_and_number(self):
        res = self.create_folio(customer_name="Alice")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data["folio_number"].startswith("FOL"))
        self.assertEqual(res.data["status"], "open")

    def test_folio_number_unique_and_independent_per_hotel(self):
        f1 = self.create_folio(customer_name="A")
        self.assertEqual(f1.data["folio_number"], "FOL00001")
        f2 = self.create_folio(customer_name="B")
        self.assertEqual(f2.data["folio_number"], "FOL00002")
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        om = User.objects.get(email="om@x.com")
        self.client.force_authenticate(om)
        fo = self.client.post(reverse("finance:folio-list"), {"customer_name": "C"}, format="json", **HDR(other))
        self.assertEqual(fo.data["folio_number"], "FOL00001")

    def test_balance_from_charges_and_payments(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="200.00")
        self.add_payment(fid, amount="50.00")
        folio = self.client.get(reverse("finance:folio-detail", args=[fid]), **HDR(self.hotel)).data
        self.assertEqual(folio["balance"]["total_charges"], "200.00")
        self.assertEqual(folio["balance"]["total_payments"], "50.00")
        self.assertEqual(folio["balance"]["balance"], "150.00")

    def test_cannot_close_folio_with_balance(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="100.00")
        res = self.client.post(reverse("finance:folio-close", args=[fid]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "folio_not_balanced")

    def test_can_close_zero_balance_folio(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="100.00")
        self.add_payment(fid, amount="100.00")
        res = self.client.post(reverse("finance:folio-close", args=[fid]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "closed")

    def test_cannot_charge_closed_folio(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="100.00")
        self.add_payment(fid, amount="100.00")
        self.client.post(reverse("finance:folio-close", args=[fid]), {}, format="json", **HDR(self.hotel))
        res = self.add_charge(fid, unit_amount="10.00")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "folio_closed")

    def test_void_folio_requires_reason(self):
        fid = self.create_folio(customer_name="A").data["id"]
        no = self.client.post(reverse("finance:folio-void", args=[fid]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(no.status_code, 400)
        ok = self.client.post(reverse("finance:folio-void", args=[fid]), {"reason": "duplicate"}, format="json", **HDR(self.hotel))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["status"], "voided")


# --------------------------------------------------------------------------- #
# Charges                                                                       #
# --------------------------------------------------------------------------- #


class ChargeTests(APITestCase, FinanceMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]

    def test_charge_totals_with_tax(self):
        self.add_charge(self.fid, quantity="2", unit_amount="100.00", tax_rate="15.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        self.assertEqual(charge.amount, Decimal("200.00"))
        self.assertEqual(charge.tax_amount, Decimal("30.00"))
        self.assertEqual(charge.total_amount, Decimal("230.00"))

    def test_negative_amount_rejected_for_service(self):
        res = self.add_charge(self.fid, type="service", unit_amount="-50.00")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_amount")

    def test_discount_allows_negative(self):
        res = self.add_charge(self.fid, type="discount", description="Loyalty", unit_amount="-20.00")
        self.assertEqual(res.status_code, 201)

    def test_void_charge_requires_reason_and_excludes_from_balance(self):
        self.add_charge(self.fid, unit_amount="100.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        no = self.client.post(reverse("finance:charge-void", args=[charge.id]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(no.status_code, 400)
        ok = self.client.post(reverse("finance:charge-void", args=[charge.id]), {"reason": "mistake"}, format="json", **HDR(self.hotel))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["balance"]["balance"], "0.00")

    def test_no_hard_delete_endpoint(self):
        self.add_charge(self.fid, unit_amount="100.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        # There is no charge detail/delete route.
        res = self.client.delete(f"/api/v1/hotel/finance/charges/{charge.id}/", **HDR(self.hotel))
        self.assertIn(res.status_code, (404, 405))
        self.assertTrue(FolioCharge.objects.filter(pk=charge.id).exists())


# --------------------------------------------------------------------------- #
# Payments                                                                      #
# --------------------------------------------------------------------------- #


class PaymentTests(APITestCase, FinanceMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(self.fid, unit_amount="300.00")

    def test_payment_receipt_unique_and_reduces_balance(self):
        r = self.add_payment(self.fid, amount="100.00")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data["payment"]["receipt_number"].startswith("RCP"))
        self.assertEqual(r.data["folio"]["balance"]["balance"], "200.00")

    def test_non_positive_amount_rejected(self):
        res = self.add_payment(self.fid, amount="0.00")
        self.assertEqual(res.status_code, 400)

    def test_void_payment_requires_reason_and_excludes(self):
        pid = self.add_payment(self.fid, amount="100.00").data["payment"]["id"]
        no = self.client.post(reverse("finance:payment-void", args=[pid]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(no.status_code, 400)
        ok = self.client.post(reverse("finance:payment-void", args=[pid]), {"reason": "error"}, format="json", **HDR(self.hotel))
        self.assertEqual(ok.status_code, 200)
        folio = self.client.get(reverse("finance:folio-detail", args=[self.fid]), **HDR(self.hotel)).data
        self.assertEqual(folio["balance"]["total_payments"], "0.00")

    def test_receipt_print_friendly(self):
        pid = self.add_payment(self.fid, amount="100.00").data["payment"]["id"]
        res = self.client.get(reverse("finance:payment-receipt", args=[pid]), **HDR(self.hotel))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["document"], "receipt")
        self.assertIn("hotel_name", res.data["hotel"])


# --------------------------------------------------------------------------- #
# Invoices                                                                      #
# --------------------------------------------------------------------------- #


class InvoiceTests(APITestCase, FinanceMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="Alice").data["id"]

    def _draft(self):
        return self.client.post(reverse("finance:folio-invoice-create", args=[self.fid]), {}, format="json", **HDR(self.hotel))

    def _issue(self, iid):
        return self.client.post(reverse("finance:invoice-issue", args=[iid]), {}, format="json", **HDR(self.hotel))

    def test_issue_snapshots_lines_and_number(self):
        self.add_charge(self.fid, quantity="2", unit_amount="100.00", tax_rate="10.00")
        iid = self._draft().data["id"]
        res = self._issue(iid)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["invoice_number"].startswith("INV"))
        self.assertEqual(res.data["status"], "issued")
        self.assertEqual(res.data["subtotal"], "200.00")
        self.assertEqual(res.data["tax_total"], "20.00")
        self.assertEqual(res.data["total"], "220.00")
        self.assertEqual(len(res.data["lines"]), 1)

    def test_issued_lines_frozen_when_charges_change(self):
        self.add_charge(self.fid, unit_amount="100.00")
        iid = self._draft().data["id"]
        self._issue(iid)
        # Void the charge AFTER issuing; the invoice snapshot must not change.
        charge = FolioCharge.objects.get(folio_id=self.fid)
        self.client.post(reverse("finance:charge-void", args=[charge.id]), {"reason": "x"}, format="json", **HDR(self.hotel))
        inv = self.client.get(reverse("finance:invoice-detail", args=[iid]), **HDR(self.hotel)).data
        self.assertEqual(inv["total"], "100.00")
        self.assertEqual(len(inv["lines"]), 1)

    def test_cannot_issue_without_charges(self):
        iid = self._draft().data["id"]
        res = self._issue(iid)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_finance_operation")

    def test_cannot_issue_twice(self):
        self.add_charge(self.fid, unit_amount="100.00")
        iid = self._draft().data["id"]
        self._issue(iid)
        res = self._issue(iid)
        self.assertEqual(res.status_code, 400)

    def test_void_invoice_requires_reason(self):
        self.add_charge(self.fid, unit_amount="100.00")
        iid = self._draft().data["id"]
        self._issue(iid)
        no = self.client.post(reverse("finance:invoice-void", args=[iid]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(no.status_code, 400)
        ok = self.client.post(reverse("finance:invoice-void", args=[iid]), {"reason": "reissue"}, format="json", **HDR(self.hotel))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["status"], "voided")

    def test_invoice_print_friendly(self):
        self.add_charge(self.fid, unit_amount="100.00")
        iid = self._draft().data["id"]
        self._issue(iid)
        res = self.client.get(reverse("finance:invoice-print", args=[iid]), **HDR(self.hotel))
        self.assertEqual(res.data["document"], "invoice")


# --------------------------------------------------------------------------- #
# Expenses / numbering / overview / regression                                 #
# --------------------------------------------------------------------------- #


class ExpenseTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)

    def _create(self, **body):
        body.setdefault("category", "supplies")
        body.setdefault("description", "Towels")
        body.setdefault("amount", "80.00")
        body.setdefault("method", "cash")
        return self.client.post(reverse("finance:expense-list"), body, format="json", **HDR(self.hotel))

    def test_create_and_voucher_number(self):
        res = self._create()
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data["expense_number"].startswith("EXP"))

    def test_positive_amount(self):
        self.assertEqual(self._create(amount="0.00").status_code, 400)

    def test_scoped_by_hotel(self):
        self._create()
        other = make_hotel(slug="o")
        Expense.objects.create(hotel=other, expense_number="EXP00001", category="other", description="X", amount=Decimal("5.00"), method="cash", paid_at="2030-01-01T00:00:00Z")
        self.assertEqual(self.client.get(reverse("finance:expense-list"), **HDR(self.hotel)).data["count"], 1)

    def test_void_requires_reason(self):
        eid = self._create().data["id"]
        no = self.client.post(reverse("finance:expense-void", args=[eid]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(no.status_code, 400)
        ok = self.client.post(reverse("finance:expense-void", args=[eid]), {"reason": "wrong"}, format="json", **HDR(self.hotel))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["status"], "voided")


class NumberingTests(APITestCase, FinanceMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)

    def test_sequences_independent_per_kind(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="10.00")
        pr = self.add_payment(fid, amount="5.00")
        self.assertEqual(Folio.objects.get(pk=fid).folio_number, "FOL00001")
        self.assertEqual(pr.data["payment"]["receipt_number"], "RCP00001")
        self.assertEqual(Expense.objects.count(), 0)


class OverviewTests(APITestCase, FinanceMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)

    def test_overview_totals(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="200.00")
        self.add_payment(fid, amount="120.00")  # paid_at defaults to now -> today
        self.client.post(reverse("finance:expense-list"), {"category": "supplies", "description": "X", "amount": "50.00", "method": "cash"}, format="json", **HDR(self.hotel))
        ov = self.client.get(reverse("finance:overview"), **HDR(self.hotel)).data
        self.assertEqual(ov["open_folios"], 1)
        self.assertEqual(ov["outstanding_balance"], "80.00")
        self.assertEqual(ov["unpaid_folios"], 1)
        self.assertEqual(ov["payments_today"], "120.00")
        self.assertEqual(ov["expenses_today"], "50.00")
        self.assertEqual(ov["net_today"], "70.00")


class RegressionTests(APITestCase):
    def test_health_and_prior_apis(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
        hotel = make_hotel()
        mgr = add_member(hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(mgr)
        for name in ("rooms:room-list", "reservations:reservation-list", "stays:stay-current", "guests:guest-list"):
            self.assertEqual(self.client.get(reverse(name), **HDR(hotel)).status_code, 200, name)

    def test_finance_tables_present_no_forbidden(self):
        from django.apps import apps as django_apps

        tables = {m._meta.db_table for m in django_apps.get_models()}
        for present in ("folios", "payments", "invoices", "expenses"):
            self.assertIn(present, tables)
        # Still no restaurant/stock/daily-close/shift models.
        for forbidden in ("restaurant_orders", "stock_items", "daily_closes", "shifts", "payroll"):
            self.assertNotIn(forbidden, tables)
