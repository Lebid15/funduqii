"""Tests for internal finance (Phase 8): access/permissions, folios, charges,
payments, invoices, expenses, numbering, overview, and regression."""
from __future__ import annotations

from decimal import Decimal

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.models import (
    Expense,
    ExpenseType,
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
    "expenses.reverse", "expenses.manage_types",
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
        # P4 — a negative amount on the generic charge-create path is now
        # rejected up-front by the serializer (must_not_be_negative), still a
        # clean 400. Credits/negatives belong to finance.adjust.
        res = self.add_charge(self.fid, type="service", unit_amount="-50.00")
        self.assertEqual(res.status_code, 400)
        self.assertIn("must_not_be_negative", str(res.data))

    def test_discount_and_adjustment_refused_via_charge_create(self):
        # P4 — credit corrections no longer go through the generic charge-create
        # path (they belong to finance.adjust / adjust_charge, which is reasoned,
        # linked, one-per-original and audited). Both credit TYPES and any
        # negative amount are rejected here with a clean 400.
        for t in ("discount", "adjustment"):
            res = self.add_charge(self.fid, type=t, description="Loyalty", unit_amount="20.00")
            self.assertEqual(res.status_code, 400, f"{t}: {res.data}")
            self.assertIn("credit_charges_go_through_adjust", str(res.data))
        neg = self.add_charge(self.fid, type="other", description="X", unit_amount="-20.00")
        self.assertEqual(neg.status_code, 400)
        self.assertIn("must_not_be_negative", str(neg.data))

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
        # EXPENSES-CLOSURE: new expenses reference a manageable ExpenseType, not
        # the legacy fixed category enum.
        self.expense_type = self.client.post(
            reverse("finance:expense-type-list"), {"name": "Supplies"},
            format="json", **HDR(self.hotel),
        ).data["id"]

    def _create(self, **body):
        body.setdefault("expense_type", self.expense_type)
        body.setdefault("description", "Towels")
        body.setdefault("amount", "80.00")
        body.setdefault("method", "cash")
        return self.client.post(reverse("finance:expense-list"), body, format="json", **HDR(self.hotel))

    def test_create_and_voucher_number(self):
        res = self._create()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["expense_number"].startswith("EXP"))
        self.assertEqual(res.data["expense_type"], self.expense_type)
        self.assertEqual(res.data["expense_type_name"], "Supplies")

    def test_positive_amount(self):
        self.assertEqual(self._create(amount="0.00").status_code, 400)

    def test_scoped_by_hotel(self):
        self._create()
        other = make_hotel(slug="o")
        other_type = ExpenseType.objects.create(
            hotel=other, name="Other", name_normalized="other"
        )
        Expense.objects.create(
            hotel=other, expense_number="EXP00001", expense_type=other_type,
            category="other", description="X", amount=Decimal("5.00"),
            method="cash", paid_at="2030-01-01T00:00:00Z",
        )
        self.assertEqual(self.client.get(reverse("finance:expense-list"), **HDR(self.hotel)).data["count"], 1)

    def test_void_requires_reason(self):
        eid = self._create().data["id"]
        no = self.client.post(reverse("finance:expense-void", args=[eid]), {}, format="json", **HDR(self.hotel))
        self.assertEqual(no.status_code, 400)
        ok = self.client.post(reverse("finance:expense-void", args=[eid]), {"reason": "wrong"}, format="json", **HDR(self.hotel))
        self.assertEqual(ok.status_code, 200)
        # The void response is a MINIMAL ack (not the full serializer).
        self.assertEqual(ok.data["status"], "voided")
        self.assertEqual(set(ok.data.keys()), {"id", "expense_number", "status", "voided_at"})


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
        etype = self.client.post(
            reverse("finance:expense-type-list"), {"name": "Supplies"},
            format="json", **HDR(self.hotel),
        ).data["id"]
        self.client.post(reverse("finance:expense-list"), {"expense_type": etype, "description": "X", "amount": "50.00", "method": "cash"}, format="json", **HDR(self.hotel))
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
        # Shifts/daily close arrived legitimately in Phase 12; still no
        # restaurant/stock/payroll/attendance models.
        for forbidden in ("restaurant_orders", "stock_items", "payroll", "attendance_records"):
            self.assertNotIn(forbidden, tables)


# --------------------------------------------------------------------------- #
# Folio final closure round                                                    #
# --------------------------------------------------------------------------- #

from datetime import timedelta

from django.db import IntegrityError, transaction as db_transaction

from apps.finance import services as fin
from apps.finance.models import FolioStatus, PostingStatus
from apps.guests.models import Guest
from apps.hotels.models import HotelSettings
from apps.notifications.models import ActivityEvent
from apps.rooms.models import Floor, Room, RoomType
from apps.shifts.models import DailyClose, DailyCloseStatus
from apps.stays.models import Stay


class ClosureMixin(FinanceMixin):
    """Helpers for the folio closure round: business date, day close, and
    "aging" a record so its void window has passed."""

    _dc = {"n": 0}

    def bd(self):
        from apps.shifts.services import get_business_date

        return get_business_date(self.hotel)

    def close_day(self, hotel=None, on_date=None):
        ClosureMixin._dc["n"] += 1
        return DailyClose.objects.create(
            hotel=hotel or self.hotel,
            close_number=f"DC9{ClosureMixin._dc['n']:04d}",
            business_date=on_date or self.bd(),
            status=DailyCloseStatus.CLOSED,
            snapshot_json={},
            totals_json={},
        )

    def age_charge(self, charge, days=1):
        FolioCharge.objects.filter(pk=charge.pk).update(
            charge_date=self.bd() - timedelta(days=days)
        )
        charge.refresh_from_db()
        return charge

    def age_payment(self, payment, days=1):
        Payment.objects.filter(pk=payment.pk).update(
            business_date=self.bd() - timedelta(days=days)
        )
        payment.refresh_from_db()
        return payment

    def void_charge_api(self, cid, reason="mistake"):
        return self.client.post(
            reverse("finance:charge-void", args=[cid]), {"reason": reason},
            format="json", **HDR(self.hotel),
        )

    def adjust_api(self, cid, reason="late correction", hotel=None):
        return self.client.post(
            reverse("finance:charge-adjust", args=[cid]), {"reason": reason},
            format="json", **HDR(hotel or self.hotel),
        )

    def void_payment_api(self, pid, reason="mistake"):
        return self.client.post(
            reverse("finance:payment-void", args=[pid]), {"reason": reason},
            format="json", **HDR(self.hotel),
        )

    def reverse_api(self, pid, reason="late correction", hotel=None):
        return self.client.post(
            reverse("finance:payment-reverse", args=[pid]), {"reason": reason},
            format="json", **HDR(hotel or self.hotel),
        )

    def close_folio_api(self, fid):
        return self.client.post(
            reverse("finance:folio-close", args=[fid]), {}, format="json",
            **HDR(self.hotel),
        )

    def void_folio_api(self, fid, reason="duplicate"):
        return self.client.post(
            reverse("finance:folio-void", args=[fid]), {"reason": reason},
            format="json", **HDR(self.hotel),
        )


class ClosedFolioProtectionTests(APITestCase, ClosureMixin):
    """A closed/voided folio is fully read-only — nothing inside it moves."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(self.fid, unit_amount="100.00")
        self.add_payment(self.fid, amount="100.00")
        self.charge = FolioCharge.objects.get(folio_id=self.fid)
        self.payment = Payment.objects.get(folio_id=self.fid)
        self.assertEqual(self.close_folio_api(self.fid).status_code, 200)

    def test_void_charge_on_closed_folio_refused(self):
        r = self.void_charge_api(self.charge.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_closed")
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.status, PostingStatus.POSTED)

    def test_void_payment_on_closed_folio_refused(self):
        r = self.void_payment_api(self.payment.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_closed")

    def test_void_closed_folio_refused(self):
        r = self.void_folio_api(self.fid)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_closed")

    def test_patch_notes_on_closed_folio_refused(self):
        r = self.client.patch(
            reverse("finance:folio-detail", args=[self.fid]),
            {"notes": "late edit"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_closed")

    def test_invoice_create_on_closed_folio_refused(self):
        r = self.client.post(
            reverse("finance:folio-invoice-create", args=[self.fid]), {},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_closed")

    def test_adjust_on_closed_folio_refused(self):
        self.age_charge(self.charge)
        r = self.adjust_api(self.charge.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_closed")

    def test_reverse_on_closed_folio_refused(self):
        self.age_payment(self.payment)
        r = self.reverse_api(self.payment.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_closed")

    def test_void_open_folio_with_postings_refused(self):
        fid2 = self.create_folio(customer_name="B").data["id"]
        self.add_charge(fid2, unit_amount="10.00")
        r = self.void_folio_api(fid2)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "folio_has_postings")

    def test_void_empty_open_folio_ok(self):
        fid2 = self.create_folio(customer_name="C").data["id"]
        r = self.void_folio_api(fid2)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "voided")


class VoidWindowTests(APITestCase, ClosureMixin):
    """Void only inside the record's own OPEN business date."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]

    def test_same_day_void_charge_ok(self):
        self.add_charge(self.fid, unit_amount="50.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        self.assertEqual(self.void_charge_api(charge.id).status_code, 200)

    def test_void_charge_from_previous_day_refused(self):
        self.add_charge(self.fid, unit_amount="50.00")
        charge = self.age_charge(FolioCharge.objects.get(folio_id=self.fid))
        r = self.void_charge_api(charge.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "void_window_closed")

    def test_void_charge_after_day_close_refused(self):
        self.add_charge(self.fid, unit_amount="50.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        self.close_day()
        r = self.void_charge_api(charge.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "void_window_closed")

    def test_void_payment_from_previous_day_refused(self):
        self.add_payment(self.fid, amount="20.00")
        payment = self.age_payment(Payment.objects.get(folio_id=self.fid))
        r = self.void_payment_api(payment.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "void_window_closed")

    def test_add_charge_on_closed_business_day_refused(self):
        self.close_day()
        r = self.add_charge(self.fid, unit_amount="10.00")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "business_day_closed")

    def test_charge_stamped_with_business_date(self):
        self.add_charge(self.fid, unit_amount="10.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        self.assertEqual(charge.charge_date, self.bd())

    def test_payment_stamped_with_business_date(self):
        self.add_payment(self.fid, amount="10.00")
        payment = Payment.objects.get(folio_id=self.fid)
        self.assertEqual(payment.business_date, self.bd())

    def test_client_charge_date_rejected(self):
        r = self.add_charge(self.fid, unit_amount="10.00", charge_date="2020-01-01")
        self.assertEqual(r.status_code, 400)

    def test_client_paid_at_rejected(self):
        r = self.add_payment(self.fid, amount="10.00", paid_at="2020-01-01T00:00:00Z")
        self.assertEqual(r.status_code, 400)

    def test_client_currency_rejected_on_folio_create(self):
        r = self.create_folio(customer_name="X", currency="EUR")
        self.assertEqual(r.status_code, 400)


class AdjustmentTests(APITestCase, ClosureMixin):
    """Full linked counter-charge once the void window has passed."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]

    def _aged_charge(self, unit="100.00", tax="15.00"):
        self.add_charge(self.fid, unit_amount=unit, tax_rate=tax)
        return self.age_charge(
            FolioCharge.objects.filter(folio_id=self.fid).latest("id")
        )

    def test_adjust_requires_reason(self):
        charge = self._aged_charge()
        r = self.client.post(
            reverse("finance:charge-adjust", args=[charge.id]), {},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)

    def test_adjust_same_day_refused_use_void(self):
        self.add_charge(self.fid, unit_amount="10.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        r = self.adjust_api(charge.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "void_window_open")

    def test_adjust_links_and_negates_full_total(self):
        charge = self._aged_charge()  # total 115.00
        r = self.adjust_api(charge.id)
        self.assertEqual(r.status_code, 201)
        adj = FolioCharge.objects.get(folio_id=self.fid, adjusts=charge)
        self.assertEqual(adj.type, "adjustment")
        self.assertEqual(adj.total_amount, -charge.total_amount)
        self.assertEqual(adj.charge_date, self.bd())
        self.assertEqual(adj.status, PostingStatus.POSTED)
        charge.refresh_from_db()
        self.assertEqual(charge.status, PostingStatus.POSTED)
        folio = self.client.get(
            reverse("finance:folio-detail", args=[self.fid]), **HDR(self.hotel)
        ).data
        self.assertEqual(folio["balance"]["balance"], "0.00")

    def test_adjust_twice_refused(self):
        charge = self._aged_charge()
        self.assertEqual(self.adjust_api(charge.id).status_code, 201)
        r = self.adjust_api(charge.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "charge_already_adjusted")

    def test_adjust_again_after_adjustment_voided(self):
        charge = self._aged_charge()
        self.adjust_api(charge.id)
        adj = FolioCharge.objects.get(folio_id=self.fid, adjusts=charge)
        # The adjustment itself is a today-record: same-day void undoes it...
        self.assertEqual(self.void_charge_api(adj.id).status_code, 200)
        # ...and frees the slot for a corrected adjustment.
        self.assertEqual(self.adjust_api(charge.id).status_code, 201)

    def test_adjust_an_adjustment_refused(self):
        charge = self._aged_charge()
        self.adjust_api(charge.id)
        adj = self.age_charge(FolioCharge.objects.get(folio_id=self.fid, adjusts=charge))
        r = self.adjust_api(adj.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_finance_operation")

    def test_voided_charge_cannot_be_adjusted(self):
        self.add_charge(self.fid, unit_amount="10.00")
        charge = FolioCharge.objects.get(folio_id=self.fid)
        self.void_charge_api(charge.id)
        self.age_charge(charge)
        r = self.adjust_api(charge.id)
        self.assertEqual(r.status_code, 400)

    def test_adjust_permission_enforced(self):
        charge = self._aged_charge()
        staff = add_member(self.hotel, "s@x.com", perms=["finance.view", "finance.charge_void"])
        self.client.force_authenticate(staff)
        self.assertEqual(self.adjust_api(charge.id).status_code, 403)
        staff2 = add_member(self.hotel, "s2@x.com", perms=["finance.adjust"])
        self.client.force_authenticate(staff2)
        self.assertEqual(self.adjust_api(charge.id).status_code, 201)

    def test_adjust_cross_hotel_isolated(self):
        charge = self._aged_charge()
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        om = User.objects.get(email="om@x.com")
        self.client.force_authenticate(om)
        self.assertEqual(self.adjust_api(charge.id, hotel=other).status_code, 404)


class PaymentReversalTests(APITestCase, ClosureMixin):
    """Full linked counter-payment once the void window has passed."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(self.fid, unit_amount="300.00")

    def _aged_payment(self, amount="100.00"):
        self.add_payment(self.fid, amount=amount)
        return self.age_payment(
            Payment.objects.filter(folio_id=self.fid).latest("id")
        )

    def test_reverse_requires_reason(self):
        payment = self._aged_payment()
        r = self.client.post(
            reverse("finance:payment-reverse", args=[payment.id]), {},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)

    def test_reverse_same_day_refused_use_void(self):
        self.add_payment(self.fid, amount="10.00")
        payment = Payment.objects.filter(folio_id=self.fid).latest("id")
        r = self.reverse_api(payment.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "void_window_open")

    def test_reverse_links_and_negates_full_amount(self):
        payment = self._aged_payment()
        r = self.reverse_api(payment.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["payment"]["amount"], "-100.00")
        self.assertEqual(r.data["payment"]["reverses"], payment.id)
        reversal = Payment.objects.get(reverses=payment)
        self.assertEqual(reversal.amount, -payment.amount)
        self.assertEqual(reversal.business_date, self.bd())
        self.assertEqual(reversal.method, payment.method)
        self.assertTrue(reversal.receipt_number.startswith("RCP"))
        payment.refresh_from_db()
        self.assertEqual(payment.status, PostingStatus.POSTED)
        folio = self.client.get(
            reverse("finance:folio-detail", args=[self.fid]), **HDR(self.hotel)
        ).data
        self.assertEqual(folio["balance"]["total_payments"], "0.00")

    def test_reverse_twice_refused(self):
        payment = self._aged_payment()
        self.assertEqual(self.reverse_api(payment.id).status_code, 201)
        r = self.reverse_api(payment.id)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "payment_already_reversed")

    def test_reverse_a_reversal_refused(self):
        payment = self._aged_payment()
        self.reverse_api(payment.id)
        reversal = self.age_payment(Payment.objects.get(reverses=payment))
        r = self.reverse_api(reversal.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_finance_operation")

    def test_voided_payment_cannot_be_reversed(self):
        self.add_payment(self.fid, amount="10.00")
        payment = Payment.objects.filter(folio_id=self.fid).latest("id")
        self.void_payment_api(payment.id)
        self.age_payment(payment)
        r = self.reverse_api(payment.id)
        self.assertEqual(r.status_code, 400)

    def test_reverse_permission_enforced(self):
        payment = self._aged_payment()
        staff = add_member(self.hotel, "s@x.com", perms=["finance.view", "finance.payment_void"])
        self.client.force_authenticate(staff)
        self.assertEqual(self.reverse_api(payment.id).status_code, 403)
        staff2 = add_member(self.hotel, "s2@x.com", perms=["finance.payment_reverse"])
        self.client.force_authenticate(staff2)
        self.assertEqual(self.reverse_api(payment.id).status_code, 201)

    def test_reverse_cross_hotel_isolated(self):
        payment = self._aged_payment()
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        om = User.objects.get(email="om@x.com")
        self.client.force_authenticate(om)
        self.assertEqual(self.reverse_api(payment.id, hotel=other).status_code, 404)


class StayFolioRuleTests(APITestCase, ClosureMixin):
    """ONE open folio per stay: service guard + DB backstop + idempotency."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.guest = Guest.objects.create(hotel=self.hotel, full_name="G One")
        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        rtype = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD", base_capacity=2, max_capacity=2
        )
        room = Room.objects.create(
            hotel=self.hotel, floor=floor, room_type=rtype, number="101"
        )
        from django.utils import timezone as dj_tz

        self.stay = Stay.objects.create(
            hotel=self.hotel, room=room, primary_guest=self.guest,
            planned_check_in_date=self.bd(),
            planned_check_out_date=self.bd() + timedelta(days=2),
            actual_check_in_at=dj_tz.now(),
        )

    def test_service_level_duplicate_open_folio_refused(self):
        fin.create_folio(self.hotel, stay=self.stay, guest=self.guest)
        from apps.common.exceptions import InvalidFinanceOperation

        with self.assertRaises(InvalidFinanceOperation):
            fin.create_folio(self.hotel, stay=self.stay, guest=self.guest)

    def test_ensure_stay_folio_idempotent(self):
        first = fin.ensure_stay_folio(self.stay)
        second = fin.ensure_stay_folio(self.stay)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            Folio.objects.filter(stay=self.stay, status=FolioStatus.OPEN).count(), 1
        )

    def test_db_constraint_backstop(self):
        fin.ensure_stay_folio(self.stay)
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                Folio.objects.create(
                    hotel=self.hotel, stay=self.stay, folio_number="FOLX9999",
                    currency="USD",
                )

    def test_new_open_folio_allowed_after_close(self):
        first = fin.ensure_stay_folio(self.stay)
        fin.close_folio(first)  # zero balance
        second = fin.ensure_stay_folio(self.stay)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(Folio.objects.filter(stay=self.stay).count(), 2)

    def test_reservation_without_stay_refused_service_and_api(self):
        from apps.common.exceptions import ReservationFolioNotSupported
        from apps.reservations.models import Reservation, ReservationStatus

        res = Reservation.objects.create(
            hotel=self.hotel, reservation_number="R99001",
            status=ReservationStatus.CONFIRMED,
            check_in_date=self.bd(), check_out_date=self.bd() + timedelta(days=1),
            primary_guest_name="X",
        )
        with self.assertRaises(ReservationFolioNotSupported):
            fin.create_folio(self.hotel, reservation=res)
        r = self.client.post(
            reverse("finance:folio-list"), {"reservation": res.id},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "reservation_folio_not_supported")

    def test_reservation_with_stay_link_allowed(self):
        from apps.reservations.models import Reservation, ReservationStatus

        res = Reservation.objects.create(
            hotel=self.hotel, reservation_number="R99002",
            status=ReservationStatus.CONFIRMED,
            check_in_date=self.bd(), check_out_date=self.bd() + timedelta(days=1),
            primary_guest_name="X",
        )
        folio = fin.create_folio(
            self.hotel, reservation=res, stay=self.stay, guest=self.guest
        )
        self.assertEqual(folio.reservation_id, res.id)


class CurrencyRuleTests(APITestCase, ClosureMixin):
    """Folio currency is ALWAYS the hotel currency; no cross-currency sums."""

    def setUp(self):
        self.hotel = make_hotel()
        HotelSettings.objects.create(hotel=self.hotel, default_currency="SAR")
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)

    def test_folio_currency_forced_to_hotel_currency(self):
        r = self.create_folio(customer_name="A")
        self.assertEqual(r.data["currency"], "SAR")

    def test_service_ignores_passed_currency(self):
        folio = fin.create_folio(self.hotel, customer_name="B", currency="EUR")
        self.assertEqual(folio.currency, "SAR")

    def test_payment_inherits_folio_currency(self):
        fid = self.create_folio(customer_name="C").data["id"]
        self.add_charge(fid, unit_amount="10.00")
        r = self.add_payment(fid, amount="10.00")
        self.assertEqual(r.data["payment"]["currency"], "SAR")

    def test_overview_flags_foreign_currency_folios_separately(self):
        fid = self.create_folio(customer_name="D").data["id"]
        self.add_charge(fid, unit_amount="70.00")
        legacy = fin.create_folio(self.hotel, customer_name="Legacy")
        Folio.objects.filter(pk=legacy.pk).update(currency="EUR")
        fin.add_charge(
            legacy, charge_type="service", description="legacy", quantity=1,
            unit_amount="999.00",
        )
        ov = self.client.get(reverse("finance:overview"), **HDR(self.hotel)).data
        self.assertEqual(ov["currency"], "SAR")
        self.assertEqual(ov["outstanding_balance"], "70.00")  # EUR excluded
        self.assertEqual(ov["foreign_currency_folios"]["count"], 1)
        self.assertEqual(ov["foreign_currency_folios"]["currencies"], ["EUR"])


class ActiveInvoiceTests(APITestCase, ClosureMixin):
    """ONE issued (non-voided) invoice per folio."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(self.fid, unit_amount="100.00")

    def _issue_new(self):
        iid = self.client.post(
            reverse("finance:folio-invoice-create", args=[self.fid]), {},
            format="json", **HDR(self.hotel),
        ).data["id"]
        return iid, self.client.post(
            reverse("finance:invoice-issue", args=[iid]), {}, format="json",
            **HDR(self.hotel),
        )

    def test_second_issue_refused_while_first_active(self):
        _, first = self._issue_new()
        self.assertEqual(first.status_code, 200)
        _, second = self._issue_new()
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data["code"], "active_invoice_exists")

    def test_issue_allowed_after_void(self):
        iid, _ = self._issue_new()
        self.client.post(
            reverse("finance:invoice-void", args=[iid]), {"reason": "reissue"},
            format="json", **HDR(self.hotel),
        )
        _, second = self._issue_new()
        self.assertEqual(second.status_code, 200)


class FolioStatementTests(APITestCase, ClosureMixin):
    """The print-friendly operational statement — reprintable even closed."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="Alice").data["id"]
        self.add_charge(self.fid, unit_amount="100.00")
        self.add_payment(self.fid, amount="40.00")

    def _statement(self, fid=None):
        return self.client.get(
            reverse("finance:folio-statement", args=[fid or self.fid]),
            **HDR(self.hotel),
        )

    def test_statement_structure(self):
        r = self._statement()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["document"], "statement")
        self.assertIn("hotel_name", r.data["hotel"])
        folio = r.data["folio"]
        self.assertEqual(len(folio["charges"]), 1)
        self.assertEqual(len(folio["payments"]), 1)
        self.assertEqual(folio["balance"]["balance"], "60.00")

    def test_statement_shows_adjustment_and_reversal_links(self):
        charge = self.age_charge(FolioCharge.objects.get(folio_id=self.fid))
        payment = self.age_payment(Payment.objects.get(folio_id=self.fid))
        self.adjust_api(charge.id)
        self.reverse_api(payment.id)
        folio = self._statement().data["folio"]
        adj = next(c for c in folio["charges"] if c["adjusts"] == charge.id)
        self.assertEqual(adj["adjusts_number"], charge.charge_number)
        rev = next(p for p in folio["payments"] if p["reverses"] == payment.id)
        self.assertEqual(rev["reverses_receipt"], payment.receipt_number)

    def test_closed_folio_statement_reprintable(self):
        self.add_payment(self.fid, amount="60.00")
        self.assertEqual(self.close_folio_api(self.fid).status_code, 200)
        r = self._statement()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["folio"]["status"], "closed")

    def test_statement_requires_view_permission(self):
        staff = add_member(self.hotel, "s@x.com")
        self.client.force_authenticate(staff)
        self.assertEqual(self._statement().status_code, 403)
        staff2 = add_member(self.hotel, "s2@x.com", perms=["finance.view"])
        self.client.force_authenticate(staff2)
        self.assertEqual(self._statement().status_code, 200)


class FinanceActivityTests(APITestCase, ClosureMixin):
    """Every sensitive money move shows up in the activity feed."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)

    def _types(self):
        return set(
            ActivityEvent.objects.filter(hotel=self.hotel).values_list(
                "event_type", flat=True
            )
        )

    def test_lifecycle_events_recorded(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="100.00")
        charge = FolioCharge.objects.get(folio_id=fid)
        self.add_payment(fid, amount="100.00")
        payment = Payment.objects.get(folio_id=fid)
        aged_c = self.age_charge(charge)
        aged_p = self.age_payment(payment)
        self.adjust_api(aged_c.id)
        self.reverse_api(aged_p.id)
        # settle back to zero and close (adjustment -100 and reversal -100 cancel)
        self.close_folio_api(fid)
        fid2 = self.create_folio(customer_name="B").data["id"]
        self.void_folio_api(fid2)
        fid3 = self.create_folio(customer_name="C").data["id"]
        self.add_charge(fid3, unit_amount="10.00")
        c3 = FolioCharge.objects.filter(folio_id=fid3).latest("id")
        self.void_charge_api(c3.id)
        self.add_charge(fid3, unit_amount="20.00")
        iid = self.client.post(
            reverse("finance:folio-invoice-create", args=[fid3]), {},
            format="json", **HDR(self.hotel),
        ).data["id"]
        self.client.post(
            reverse("finance:invoice-issue", args=[iid]), {}, format="json",
            **HDR(self.hotel),
        )
        self.client.post(
            reverse("finance:invoice-void", args=[iid]), {"reason": "reissue"},
            format="json", **HDR(self.hotel),
        )
        self.add_payment(fid3, amount="5.00")
        p3 = Payment.objects.filter(folio_id=fid3).latest("id")
        self.void_payment_api(p3.id)
        expected = {
            "folio.created", "folio.closed", "folio.voided",
            "charge.posted", "charge.voided", "charge.adjusted",
            "payment.recorded", "payment.voided", "payment.reversed",
            "invoice.issued", "invoice.voided",
        }
        self.assertTrue(expected.issubset(self._types()),
                        expected - self._types())

    def test_sensitive_events_carry_reason(self):
        fid = self.create_folio(customer_name="A").data["id"]
        self.add_charge(fid, unit_amount="10.00")
        charge = FolioCharge.objects.get(folio_id=fid)
        self.void_charge_api(charge.id, reason="typo in amount")
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="charge.voided"
        ).latest("id")
        self.assertIn("typo in amount", event.message)


# --------------------------------------------------------------------------- #
# Expenses final closure round                                                 #
# --------------------------------------------------------------------------- #

from django.utils import timezone

from apps.finance.models import Expense as ExpenseModel


class ExpensesClosureBase(APITestCase, ClosureMixin):
    def setUp(self):
        self.hotel = make_hotel()
        HotelSettings.objects.create(hotel=self.hotel, default_currency="SAR")
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE)
        self.client.force_authenticate(self.manager)
        # EXPENSES-CLOSURE: a manageable per-hotel ExpenseType is the source of
        # truth for new expenses (replaces the fixed ``category`` enum). The id is
        # posted as ``expense_type=<id>`` by ``create_exp``.
        self.expense_type = self.new_type("Supplies")

    def new_type(self, name):
        r = self.client.post(
            reverse("finance:expense-type-list"), {"name": name},
            format="json", **HDR(self.hotel),
        )
        assert r.status_code == 201, r.data
        return r.data["id"]

    def create_exp(self, **body):
        body.setdefault("expense_type", self.expense_type)
        body.setdefault("description", "Towels")
        body.setdefault("amount", "80.00")
        body.setdefault("method", "cash")
        return self.client.post(
            reverse("finance:expense-list"), body, format="json", **HDR(self.hotel)
        )

    def patch_exp(self, eid, **body):
        return self.client.patch(
            reverse("finance:expense-detail", args=[eid]), body, format="json",
            **HDR(self.hotel),
        )

    def void_exp(self, eid, reason="mistake"):
        return self.client.post(
            reverse("finance:expense-void", args=[eid]), {"reason": reason},
            format="json", **HDR(self.hotel),
        )

    def reverse_exp(self, eid, reason="late correction", hotel=None):
        return self.client.post(
            reverse("finance:expense-reverse", args=[eid]), {"reason": reason},
            format="json", **HDR(hotel or self.hotel),
        )

    def age_exp(self, eid, days=1):
        ExpenseModel.objects.filter(pk=eid).update(
            business_date=self.bd() - timedelta(days=days)
        )


class ExpenseStampingTests(ExpensesClosureBase):
    def test_business_date_and_paid_at_stamped_by_backend(self):
        res = self.create_exp()
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["business_date"], str(self.bd()))
        self.assertIsNotNone(res.data["paid_at"])
        self.assertEqual(res.data["currency"], "SAR")

    def test_client_paid_at_and_business_date_rejected(self):
        # EXPENSES-CLOSURE: ``currency`` is now a VALID entry-currency input (see
        # ExpenseFXTests); only the backend-decided timestamp/financial date are
        # refused outright by the create serializer.
        for payload in (
            {"paid_at": "2020-01-01T00:00:00Z"},
            {"business_date": "2020-01-01"},
        ):
            res = self.create_exp(**payload)
            self.assertEqual(res.status_code, 400, payload)

    def test_create_refused_on_closed_business_day(self):
        self.close_day()
        res = self.create_exp()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "business_day_closed")

    def test_cash_expense_joins_open_shift(self):
        from apps.shifts.services import open_shift, shift_cash_summary

        shift = open_shift(self.hotel, user=self.manager, opening_cash_amount="100.00")
        self.create_exp(amount="20.00")
        summary = shift_cash_summary(shift)
        self.assertEqual(str(summary["expected_cash"]), "80.00")


class ExpensePatchGuardTests(ExpensesClosureBase):
    """EXPENSES-CLOSURE FLIP: the atomic financial edit now lets money AND
    classification change (amount / method / expense_type / currency + FX) inside
    the voucher's own open business date, recording a before→after activity diff.
    The truly immutable fields (paid_at / business_date / shift / status / reverses
    / hotel / category) are STILL rejected outright."""

    def setUp(self):
        super().setUp()
        self.eid = self.create_exp().data["id"]

    def test_descriptive_fields_editable_same_day_with_activity_diff(self):
        res = self.patch_exp(self.eid, description="Bath towels", notes="urgent")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["description"], "Bath towels")
        self.assertEqual(res.data["notes"], "urgent")
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="expense.updated"
        ).latest("id")
        self.assertIn("Towels", event.message)       # old value
        self.assertIn("Bath towels", event.message)  # new value

    def test_money_and_classification_editable_with_activity_diff(self):
        other_type = self.new_type("Maintenance")
        res = self.patch_exp(
            self.eid, amount="15.00", method="electronic", expense_type=other_type,
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["amount"], "15.00")
        self.assertEqual(res.data["method"], "electronic")
        self.assertEqual(res.data["expense_type"], other_type)
        self.assertEqual(res.data["expense_type_name"], "Maintenance")
        event = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="expense.updated"
        ).latest("id")
        # The diff carries the old and new money values.
        self.assertIn("80.00", event.message)
        self.assertIn("15.00", event.message)

    def test_no_activity_when_nothing_changes(self):
        before = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="expense.updated"
        ).count()
        res = self.patch_exp(self.eid, description="Towels")
        self.assertEqual(res.status_code, 200)
        after = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="expense.updated"
        ).count()
        self.assertEqual(before, after)

    def test_immutable_fields_rejected(self):
        original_category = ExpenseModel.objects.get(pk=self.eid).category
        for payload in (
            {"category": "salary"}, {"paid_at": "2020-01-01T00:00:00Z"},
            {"business_date": "2020-01-01"}, {"shift": 1}, {"status": "voided"},
            {"reverses": 1}, {"hotel": 999},
        ):
            res = self.patch_exp(self.eid, **payload)
            self.assertEqual(res.status_code, 400, payload)
        expense = ExpenseModel.objects.get(pk=self.eid)
        self.assertEqual(str(expense.amount), "80.00")
        self.assertEqual(expense.category, original_category)

    def test_edit_refused_after_record_day_passed(self):
        self.age_exp(self.eid)
        res = self.patch_exp(self.eid, description="late edit")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "void_window_closed")

    def test_edit_refused_after_day_closed(self):
        self.close_day()
        res = self.patch_exp(self.eid, description="late edit")
        self.assertEqual(res.status_code, 409)

    def test_edit_refused_on_voided(self):
        self.void_exp(self.eid)
        res = self.patch_exp(self.eid, description="zombie")
        self.assertEqual(res.status_code, 400)


class ExpenseVoidWindowTests(ExpensesClosureBase):
    def test_same_day_void_ok(self):
        eid = self.create_exp().data["id"]
        res = self.void_exp(eid)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "voided")

    def test_void_refused_after_record_day_passed(self):
        eid = self.create_exp().data["id"]
        self.age_exp(eid)
        res = self.void_exp(eid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "void_window_closed")

    def test_void_refused_after_day_closed(self):
        eid = self.create_exp().data["id"]
        self.close_day()
        res = self.void_exp(eid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "void_window_closed")

    def test_void_requires_reason(self):
        eid = self.create_exp().data["id"]
        res = self.client.post(
            reverse("finance:expense-void", args=[eid]), {}, format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 400)


class ExpenseReversalTests(ExpensesClosureBase):
    def _aged(self, **kw):
        eid = self.create_exp(**kw).data["id"]
        self.age_exp(eid)
        return eid

    def test_reverse_full_linked_negative(self):
        eid = self._aged(amount="80.00")
        res = self.reverse_exp(eid)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["amount"], "-80.00")
        self.assertEqual(res.data["reverses"], eid)
        self.assertEqual(res.data["business_date"], str(self.bd()))
        # The counter-voucher copies the original's expense_type (classification).
        self.assertEqual(res.data["expense_type"], self.expense_type)
        self.assertEqual(res.data["expense_type_name"], "Supplies")
        original = ExpenseModel.objects.get(pk=eid)
        self.assertEqual(original.status, "posted")

    def test_reverse_refused_while_void_window_open(self):
        eid = self.create_exp().data["id"]
        res = self.reverse_exp(eid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "void_window_open")

    def test_reverse_twice_refused(self):
        eid = self._aged()
        self.assertEqual(self.reverse_exp(eid).status_code, 201)
        res = self.reverse_exp(eid)
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "expense_already_reversed")

    def test_reverse_a_reversal_refused(self):
        eid = self._aged()
        rid = self.reverse_exp(eid).data["id"]
        self.age_exp(rid)
        res = self.reverse_exp(rid)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "invalid_finance_operation")

    def test_reverse_voided_refused(self):
        eid = self.create_exp().data["id"]
        self.void_exp(eid)
        self.age_exp(eid)
        res = self.reverse_exp(eid)
        self.assertEqual(res.status_code, 400)

    def test_void_reversal_same_day_then_corrected_reverse(self):
        eid = self._aged()
        rid = self.reverse_exp(eid).data["id"]
        self.assertEqual(self.void_exp(rid, reason="wrong reversal").status_code, 200)
        res = self.reverse_exp(eid, reason="corrected")
        self.assertEqual(res.status_code, 201)

    def test_reversal_joins_executor_shift_drawer(self):
        from apps.shifts.services import open_shift, shift_cash_summary

        eid = self._aged(amount="30.00", method="cash")
        shift = open_shift(self.hotel, user=self.manager, opening_cash_amount="50.00")
        self.reverse_exp(eid)
        summary = shift_cash_summary(shift)
        # Negative cash expense returns money to the drawer: 50 + 30.
        self.assertEqual(str(summary["expected_cash"]), "80.00")

    def test_reverse_permission_enforced(self):
        eid = self._aged()
        staff = add_member(self.hotel, "s@x.com",
                           perms=["expenses.view", "expenses.void", "expenses.create"])
        self.client.force_authenticate(staff)
        self.assertEqual(self.reverse_exp(eid).status_code, 403)
        rev = add_member(self.hotel, "r@x.com", perms=["expenses.reverse"])
        self.client.force_authenticate(rev)
        self.assertEqual(self.reverse_exp(eid).status_code, 201)

    def test_reverse_cross_hotel_isolated(self):
        eid = self._aged()
        other = make_hotel(slug="o")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        om = User.objects.get(email="om@x.com")
        self.client.force_authenticate(om)
        self.assertEqual(self.reverse_exp(eid, hotel=other).status_code, 404)

    def test_db_backstop_unique_posted_reversal(self):
        eid = self._aged()
        self.reverse_exp(eid)
        original = ExpenseModel.objects.get(pk=eid)
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                ExpenseModel.objects.create(
                    hotel=self.hotel, expense_number="EXPX9999",
                    expense_type=original.expense_type,
                    category="other", description="dup", amount=Decimal("-80.00"),
                    method="cash", paid_at=timezone.now(), reverses=original,
                )

    def test_db_backstop_amount_sign(self):
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                ExpenseModel.objects.create(
                    hotel=self.hotel, expense_number="EXPX9998",
                    expense_type_id=self.expense_type,
                    category="other", description="neg", amount=Decimal("-5.00"),
                    method="cash", paid_at=timezone.now(),
                )


class ExpenseDerivationTests(ExpensesClosureBase):
    def test_overview_and_voucher_and_events(self):
        eid = self.create_exp(amount="70.00").data["id"]
        ov = self.client.get(reverse("finance:overview"), **HDR(self.hotel)).data
        self.assertEqual(ov["expenses_today"], "70.00")
        voucher = self.client.get(
            reverse("finance:expense-voucher", args=[eid]), **HDR(self.hotel)
        ).data
        self.assertEqual(voucher["expense"]["business_date"], str(self.bd()))
        self.assertEqual(voucher["expense"]["status"], "posted")
        # Reversal cross-references appear on both documents.
        self.age_exp(eid)
        rid = self.reverse_exp(eid).data["id"]
        v_orig = self.client.get(
            reverse("finance:expense-voucher", args=[eid]), **HDR(self.hotel)
        ).data["expense"]
        v_rev = self.client.get(
            reverse("finance:expense-voucher", args=[rid]), **HDR(self.hotel)
        ).data["expense"]
        self.assertEqual(v_orig["reversed_by_number"], v_rev["expense_number"])
        self.assertEqual(v_rev["reverses_number"], v_orig["expense_number"])
        types = set(
            ActivityEvent.objects.filter(hotel=self.hotel).values_list(
                "event_type", flat=True
            )
        )
        self.assertTrue({"expense.created", "expense.reversed"}.issubset(types))

    def test_legacy_fallback_paid_at_date(self):
        legacy = ExpenseModel.objects.create(
            hotel=self.hotel, expense_number="EXPLEG01",
            expense_type_id=self.expense_type, category="other",
            description="legacy", amount=Decimal("11.00"), method="cash",
            paid_at=timezone.now(), business_date=None,
        )
        ov = self.client.get(reverse("finance:overview"), **HDR(self.hotel)).data
        self.assertEqual(ov["expenses_today"], "11.00")
        from apps.shifts.services import unassigned_movements

        rep = unassigned_movements(self.hotel, self.bd())
        self.assertEqual(rep["expenses_total"], "11.00")

    def test_date_filter_on_business_date(self):
        self.create_exp(amount="5.00")
        res = self.client.get(
            reverse("finance:expense-list"),
            {"date_from": str(self.bd()), "date_to": str(self.bd())},
            **HDR(self.hotel),
        )
        self.assertEqual(res.data["count"], 1)


# --------------------------------------------------------------------------- #
# EXPENSES-CLOSURE — new coverage (idempotency, FX, types, permissions,        #
# tenant isolation, atomic edit, attachment, migration/backfill)               #
# --------------------------------------------------------------------------- #

import importlib
import uuid
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

# A real, minimal 1x1 PNG (valid signature + IHDR + IDAT + IEND) — enough to
# pass the extension + content-type + size + magic-byte signature checks.
_PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _rows(response):
    """List responses may be paginated ({count, results}) or a bare list."""
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


class ExpenseIdempotencyTests(ExpensesClosureBase):
    """Strong creation idempotency: same key + same salient body → the SAME
    voucher (one row); same key + materially different body → 409."""

    def test_same_key_same_body_returns_same_row(self):
        r1 = self.create_exp(amount="10.00", idempotency_key="k1")
        r2 = self.create_exp(amount="10.00", idempotency_key="k1")
        self.assertEqual(r1.status_code, 201, r1.data)
        self.assertEqual(r2.status_code, 201, r2.data)
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(ExpenseModel.objects.filter(hotel=self.hotel).count(), 1)

    def test_same_key_different_body_conflict(self):
        self.create_exp(amount="10.00", idempotency_key="k2")
        r = self.create_exp(amount="99.00", idempotency_key="k2")
        self.assertEqual(r.status_code, 409, r.data)
        self.assertEqual(r.data["code"], "idempotency_key_conflict")
        self.assertEqual(ExpenseModel.objects.filter(hotel=self.hotel).count(), 1)

    def test_distinct_keys_create_distinct_rows(self):
        self.create_exp(amount="10.00", idempotency_key="a")
        self.create_exp(amount="10.00", idempotency_key="b")
        self.assertEqual(ExpenseModel.objects.filter(hotel=self.hotel).count(), 2)

    def test_no_key_always_creates(self):
        self.create_exp(amount="10.00")
        self.create_exp(amount="10.00")
        self.assertEqual(ExpenseModel.objects.filter(hotel=self.hotel).count(), 2)


class ExpenseFXTests(ExpensesClosureBase):
    """Multi-currency FX (mirrors payments). Base currency stores no rate; a
    foreign entry derives base = original × rate (ROUND_HALF_UP); a non-accepted
    currency or a foreign entry missing the rate/original is a clean 400."""

    def setUp(self):
        super().setUp()
        s = self.hotel.settings
        s.accepted_currencies = ["USD"]
        s.save(update_fields=["accepted_currencies"])

    def test_base_currency_stores_no_rate(self):
        r = self.create_exp(amount="80.00")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["amount"], "80.00")
        self.assertEqual(r.data["currency"], "SAR")
        self.assertIsNone(r.data["exchange_rate"])

    def test_explicit_base_currency_stores_no_rate(self):
        r = self.create_exp(currency="SAR", amount="50.00")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(r.data["exchange_rate"])
        self.assertEqual(r.data["original_currency"], "SAR")

    def test_foreign_base_is_original_times_rate(self):
        r = self.create_exp(
            currency="USD", original_amount="20.00", exchange_rate="3.75",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["amount"], "75.00")
        self.assertEqual(r.data["currency"], "SAR")
        self.assertEqual(r.data["original_currency"], "USD")
        self.assertEqual(r.data["original_amount"], "20.00")
        self.assertEqual(r.data["exchange_rate"], "3.75000000")

    def test_foreign_rounds_half_up(self):
        # 1.00 * 2.125 = 2.125 -> ROUND_HALF_UP at 2 dp = 2.13 (HALF_EVEN = 2.12).
        r = self.create_exp(
            currency="USD", original_amount="1.00", exchange_rate="2.125",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["amount"], "2.13")

    def test_non_accepted_currency_rejected(self):
        r = self.create_exp(
            currency="EUR", original_amount="5.00", exchange_rate="4.00",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_finance_operation")

    def test_foreign_missing_rate_rejected(self):
        r = self.create_exp(currency="USD", original_amount="10.00")
        self.assertEqual(r.status_code, 400, r.data)

    def test_foreign_missing_original_rejected(self):
        r = self.create_exp(currency="USD", exchange_rate="3.75")
        self.assertEqual(r.status_code, 400, r.data)


class ExpenseAmountTests(ExpensesClosureBase):
    """A zero OR negative base amount is refused through the API."""

    def test_zero_amount_rejected(self):
        r = self.create_exp(amount="0.00")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_amount")

    def test_negative_amount_rejected(self):
        r = self.create_exp(amount="-5.00")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_amount")


class ExpenseTypeManagementTests(ExpensesClosureBase):
    """Manageable per-hotel expense types: create/rename/(de)activate, normalized
    uniqueness, active-only on create, inactive hidden from create but kept on
    history, and tenant isolation on list/detail."""

    def _list(self, all_=False):
        params = {"all": "1"} if all_ else {}
        return self.client.get(
            reverse("finance:expense-type-list"), params, **HDR(self.hotel)
        )

    def _type_ids(self, all_=False):
        return [t["id"] for t in _rows(self._list(all_))]

    def _patch(self, tid, **body):
        return self.client.patch(
            reverse("finance:expense-type-detail", args=[tid]), body,
            format="json", **HDR(self.hotel),
        )

    def test_create_type(self):
        r = self.client.post(
            reverse("finance:expense-type-list"), {"name": "Utilities"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["name"], "Utilities")
        self.assertTrue(r.data["is_active"])

    def test_duplicate_normalized_name_rejected(self):
        # ``Supplies`` already exists (base setUp); case/space variants collide.
        for name in ("Supplies", "  supplies ", "SUPPLIES"):
            r = self.client.post(
                reverse("finance:expense-type-list"), {"name": name},
                format="json", **HDR(self.hotel),
            )
            self.assertEqual(r.status_code, 400, (name, r.data))

    def test_rename_type(self):
        r = self._patch(self.expense_type, name="Cleaning Supplies")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["name"], "Cleaning Supplies")

    def test_deactivate_hides_from_create_but_keeps_history(self):
        eid = self.create_exp().data["id"]  # posted under the active type
        r = self._patch(self.expense_type, is_active=False)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["is_active"])
        # A NEW expense can no longer be filed under a retired type.
        create = self.create_exp()
        self.assertEqual(create.status_code, 400, create.data)
        # But the historical voucher still shows the (now inactive) type name.
        detail = self.client.get(
            reverse("finance:expense-detail", args=[eid]), **HDR(self.hotel)
        ).data
        self.assertEqual(detail["expense_type_name"], "Supplies")

    def test_inactive_hidden_from_default_list_visible_with_all(self):
        self._patch(self.expense_type, is_active=False)
        self.assertNotIn(self.expense_type, self._type_ids())
        self.assertIn(self.expense_type, self._type_ids(all_=True))

    def test_all_flag_ignored_without_manage_types(self):
        self._patch(self.expense_type, is_active=False)
        staff = add_member(self.hotel, "vv@x.com", perms=["expenses.view"])
        self.client.force_authenticate(staff)
        self.assertNotIn(self.expense_type, self._type_ids(all_=True))

    def test_foreign_hotel_type_on_create_rejected(self):
        other = make_hotel(slug="o")
        other_type = ExpenseType.objects.create(
            hotel=other, name="X", name_normalized="x"
        )
        r = self.create_exp(expense_type=other_type.id)
        self.assertEqual(r.status_code, 400, r.data)

    def test_type_list_is_tenant_scoped(self):
        other = make_hotel(slug="o")
        ExpenseType.objects.create(
            hotel=other, name="Foreign", name_normalized="foreign"
        )
        names = [t["name"] for t in _rows(self._list(all_=True))]
        self.assertNotIn("Foreign", names)

    def test_type_detail_cross_hotel_isolated(self):
        other = make_hotel(slug="o")
        other_type = ExpenseType.objects.create(
            hotel=other, name="Foreign", name_normalized="foreign"
        )
        self.assertEqual(self._patch(other_type.id, name="Hijack").status_code, 404)


class ExpensePermissionMatrixTests(ExpensesClosureBase):
    """Per-permission gating (positive + negative) for EACH of the six expense
    permission codes. A STAFF member holding ONLY the target code succeeds; a
    STAFF member holding a DIFFERENT single code is refused (403)."""

    def _staff(self, perms):
        user = add_member(self.hotel, f"{uuid.uuid4().hex[:10]}@x.com", perms=perms)
        self.client.force_authenticate(user)
        return user

    def _manager_expense(self, **body):
        self.client.force_authenticate(self.manager)
        return self.create_exp(**body).data["id"]

    def _post_create(self):
        return self.client.post(
            reverse("finance:expense-list"),
            {"expense_type": self.expense_type, "description": "X",
             "amount": "10.00", "method": "cash"},
            format="json", **HDR(self.hotel),
        )

    def _patch(self, eid):
        return self.client.patch(
            reverse("finance:expense-detail", args=[eid]),
            {"description": "edited"}, format="json", **HDR(self.hotel),
        )

    def test_view_permission(self):
        self._staff(["expenses.view"])
        self.assertEqual(
            self.client.get(reverse("finance:expense-list"), **HDR(self.hotel)).status_code, 200
        )
        self._staff(["expenses.create"])  # a different single code, not view
        self.assertEqual(
            self.client.get(reverse("finance:expense-list"), **HDR(self.hotel)).status_code, 403
        )

    def test_create_permission(self):
        self._staff(["expenses.create"])
        self.assertEqual(self._post_create().status_code, 201)
        self._staff(["expenses.view"])
        self.assertEqual(self._post_create().status_code, 403)

    def test_update_permission(self):
        eid = self._manager_expense()
        self._staff(["expenses.update"])
        self.assertEqual(self._patch(eid).status_code, 200)
        eid2 = self._manager_expense()
        self._staff(["expenses.view"])
        self.assertEqual(self._patch(eid2).status_code, 403)

    def test_void_permission(self):
        eid = self._manager_expense()
        self._staff(["expenses.void"])
        self.assertEqual(self.void_exp(eid).status_code, 200)
        eid2 = self._manager_expense()
        self._staff(["expenses.view"])
        self.assertEqual(self.void_exp(eid2).status_code, 403)

    def test_reverse_permission(self):
        eid = self._manager_expense()
        self.age_exp(eid)
        self._staff(["expenses.reverse"])
        self.assertEqual(self.reverse_exp(eid).status_code, 201)
        eid2 = self._manager_expense()
        self.age_exp(eid2)
        self._staff(["expenses.view"])
        self.assertEqual(self.reverse_exp(eid2).status_code, 403)

    def test_manage_types_permission(self):
        self._staff(["expenses.manage_types"])
        r = self.client.post(
            reverse("finance:expense-type-list"), {"name": "New Type"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 201, r.data)
        self._staff(["expenses.view"])
        r2 = self.client.post(
            reverse("finance:expense-type-list"), {"name": "Another"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r2.status_code, 403)


class ExpenseTenantIsolationTests(ExpensesClosureBase):
    """A foreign-hotel object id is a 404 on EVERY expense endpoint — list,
    detail GET/PATCH, void, reverse, voucher, attachment upload/url/stream, and
    type list/detail."""

    def setUp(self):
        super().setUp()
        self.other = make_hotel(slug="other")
        HotelSettings.objects.create(hotel=self.other, default_currency="SAR")
        self.other_type = ExpenseType.objects.create(
            hotel=self.other, name="Foreign", name_normalized="foreign"
        )
        self.other_exp = ExpenseModel.objects.create(
            hotel=self.other, expense_number="EXPF0001",
            expense_type=self.other_type, description="foreign",
            amount=Decimal("9.00"), currency="SAR", method="cash",
            paid_at=timezone.now(), business_date=self.bd(),
            attachment=SimpleUploadedFile(
                "r.png", _PNG_1x1, content_type="image/png"
            ),
        )
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        try:
            if self.other_exp.attachment:
                self.other_exp.attachment.delete(save=False)
        except Exception:  # pragma: no cover - best-effort disk cleanup
            pass

    @property
    def _pk(self):
        return self.other_exp.id

    def test_list_excludes_foreign(self):
        data = self.client.get(reverse("finance:expense-list"), **HDR(self.hotel)).data
        self.assertNotIn(self._pk, [e["id"] for e in _rows_from(data)])

    def test_detail_get_foreign_404(self):
        self.assertEqual(
            self.client.get(reverse("finance:expense-detail", args=[self._pk]), **HDR(self.hotel)).status_code, 404
        )

    def test_detail_patch_foreign_404(self):
        self.assertEqual(
            self.client.patch(
                reverse("finance:expense-detail", args=[self._pk]),
                {"description": "x"}, format="json", **HDR(self.hotel),
            ).status_code, 404
        )

    def test_void_foreign_404(self):
        self.assertEqual(
            self.client.post(
                reverse("finance:expense-void", args=[self._pk]),
                {"reason": "x"}, format="json", **HDR(self.hotel),
            ).status_code, 404
        )

    def test_reverse_foreign_404(self):
        self.assertEqual(
            self.client.post(
                reverse("finance:expense-reverse", args=[self._pk]),
                {"reason": "x"}, format="json", **HDR(self.hotel),
            ).status_code, 404
        )

    def test_voucher_foreign_404(self):
        self.assertEqual(
            self.client.get(reverse("finance:expense-voucher", args=[self._pk]), **HDR(self.hotel)).status_code, 404
        )

    def test_attachment_upload_foreign_404(self):
        upload = SimpleUploadedFile("r.png", _PNG_1x1, content_type="image/png")
        r = self.client.post(
            reverse("finance:expense-attachment", args=[self._pk]),
            {"file": upload}, format="multipart", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 404)

    def test_attachment_url_foreign_404(self):
        self.assertEqual(
            self.client.get(reverse("finance:expense-attachment-url", args=[self._pk]), **HDR(self.hotel)).status_code, 404
        )

    def test_attachment_stream_foreign_404(self):
        self.assertEqual(
            self.client.get(reverse("finance:expense-attachment-stream", args=[self._pk]), **HDR(self.hotel)).status_code, 404
        )

    def test_type_detail_foreign_404(self):
        self.assertEqual(
            self.client.patch(
                reverse("finance:expense-type-detail", args=[self.other_type.id]),
                {"name": "x"}, format="json", **HDR(self.hotel),
            ).status_code, 404
        )

    def test_type_list_excludes_foreign(self):
        data = self.client.get(
            reverse("finance:expense-type-list"), {"all": "1"}, **HDR(self.hotel)
        ).data
        self.assertNotIn("Foreign", [t["name"] for t in _rows_from(data)])


def _rows_from(data):
    return data["results"] if isinstance(data, dict) and "results" in data else data


class ExpenseAtomicEditTests(ExpensesClosureBase):
    """The atomic financial edit reverses the old effect and applies the new one
    within one transaction (the drawer/reports re-sum the new ``amount``); it is
    refused after the record's day passes/closes; a no-op writes nothing; a
    reversal row is never editable."""

    def test_amount_change_reflects_in_shift_drawer(self):
        from apps.shifts.services import open_shift, shift_cash_summary

        shift = open_shift(self.hotel, user=self.manager, opening_cash_amount="100.00")
        eid = self.create_exp(amount="20.00", method="cash").data["id"]
        self.assertEqual(str(shift_cash_summary(shift)["expected_cash"]), "80.00")
        r = self.patch_exp(eid, amount="50.00")
        self.assertEqual(r.status_code, 200, r.data)
        # 100 opening - 50 cash-out = 50 expected in the drawer.
        self.assertEqual(str(shift_cash_summary(shift)["expected_cash"]), "50.00")

    def test_currency_to_foreign_and_back(self):
        s = self.hotel.settings
        s.accepted_currencies = ["USD"]
        s.save(update_fields=["accepted_currencies"])
        eid = self.create_exp(amount="80.00").data["id"]
        r = self.patch_exp(
            eid, currency="USD", original_amount="20.00", exchange_rate="3.75",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["amount"], "75.00")
        self.assertEqual(r.data["original_currency"], "USD")
        self.assertEqual(r.data["exchange_rate"], "3.75000000")
        # ...and back to base clears the FX snapshot.
        r2 = self.patch_exp(eid, currency="SAR", amount="80.00")
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(r2.data["amount"], "80.00")
        self.assertEqual(r2.data["currency"], "SAR")
        self.assertIsNone(r2.data["exchange_rate"])
        self.assertEqual(r2.data["original_currency"], "SAR")

    def test_edit_refused_after_day_passed(self):
        eid = self.create_exp().data["id"]
        self.age_exp(eid)
        self.assertEqual(self.patch_exp(eid, amount="5.00").status_code, 409)

    def test_edit_refused_after_close(self):
        eid = self.create_exp().data["id"]
        self.close_day()
        self.assertEqual(self.patch_exp(eid, amount="5.00").status_code, 409)

    def test_no_op_edit_writes_nothing(self):
        eid = self.create_exp(amount="80.00").data["id"]
        before = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="expense.updated"
        ).count()
        stamp = ExpenseModel.objects.get(pk=eid).updated_at
        r = self.patch_exp(eid, amount="80.00", description="Towels")
        self.assertEqual(r.status_code, 200, r.data)
        after = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="expense.updated"
        ).count()
        self.assertEqual(before, after)
        self.assertEqual(ExpenseModel.objects.get(pk=eid).updated_at, stamp)

    def test_reversal_row_not_editable(self):
        eid = self.create_exp().data["id"]
        self.age_exp(eid)
        rid = self.reverse_exp(eid).data["id"]
        r = self.patch_exp(rid, description="edit reversal")
        self.assertEqual(r.status_code, 400, r.data)


class ExpenseAttachmentTests(ExpensesClosureBase):
    """ONE optional private receipt scan: valid PNG uploads; wrong-extension /
    oversize / spoofed-signature / SVG are 400 ``invalid_media_file``; replace
    deletes the old file; remove clears it; upload is refused after close; a
    signed-url token streams the bytes while a forged/expired token is 403."""

    def setUp(self):
        super().setUp()
        self.eid = self.create_exp().data["id"]
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        # Best-effort disk cleanup. This runs as an ``addCleanup`` hook, i.e.
        # AFTER the test's transaction/connection has been torn down — on
        # PostgreSQL the query itself raises "the connection is closed", and an
        # exception in a cleanup marks an otherwise-passing test as ERROR. So the
        # LOOKUP must be guarded too, not just the per-file delete.
        try:
            expenses = list(ExpenseModel.objects.filter(hotel=self.hotel))
        except Exception:  # pragma: no cover - connection already gone
            return
        for exp in expenses:
            try:
                if exp.attachment:
                    exp.attachment.delete(save=False)
            except Exception:  # pragma: no cover - best-effort disk cleanup
                pass

    def _upload(self, eid=None, name="receipt.png", data=None, content_type="image/png"):
        upload = SimpleUploadedFile(
            name, data if data is not None else _PNG_1x1, content_type=content_type
        )
        return self.client.post(
            reverse("finance:expense-attachment", args=[eid or self.eid]),
            {"file": upload}, format="multipart", **HDR(self.hotel),
        )

    def test_upload_png_sets_has_attachment(self):
        r = self._upload()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["has_attachment"])
        detail = self.client.get(
            reverse("finance:expense-detail", args=[self.eid]), **HDR(self.hotel)
        ).data
        self.assertTrue(detail["has_attachment"])

    def test_wrong_extension_rejected(self):
        r = self._upload(name="receipt.txt", content_type="text/plain")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_media_file")

    def test_spoofed_signature_rejected(self):
        # A ``.png`` name + image/png content type but NON-image bytes.
        r = self._upload(data=b"this is definitely not a real image", content_type="image/png")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_media_file")

    def test_svg_rejected(self):
        r = self._upload(
            name="logo.svg", data=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            content_type="image/svg+xml",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_media_file")

    @override_settings(EXPENSE_ATTACH_MAX_BYTES=8)
    def test_oversize_rejected(self):
        r = self._upload()  # _PNG_1x1 is well over 8 bytes
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(r.data["code"], "invalid_media_file")

    def test_replace_deletes_old_file(self):
        self._upload()
        exp = ExpenseModel.objects.get(pk=self.eid)
        old_name = exp.attachment.name
        storage = exp.attachment.storage
        self.assertTrue(storage.exists(old_name))
        # The physical delete of the REPLACED file is deferred to
        # ``transaction.on_commit`` (a filesystem delete must not happen inside a
        # transaction that can still roll back), so run the callbacks here.
        with self.captureOnCommitCallbacks(execute=True):
            self._upload()  # replace
        exp.refresh_from_db()
        new_name = exp.attachment.name
        self.assertNotEqual(old_name, new_name)
        self.assertFalse(storage.exists(old_name))
        self.assertTrue(storage.exists(new_name))

    def test_remove_clears_attachment(self):
        self._upload()
        exp = ExpenseModel.objects.get(pk=self.eid)
        name = exp.attachment.name
        storage = exp.attachment.storage
        # The physical delete is deferred to ``transaction.on_commit``.
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.delete(
                reverse("finance:expense-attachment", args=[self.eid]), **HDR(self.hotel)
            )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["has_attachment"])
        exp.refresh_from_db()
        self.assertFalse(bool(exp.attachment))
        self.assertFalse(storage.exists(name))

    def test_upload_refused_after_close(self):
        self.close_day()
        r = self._upload()
        self.assertEqual(r.status_code, 409, r.data)

    def test_stream_via_signed_url_token(self):
        self._upload()
        url = self.client.get(
            reverse("finance:expense-attachment-url", args=[self.eid]), **HDR(self.hotel)
        ).data["url"]
        token = parse_qs(urlparse(url).query)["token"][0]
        stream = reverse("finance:expense-attachment-stream", args=[self.eid])
        self.client.force_authenticate(None)  # the token alone authorizes
        resp = self.client.get(stream, {"token": token})
        self.assertEqual(resp.status_code, 200)
        content = b"".join(resp.streaming_content)
        # Do NOT call ``resp.close()``: closing a response fires Django's
        # ``request_finished`` signal, whose ``close_old_connections`` receiver
        # closes the DB connection — which destroys the transaction wrapping this
        # TestCase and makes EVERY later test in the class fail in setUp with
        # "the connection is closed". Release the file handle directly instead.
        handle = getattr(resp, "file_to_stream", None)
        if handle is not None:
            handle.close()
        self.assertEqual(content[:8], _PNG_1x1[:8])

    def test_forged_token_rejected(self):
        self._upload()
        stream = reverse("finance:expense-attachment-stream", args=[self.eid])
        self.client.force_authenticate(None)
        resp = self.client.get(stream, {"token": "forged.garbage.value"})
        self.assertEqual(resp.status_code, 403)

    def test_expired_token_rejected(self):
        self._upload()
        url = self.client.get(
            reverse("finance:expense-attachment-url", args=[self.eid]), **HDR(self.hotel)
        ).data["url"]
        token = parse_qs(urlparse(url).query)["token"][0]
        stream = reverse("finance:expense-attachment-stream", args=[self.eid])
        self.client.force_authenticate(None)
        with mock.patch(
            "apps.finance.expense_attachment_views.STREAM_TOKEN_MAX_AGE", -1
        ):
            resp = self.client.get(stream, {"token": token})
        self.assertEqual(resp.status_code, 403)


class ExpenseTypeBackfillMigrationTests(TransactionTestCase):
    """Data-integrity proof of the backfill chain (0011 nullable → 0012 seed +
    backfill → 0013 enforce NOT NULL): every legacy ``category`` row gains a
    matching non-null ``expense_type``, and 0013's guard refuses to enforce
    NOT NULL while any null remains."""

    migrate_from = ("finance", "0010_foliocharge_snapshots_and_wide_source")
    migrate_backfill = ("finance", "0012_expense_type_backfill")
    migrate_to = ("finance", "0013_expense_type_enforce")

    _LABELS = {
        "operations": "Operations", "maintenance": "Maintenance",
        "supplies": "Supplies", "marketing": "Marketing", "salary": "Salary",
        "utilities": "Utilities", "other": "Other",
    }

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        executor.loader.build_graph()

    def tearDown(self):
        # Restore the DB to the latest migration state for the rest of the suite.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _state(self, target):
        return MigrationExecutor(connection).loader.project_state([target]).apps

    def test_backfill_assigns_matching_type(self):
        old = self._state(self.migrate_from)
        Hotel = old.get_model("tenancy", "Hotel")
        Expense = old.get_model("finance", "Expense")
        hotel = Hotel.objects.create(name="H", slug="mig-hotel", status="active")
        created = {}
        for i, cat in enumerate(self._LABELS):
            e = Expense.objects.create(
                hotel=hotel, expense_number=f"EXP{i:05d}", category=cat,
                description=f"legacy {cat}", amount=Decimal("10.00"),
                method="cash", paid_at=timezone.now(),
            )
            created[e.id] = cat
        # A blank/unknown legacy category must fall to the "Other" type.
        blank = Expense.objects.create(
            hotel=hotel, expense_number="EXPBLANK", category="",
            description="blank", amount=Decimal("5.00"), method="cash",
            paid_at=timezone.now(),
        )
        created[blank.id] = ""

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])  # 0011 -> 0012 -> 0013

        new = self._state(self.migrate_to)
        Expense2 = new.get_model("finance", "Expense")
        for e in Expense2.objects.filter(hotel_id=hotel.id):
            self.assertIsNotNone(e.expense_type_id, e.expense_number)
            cat = created[e.id]
            expected = self._LABELS[cat] if cat in self._LABELS else "Other"
            self.assertEqual(e.expense_type.name, expected, e.expense_number)
        self.assertEqual(
            Expense2.objects.filter(hotel_id=hotel.id, expense_type__isnull=True).count(),
            0,
        )

    def test_enforce_guard_heals_late_rows_before_enforcing(self):
        """A row written AFTER 0012 — e.g. by the PREVIOUS release still serving
        traffic during a rolling deploy — is healed by 0013's guard (mapped from
        its legacy ``category``) instead of hard-failing the release. The guard
        still refuses to enforce if anything remains unassigned."""
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_backfill])  # 0011 + 0012 only
        state = self._state(self.migrate_backfill)
        Hotel = state.get_model("tenancy", "Hotel")
        Expense = state.get_model("finance", "Expense")
        hotel = Hotel.objects.create(name="H", slug="mig-guard", status="active")
        Expense.objects.create(
            hotel=hotel, expense_number="EXPNULL", category="utilities",
            description="late row", amount=Decimal("1.00"), method="cash",
            paid_at=timezone.now(), expense_type=None,
        )
        mod = importlib.import_module(
            "apps.finance.migrations.0013_expense_type_enforce"
        )
        with connection.schema_editor(atomic=False) as se:
            mod.heal_then_assert(state, se)  # heals, does NOT raise

        healed = Expense.objects.get(expense_number="EXPNULL")
        self.assertIsNotNone(healed.expense_type_id)
        self.assertEqual(healed.expense_type.name, "Utilities")
        # Nothing left unassigned, so NOT NULL can now be enforced safely.
        self.assertEqual(
            Expense.objects.filter(expense_type__isnull=True).count(), 0
        )


# --------------------------------------------------------------------------- #
# GUEST-FOLIO-EXTRA-SERVICES-CLOSURE (finance backend foundation)             #
# --------------------------------------------------------------------------- #

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.finance.constants import ChargeSource, SERVICE_LINE_SOURCES


class ChargeSourceConstantsTests(APITestCase):
    """PKG-CONST — a single source-of-truth for charge ``source`` values whose
    strings MUST equal what the code already stored (no data migration)."""

    def test_values_match_existing_source_strings(self):
        self.assertEqual(ChargeSource.MANUAL, "manual")
        self.assertEqual(ChargeSource.SERVICE_ORDER, "service_order")
        self.assertEqual(ChargeSource.STAY_ROOM, "stay_room")
        self.assertEqual(ChargeSource.ROOM_ACCOUNT, "room_account")
        self.assertEqual(ChargeSource.ADJUSTMENT, "adjustment")
        self.assertEqual(ChargeSource.GUEST_EXTRA_SERVICE, "guest_extra_service")

    def test_room_night_source_uses_the_constant(self):
        self.assertEqual(fin.ROOM_NIGHT_SOURCE, ChargeSource.STAY_ROOM)
        self.assertEqual(fin.ROOM_NIGHT_SOURCE, "stay_room")

    def test_service_line_sources_allowlist(self):
        self.assertEqual(
            set(SERVICE_LINE_SOURCES),
            {ChargeSource.GUEST_EXTRA_SERVICE, ChargeSource.SERVICE_ORDER},
        )
        # SOURCES, not ChargeType.SERVICE — a room-night / manual source is NOT
        # a service line even though ROOM/others exist.
        self.assertIn("service_order", SERVICE_LINE_SOURCES)
        self.assertIn("guest_extra_service", SERVICE_LINE_SOURCES)
        self.assertNotIn("manual", SERVICE_LINE_SOURCES)
        self.assertNotIn("stay_room", SERVICE_LINE_SOURCES)

    def test_add_charge_default_source_is_manual_constant(self):
        hotel = make_hotel()
        manager = add_member(
            hotel, "cs@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        folio = fin.create_folio(hotel, customer_name="A", user=manager)
        charge = fin.add_charge(
            folio, charge_type="service", description="X", quantity=1,
            unit_amount="10.00", user=manager,
        )
        self.assertEqual(charge.source, "manual")


class OverviewAggregationParityTests(APITestCase, ClosureMixin):
    """S1 — the finance-overview DB aggregation MUST return exactly what a
    per-folio ``folio_balance`` loop would, across composite folio states, and
    without ever summing different currencies together."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.client.force_authenticate(self.manager)

    def _folio(self, name, currency=None):
        folio = fin.create_folio(self.hotel, customer_name=name, user=self.manager)
        if currency:
            Folio.objects.filter(pk=folio.pk).update(currency=currency)
            folio.refresh_from_db()
        return folio

    def _charge(self, folio, amount, ctype="service"):
        return fin.add_charge(
            folio, charge_type=ctype, description="c", quantity=1,
            unit_amount=amount, user=self.manager,
        )

    def _pay(self, folio, amount):
        return fin.record_payment(
            folio, amount=amount, method="cash", user=self.manager
        )

    def _reference(self, base):
        """The oracle: iterate ``folio_balance`` exactly like the old loop."""
        open_folios = list(
            Folio.objects.filter(hotel=self.hotel, status=FolioStatus.OPEN)
        )
        base_folios = [f for f in open_folios if f.currency == base]
        outstanding = Decimal("0.00")
        unpaid = 0
        for f in base_folios:
            bal = fin.folio_balance(f)["balance"]
            outstanding += bal
            if bal > Decimal("0.00"):
                unpaid += 1
        foreign = [f for f in open_folios if f.currency != base]
        return {
            "outstanding": fin.money(outstanding),
            "unpaid": unpaid,
            "foreign_count": len(foreign),
            "foreign_currencies": sorted({f.currency for f in foreign}),
        }

    def test_parity_across_composite_states(self):
        # empty folio
        self._folio("empty")
        # charges-only
        self._charge(self._folio("charges"), "200.00")
        # payments-only (credit balance)
        self._pay(self._folio("payments"), "50.00")
        # charges + payments (partial)
        mix = self._folio("mix")
        self._charge(mix, "300.00")
        self._pay(mix, "120.00")
        # charge voided (same-day) -> excluded
        cv = self._folio("charge_void")
        voided = self._charge(cv, "999.00")
        self._charge(cv, "40.00")
        fin.void_charge(voided, reason="mistake", user=self.manager)
        # payment voided (same-day) -> excluded
        pv = self._folio("pay_void")
        self._charge(pv, "80.00")
        bad = self._pay(pv, "80.00")
        fin.void_payment(bad, reason="mistake", user=self.manager)
        # payment reversed (aged -> full counter-payment, both posted, net out)
        pr = self._folio("pay_reverse")
        self._charge(pr, "100.00")
        orig = self._pay(pr, "60.00")
        self.age_payment(orig)
        fin.reverse_payment(orig, reason="late correction", user=self.manager)
        # multi-currency foreign folio (excluded from the summed number)
        eur = self._folio("eur", currency="EUR")
        self._charge(eur, "500.00")
        gbp = self._folio("gbp", currency="GBP")
        self._charge(gbp, "10.00")

        base = "USD"
        expected = self._reference(base)
        agg = fin.aggregate_open_folio_balances(
            Folio.objects.filter(hotel=self.hotel, status=FolioStatus.OPEN),
            base_currency=base,
        )
        self.assertEqual(agg, expected)

        # And the HTTP overview surfaces the same numbers.
        ov = self.client.get(reverse("finance:overview"), **HDR(self.hotel)).data
        self.assertEqual(ov["outstanding_balance"], str(expected["outstanding"]))
        self.assertEqual(ov["unpaid_folios"], expected["unpaid"])
        self.assertEqual(
            ov["foreign_currency_folios"]["count"], expected["foreign_count"]
        )
        self.assertEqual(
            ov["foreign_currency_folios"]["currencies"],
            expected["foreign_currencies"],
        )

    def test_overview_query_count_constant_for_1_vs_n_folios(self):
        # One open folio with activity.
        f1 = self._folio("one")
        self._charge(f1, "100.00")
        self._pay(f1, "40.00")
        with CaptureQueriesContext(connection) as q1:
            self.client.get(reverse("finance:overview"), **HDR(self.hotel))
        # Many more open folios with activity.
        for i in range(6):
            fi = self._folio(f"f{i}")
            self._charge(fi, "100.00")
            self._pay(fi, "40.00")
        with CaptureQueriesContext(connection) as qn:
            self.client.get(reverse("finance:overview"), **HDR(self.hotel))
        self.assertEqual(
            len(q1.captured_queries),
            len(qn.captured_queries),
            msg="finance overview must not add a query per open folio (no N+1)",
        )


class ChargeSnapshotTests(APITestCase, ClosureMixin):
    """P2 — nullable frozen snapshots on FolioCharge; no FK to any catalog."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.client.force_authenticate(self.manager)
        self.folio = fin.create_folio(
            self.hotel, customer_name="A", user=self.manager
        )

    def test_snapshots_persist_when_provided(self):
        charge = fin.add_charge(
            self.folio, charge_type="service", description="Spa", quantity=1,
            unit_amount="50.00", source=ChargeSource.GUEST_EXTRA_SERVICE,
            currency_snapshot="USD", service_name_snapshot="Spa session",
            unit_price_snapshot="50.00", tax_rate_snapshot="15.00",
            source_reference="8f1c-uuid-ref", user=self.manager,
        )
        charge.refresh_from_db()
        self.assertEqual(charge.source, "guest_extra_service")
        self.assertEqual(charge.currency_snapshot, "USD")
        self.assertEqual(charge.service_name_snapshot, "Spa session")
        self.assertEqual(charge.unit_price_snapshot, Decimal("50.00"))
        self.assertEqual(charge.tax_rate_snapshot, Decimal("15.00"))
        self.assertEqual(charge.source_reference, "8f1c-uuid-ref")

    def test_existing_charges_keep_null_snapshots(self):
        charge = fin.add_charge(
            self.folio, charge_type="service", description="Plain", quantity=1,
            unit_amount="10.00", user=self.manager,
        )
        charge.refresh_from_db()
        self.assertIsNone(charge.currency_snapshot)
        self.assertIsNone(charge.service_name_snapshot)
        self.assertIsNone(charge.unit_price_snapshot)
        self.assertIsNone(charge.tax_rate_snapshot)
        self.assertIsNone(charge.source_reference)

    def test_snapshot_fields_persist_exact_values(self):
        """``add_charge`` stores the snapshot values it is HANDED, verbatim.

        Scope note (A5): this asserts persistence only. It deliberately does NOT
        claim to prove the frozen-copy invariant — proving that requires mutating
        a real catalog row after posting, which finance cannot reference (the
        layering rule). That invariant is owned by
        ``apps.guest_services.tests.SnapshotImmutabilityTests``.
        """
        name = "Spa session"
        price = Decimal("50.00")
        charge = fin.add_charge(
            self.folio, charge_type="service", description="Spa", quantity=1,
            unit_amount="50.00", service_name_snapshot=name,
            unit_price_snapshot=price, user=self.manager,
        )
        charge.refresh_from_db()
        self.assertEqual(charge.service_name_snapshot, "Spa session")
        self.assertEqual(charge.unit_price_snapshot, Decimal("50.00"))

    def test_no_fk_from_charge_to_guest_services(self):
        related_apps = {
            f.related_model._meta.app_label
            for f in FolioCharge._meta.get_fields()
            if f.is_relation and f.related_model is not None
        }
        self.assertNotIn("guest_services", related_apps)
        self.assertNotIn("guest_service", related_apps)


class ChargeVoidResponseGatingTests(APITestCase, ClosureMixin):
    """A3 (S2) — ``finance.charge_void`` alone must not become a back door onto
    the folio's money.

    ``charge_void`` is an operational correction right held by personas that are
    deliberately denied ``finance.view`` (the guest-folio surface voids service
    lines through exactly this endpoint). The response used to be the FULL
    ``FolioSerializer``, handing such a caller the balance, the totals, every
    payment with its receipt number / method / payer, and every unrelated charge
    on the folio. WHO may void is unchanged; only the payload is gated."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.client.force_authenticate(self.manager)
        self.folio = fin.create_folio(
            self.hotel, customer_name="A", user=self.manager
        )
        self.target = fin.add_charge(
            self.folio, charge_type="service", description="Laundry", quantity=1,
            unit_amount="100.00", source=ChargeSource.GUEST_EXTRA_SERVICE,
            user=self.manager,
        )
        # Money that must NEVER reach a non-finance voider.
        fin.add_charge(
            self.folio, charge_type="service", description="Unrelated spa",
            quantity=1, unit_amount="250.00", user=self.manager,
        )
        fin.record_payment(
            self.folio, amount=Decimal("60.00"), method="cash",
            payer_name="Jane Payer", user=self.manager,
        )

    _MONEY_KEYS = (
        "balance", "total_charges", "total_payments", "payments", "charges",
        "deposits", "insurances", "customer_name",
    )

    def test_voider_without_finance_view_gets_a_minimal_ack_only(self):
        voider = add_member(
            self.hotel, "vo@x.com", perms=["finance.charge_void"]
        )
        self.client.force_authenticate(voider)
        r = self.void_charge_api(self.target.id, reason="posted twice")
        # The void still SUCCEEDS — the right itself is untouched.
        self.assertEqual(r.status_code, 200, r.data)
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, PostingStatus.VOIDED)

        body = r.data
        self.assertIsInstance(body, dict)
        # It describes only the caller's own action...
        self.assertEqual(body["id"], self.target.id)
        self.assertEqual(body["status"], PostingStatus.VOIDED)
        self.assertEqual(body["void_reason"], "posted twice")
        self.assertIsNotNone(body["voided_at"])
        # ...and leaks NOTHING about the folio's money.
        for key in self._MONEY_KEYS:
            self.assertNotIn(key, body, f"{key} leaked to a non-finance voider")
        blob = str(body)
        # "190.00" is the outstanding balance AFTER this void — i.e. the single
        # most sensitive number the old full-folio response handed back. It was
        # missing from this list while "290.00" (a value this fixture never
        # produces) sat here as a dead witness.
        for secret in ("250.00", "60.00", "190.00", "Jane Payer", "Unrelated spa"):
            self.assertNotIn(secret, blob, f"{secret} leaked to a non-finance voider")
        # No staff email anywhere in the payload.
        self.assertNotIn("@", blob)

    def test_voider_with_finance_view_keeps_the_full_body(self):
        """The finance UI is unaffected: same full FolioSerializer as before."""
        staff = add_member(
            self.hotel, "fv@x.com", perms=["finance.view", "finance.charge_void"]
        )
        self.client.force_authenticate(staff)
        r = self.void_charge_api(self.target.id, reason="posted twice")
        self.assertEqual(r.status_code, 200, r.data)
        for key in ("balance", "charges", "payments"):
            self.assertIn(key, r.data, f"{key} missing for a finance.view caller")
        # The totals live INSIDE the ``balance`` block of FolioSerializer, never
        # at the top level — assert them where they actually are.
        for key in ("total_charges", "total_payments", "balance"):
            self.assertIn(
                key, r.data["balance"], f"{key} missing from the balance block"
            )
        # 350.00 charged - 100.00 voided - 60.00 paid = 190.00 outstanding.
        self.assertEqual(r.data["balance"]["balance"], "190.00")
        self.assertEqual(len(r.data["payments"]), 1)

    def test_gating_is_on_the_body_not_on_the_right_to_void(self):
        """A caller lacking charge_void is still 403 — unchanged."""
        nobody = add_member(self.hotel, "nb@x.com", perms=["finance.view"])
        self.client.force_authenticate(nobody)
        r = self.void_charge_api(self.target.id, reason="nope")
        self.assertEqual(r.status_code, 403)
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, PostingStatus.POSTED)


class ChargeCreateRestrictionTests(APITestCase, ClosureMixin):
    """P4 — the generic charge-create path posts DEBITS only; credit corrections
    go through finance.adjust; an overflow returns a clean typed 400."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.client.force_authenticate(self.manager)
        self.fid = self.create_folio(customer_name="A").data["id"]

    def test_charge_create_only_holder_refused_credit_and_negative(self):
        staff = add_member(
            self.hotel, "cc@x.com", perms=["finance.view", "finance.charge_create"]
        )
        self.client.force_authenticate(staff)
        for t in ("discount", "adjustment"):
            r = self.add_charge(self.fid, type=t, unit_amount="20.00")
            self.assertEqual(r.status_code, 400, f"{t}: {r.data}")
            self.assertIn("credit_charges_go_through_adjust", str(r.data))
        neg = self.add_charge(self.fid, type="service", unit_amount="-5.00")
        self.assertEqual(neg.status_code, 400)
        self.assertIn("must_not_be_negative", str(neg.data))
        # ...but the ordinary debit types still post.
        for t in ("service", "tax", "other"):
            ok = self.add_charge(self.fid, type=t, unit_amount="15.00")
            self.assertEqual(ok.status_code, 201, f"{t}: {ok.data}")

    def test_credit_correction_still_flows_through_adjust(self):
        # A charge-create-only holder cannot credit; finance.adjust can (with a
        # mandatory reason, linked to the original, one-per-original, audited).
        self.add_charge(self.fid, unit_amount="100.00", tax_rate="15.00")
        charge = self.age_charge(
            FolioCharge.objects.filter(folio_id=self.fid).latest("id")
        )
        no_reason = self.client.post(
            reverse("finance:charge-adjust", args=[charge.id]), {},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(no_reason.status_code, 400)
        ok = self.adjust_api(charge.id)
        self.assertEqual(ok.status_code, 201)
        adj = FolioCharge.objects.get(folio_id=self.fid, adjusts=charge)
        self.assertEqual(adj.type, "adjustment")
        self.assertEqual(adj.source, "adjustment")
        self.assertEqual(adj.total_amount, -charge.total_amount)

    def test_amount_overflow_returns_clean_400_not_500(self):
        # quantity x unit_amount reaches 11 integer digits (>= MONEY_MAX_ABS);
        # the guard returns a typed 400 instead of a DB NumericValueOutOfRange.
        r = self.add_charge(
            self.fid, type="service", quantity="2", unit_amount="9999999999.00"
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "invalid_amount")


class ChargeDTOEnrichmentTests(APITestCase, ClosureMixin):
    """P7 — enriched charge DTO fields + an itemized departure statement."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=ALL_FINANCE
        )
        self.client.force_authenticate(self.manager)
        self.folio = fin.create_folio(
            self.hotel, customer_name="Alice", user=self.manager
        )

    def test_charge_dto_exposes_created_by_source_qty_unit_tax(self):
        fin.add_charge(
            self.folio, charge_type="service", description="Laundry", quantity=2,
            unit_amount="25.00", tax_rate="15.00", user=self.manager,
        )
        data = self.client.get(
            reverse("finance:folio-detail", args=[self.folio.id]), **HDR(self.hotel)
        ).data
        line = data["charges"][0]
        self.assertEqual(line["created_by"], self.manager.email)
        self.assertEqual(line["created_by_name"], self.manager.full_name)
        self.assertEqual(line["source"], "manual")
        self.assertEqual(line["quantity"], "2.00")
        self.assertEqual(line["unit_amount"], "25.00")
        self.assertEqual(line["tax_amount"], "7.50")
        self.assertEqual(line["tax_rate"], "15.00")

    def test_statement_is_itemized_and_flags_service_lines(self):
        # A restaurant/café order line, a guest-extra-service line, and a plain
        # manual line all appear as itemized rows.
        fin.add_charge(
            self.folio, charge_type="service", description="Dinner", quantity=1,
            unit_amount="40.00", source=ChargeSource.SERVICE_ORDER,
            user=self.manager,
        )
        fin.add_charge(
            self.folio, charge_type="service", description="Spa", quantity=1,
            unit_amount="60.00", source=ChargeSource.GUEST_EXTRA_SERVICE,
            service_name_snapshot="Spa session", source_reference="ref-1",
            user=self.manager,
        )
        fin.add_charge(
            self.folio, charge_type="other", description="Misc", quantity=1,
            unit_amount="5.00", user=self.manager,
        )
        r = self.client.get(
            reverse("finance:folio-statement", args=[self.folio.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        items = r.data["line_items"]
        self.assertEqual(len(items), 3)
        by_source = {i["source"]: i for i in items}
        self.assertTrue(by_source["service_order"]["is_service_line"])
        self.assertTrue(by_source["guest_extra_service"]["is_service_line"])
        self.assertFalse(by_source["manual"]["is_service_line"])
        spa = by_source["guest_extra_service"]
        self.assertEqual(spa["unit_price"], "60.00")
        self.assertEqual(spa["quantity"], "1.00")
        self.assertEqual(spa["staff"], self.manager.full_name)
        self.assertEqual(spa["service_name_snapshot"], "Spa session")
        self.assertEqual(spa["source_reference"], "ref-1")
        # The existing folio print still works unchanged.
        self.assertEqual(r.data["document"], "statement")
        self.assertEqual(len(r.data["folio"]["charges"]), 3)


class ExpenseWriteResponseDisclosureTests(ExpensesClosureBase):
    """SEC regression: a WRITE permission must NEVER widen READ access.

    An ``expenses.update``-only caller is refused on GET, so an (even empty)
    PATCH must not hand back the full voucher — that would be a silent
    ``expenses.view`` bypass. Same for an ``expenses.reverse``-only caller
    (owner §7: void/reverse must not return data wider than the permission).
    """

    ACK_KEYS = {"id", "expense_number", "status", "voided_at"}

    def _staff(self, perms):
        user = add_member(self.hotel, f"{uuid.uuid4().hex[:10]}@x.com", perms=perms)
        self.client.force_authenticate(user)
        return user

    def test_update_only_caller_gets_ack_not_the_voucher(self):
        eid = self.create_exp(amount="777.77").data["id"]
        self._staff(["expenses.update"])
        # It cannot READ the record...
        got = self.client.get(
            reverse("finance:expense-detail", args=[eid]), **HDR(self.hotel)
        )
        self.assertEqual(got.status_code, 403)
        # ...so an empty PATCH must not disclose it either.
        res = self.client.patch(
            reverse("finance:expense-detail", args=[eid]), {},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(set(res.data), self.ACK_KEYS)
        self.assertNotIn("amount", res.data)
        self.assertNotIn("description", res.data)

    def test_update_caller_holding_view_still_gets_the_voucher(self):
        eid = self.create_exp(amount="12.00").data["id"]
        self._staff(["expenses.update", "expenses.view"])
        res = self.client.patch(
            reverse("finance:expense-detail", args=[eid]),
            {"description": "New text"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["amount"], "12.00")

    def test_reverse_only_caller_gets_ack_not_the_voucher(self):
        eid = self.create_exp(amount="55.00").data["id"]
        self.age_exp(eid)  # void window passed -> the corrective path applies
        self._staff(["expenses.reverse"])
        res = self.client.post(
            reverse("finance:expense-reverse", args=[eid]), {"reason": "fix"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(set(res.data), self.ACK_KEYS)
        self.assertNotIn("amount", res.data)
