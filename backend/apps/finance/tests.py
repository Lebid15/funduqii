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
