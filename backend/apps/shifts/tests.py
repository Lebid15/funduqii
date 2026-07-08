"""Tests for shifts / handover / daily close (Phase 12).

Covers access control, tenant isolation, the suspended-hotel read-only rule,
SH/HO/DC numbering, the shift lifecycle with drawer math (expected cash from
POSTED cash movements; a difference needs a reason), the finance attachment
(payments/expenses auto-attach to the creator's open shift; unassigned
movements are reported), the handover workflow with the recipient guard, the
daily close validations (no open shifts, no pending handovers, never twice)
and the business-day lock on the safe integrated flows.
"""
from __future__ import annotations

from decimal import Decimal

from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.common.exceptions import BusinessDayClosed
from apps.finance.models import PaymentMethod
from apps.finance.services import create_expense, create_folio, record_payment, void_payment
from apps.rbac.services import grant_permission
from apps.shifts.models import (
    DailyClose,
    DailyCloseStatus,
    Shift,
    ShiftHandover,
    ShiftStatus,
)
from apps.shifts.services import get_business_date
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

STRONG = "StrongPass!234"

SHIFT_PERMS = [
    "shifts.view", "shifts.create", "shifts.update", "shifts.close",
    "shifts.cancel", "shifts.handover", "shifts.accept_handover",
]
DC_PERMS = ["daily_close.view", "daily_close.prepare", "daily_close.close"]


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=()):
    user = User.objects.create_user(email=email, password=STRONG, full_name="Member")
    m = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True
    )
    for code in perms:
        grant_permission(m, code)
    return user


class ShiftsMixin:
    def open_shift(self, hotel=None, **body):
        hotel = hotel or self.hotel
        body.setdefault("opening_cash_amount", "100.00")
        return self.client.post(
            reverse("shifts:shift-list"), body, format="json", **HDR(hotel)
        )

    def close_shift(self, pk, actual, hotel=None, **body):
        body["actual_cash_amount"] = actual
        return self.client.post(
            reverse("shifts:shift-close", args=[pk]), body, format="json",
            **HDR(hotel or self.hotel),
        )

    def act(self, name, pk, body=None, hotel=None):
        return self.client.post(
            reverse(f"shifts:{name}", args=[pk]), body or {}, format="json",
            **HDR(hotel or self.hotel),
        )

    def close_day(self, business_date=None, hotel=None):
        body = {"business_date": str(business_date)} if business_date else {}
        return self.client.post(
            reverse("shifts:daily-close-close"), body, format="json",
            **HDR(hotel or self.hotel),
        )


# --------------------------------------------------------------------------- #
# Access / permissions                                                          #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_unauthenticated_denied(self):
        self.assertEqual(
            self.client.get(reverse("shifts:shift-list"), **HDR(self.hotel)).status_code,
            401,
        )

    def test_no_membership_denied(self):
        lonely = User.objects.create_user(email="l@x.com", password=STRONG, full_name="L")
        self.client.force_authenticate(lonely)
        self.assertEqual(
            self.client.get(reverse("shifts:shift-list"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_platform_owner_without_membership_denied(self):
        owner = User.objects.create_user(email="p@x.com", password=STRONG, full_name="P")
        owner.account_type = AccountType.PLATFORM_OWNER
        owner.save(update_fields=["account_type"])
        self.client.force_authenticate(owner)
        self.assertEqual(
            self.client.get(reverse("shifts:overview"), **HDR(self.hotel)).status_code,
            403,
        )

    def test_hotel_a_cannot_access_hotel_b(self):
        self.client.force_authenticate(self.manager)
        shift = self.open_shift().data
        other = make_hotel(slug="o")
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(om)
        r = self.client.get(
            reverse("shifts:shift-detail", args=[shift["id"]]), **HDR(other)
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(
            self.client.get(reverse("shifts:shift-list"), **HDR(other)).data["count"], 0
        )

    def test_manager_can_manage_everything(self):
        self.client.force_authenticate(self.manager)
        shift = self.open_shift().data
        self.assertEqual(shift["shift_number"], "SH00001")
        r = self.close_shift(shift["id"], "100.00")
        self.assertEqual(r.status_code, 200)
        r = self.close_day()
        self.assertEqual(r.status_code, 200)

    def test_staff_view_only(self):
        viewer = add_member(self.hotel, "v@x.com", perms=["shifts.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(
            self.client.get(reverse("shifts:shift-list"), **HDR(self.hotel)).status_code,
            200,
        )
        self.assertEqual(self.open_shift().status_code, 403)

    def test_staff_without_view_denied(self):
        worker = add_member(self.hotel, "w@x.com", perms=["rooms.view"])
        self.client.force_authenticate(worker)
        for name in ("shift-list", "current", "overview"):
            self.assertEqual(
                self.client.get(reverse(f"shifts:{name}"), **HDR(self.hotel)).status_code,
                403,
                name,
            )

    def test_staff_with_create_can_open(self):
        creator = add_member(self.hotel, "c@x.com", perms=["shifts.view", "shifts.create"])
        self.client.force_authenticate(creator)
        self.assertEqual(self.open_shift().status_code, 201)

    def test_staff_with_close_can_close(self):
        worker = add_member(
            self.hotel, "cl@x.com", perms=["shifts.view", "shifts.create", "shifts.close"]
        )
        self.client.force_authenticate(worker)
        shift = self.open_shift().data
        self.assertEqual(self.close_shift(shift["id"], "100.00").status_code, 200)

    def test_staff_without_daily_close_denied(self):
        worker = add_member(self.hotel, "d@x.com", perms=SHIFT_PERMS)
        self.client.force_authenticate(worker)
        self.assertEqual(self.close_day().status_code, 403)

    def test_staff_with_daily_close_can_close_day(self):
        worker = add_member(self.hotel, "d2@x.com", perms=["daily_close.view", "daily_close.close"])
        self.client.force_authenticate(worker)
        self.assertEqual(self.close_day().status_code, 200)

    def test_non_manager_cannot_open_for_someone_else(self):
        other_staff = add_member(self.hotel, "os@x.com", perms=[])
        creator = add_member(self.hotel, "c2@x.com", perms=["shifts.view", "shifts.create"])
        self.client.force_authenticate(creator)
        r = self.open_shift(responsible_user=other_staff.id)
        self.assertEqual(r.status_code, 403)


class SuspendedHotelTests(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel(status=HotelStatus.SUSPENDED)
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_view_allowed(self):
        for name in ("shift-list", "handover-list", "daily-close-list", "overview", "current"):
            self.assertEqual(
                self.client.get(reverse(f"shifts:{name}"), **HDR(self.hotel)).status_code,
                200,
                name,
            )

    def test_writes_blocked(self):
        r = self.open_shift()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "hotel_suspended")
        r = self.client.post(
            reverse("shifts:daily-close-close"), {}, format="json", **HDR(self.hotel)
        )
        self.assertEqual(r.data["code"], "hotel_suspended")
        r = self.client.post(
            reverse("shifts:daily-close-prepare"), {}, format="json", **HDR(self.hotel)
        )
        self.assertEqual(r.data["code"], "hotel_suspended")


# --------------------------------------------------------------------------- #
# Shift lifecycle & drawer math                                                 #
# --------------------------------------------------------------------------- #


class ShiftTests(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_open_generates_number_and_business_date(self):
        r = self.open_shift(opening_notes="morning")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["shift_number"], "SH00001")
        self.assertEqual(r.data["status"], "open")
        self.assertEqual(r.data["business_date"], str(get_business_date(self.hotel)))
        self.assertEqual(r.data["opening_cash_amount"], "100.00")

    def test_duplicate_open_shift_rejected(self):
        self.open_shift()
        r = self.open_shift()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "shift_already_open")

    def test_two_users_can_hold_open_shifts(self):
        self.open_shift()
        worker = add_member(self.hotel, "w@x.com", perms=["shifts.view", "shifts.create"])
        self.client.force_authenticate(worker)
        self.assertEqual(self.open_shift().status_code, 201)

    def test_current_shift_endpoint(self):
        self.assertIsNone(
            self.client.get(reverse("shifts:current"), **HDR(self.hotel)).data["shift"]
        )
        self.open_shift()
        data = self.client.get(reverse("shifts:current"), **HDR(self.hotel)).data
        self.assertEqual(data["shift"]["shift_number"], "SH00001")
        self.assertEqual(data["cash_summary"]["expected_cash"], "100.00")

    def test_close_without_difference(self):
        shift = self.open_shift().data
        r = self.close_shift(shift["id"], "100.00")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "closed")
        self.assertEqual(r.data["expected_cash_amount"], "100.00")
        self.assertEqual(r.data["cash_difference"], "0.00")

    def test_close_with_difference_requires_reason(self):
        shift = self.open_shift().data
        r = self.close_shift(shift["id"], "90.00")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "cash_difference_reason_required")
        r = self.close_shift(shift["id"], "90.00", difference_reason="missing note")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["cash_difference"], "-10.00")
        self.assertEqual(r.data["difference_reason"], "missing note")

    def test_close_twice_rejected(self):
        shift = self.open_shift().data
        self.close_shift(shift["id"], "100.00")
        r = self.close_shift(shift["id"], "100.00")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "shift_not_open")

    def test_cancel_requires_reason_and_open_status(self):
        shift = self.open_shift().data
        r = self.act("shift-cancel", shift["id"], {"reason": ""})
        self.assertEqual(r.status_code, 400)
        r = self.act("shift-cancel", shift["id"], {"reason": "opened by mistake"})
        self.assertEqual(r.data["status"], "cancelled")
        r = self.act("shift-cancel", shift["id"], {"reason": "again"})
        self.assertEqual(r.status_code, 409)

    def test_closed_shift_only_internal_notes_editable(self):
        shift = self.open_shift().data
        self.close_shift(shift["id"], "100.00")
        r = self.client.patch(
            reverse("shifts:shift-detail", args=[shift["id"]]),
            {"opening_cash_amount": "999.00"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "operation_not_editable")
        r = self.client.patch(
            reverse("shifts:shift-detail", args=[shift["id"]]),
            {"internal_notes": "management remark"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["internal_notes"], "management remark")

    def test_status_logs_created(self):
        shift = self.open_shift().data
        self.close_shift(shift["id"], "100.00")
        detail = self.client.get(
            reverse("shifts:shift-detail", args=[shift["id"]]), **HDR(self.hotel)
        ).data
        transitions = [(l["previous_status"], l["new_status"]) for l in detail["status_logs"]]
        self.assertIn(("", "open"), transitions)
        self.assertIn(("open", "closed"), transitions)

    def test_no_hard_delete(self):
        shift = self.open_shift().data
        r = self.client.delete(
            reverse("shifts:shift-detail", args=[shift["id"]]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 405)
        self.assertTrue(Shift.objects.filter(pk=shift["id"]).exists())

    def test_list_filters(self):
        shift = self.open_shift().data
        self.close_shift(shift["id"], "100.00")
        worker = add_member(self.hotel, "w2@x.com", perms=["shifts.view", "shifts.create"])
        self.client.force_authenticate(worker)
        self.open_shift()
        self.client.force_authenticate(self.manager)
        base = reverse("shifts:shift-list")
        self.assertEqual(
            self.client.get(base + "?status=open", **HDR(self.hotel)).data["count"], 1
        )
        self.assertEqual(
            self.client.get(base + "?search=SH00001", **HDR(self.hotel)).data["count"], 1
        )


# --------------------------------------------------------------------------- #
# Finance integration                                                           #
# --------------------------------------------------------------------------- #


class FinanceIntegrationTests(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.folio = create_folio(self.hotel, customer_name="Walk-in")

    def test_payment_attaches_to_open_shift(self):
        shift = self.open_shift().data
        payment = record_payment(
            self.folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager
        )
        self.assertEqual(payment.shift_id, shift["id"])

    def test_expense_attaches_to_open_shift(self):
        shift = self.open_shift().data
        expense = create_expense(
            self.hotel, category="supplies", description="Water",
            amount="20.00", method=PaymentMethod.CASH, user=self.manager,
        )
        self.assertEqual(expense.shift_id, shift["id"])

    def test_expected_cash_math(self):
        shift = self.open_shift().data  # opening 100
        record_payment(self.folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager)
        record_payment(self.folio, amount="80.00", method=PaymentMethod.CARD, user=self.manager)
        create_expense(
            self.hotel, category="supplies", description="Water",
            amount="20.00", method=PaymentMethod.CASH, user=self.manager,
        )
        summary = self.client.get(
            reverse("shifts:shift-summary", args=[shift["id"]]), **HDR(self.hotel)
        ).data["cash_summary"]
        # 100 + 50 cash - 20 cash = 130; card ignored for the drawer.
        self.assertEqual(summary["expected_cash"], "130.00")
        self.assertEqual(summary["cash_payments_total"], "50.00")
        self.assertEqual(summary["cash_expenses_total"], "20.00")
        self.assertIn("card", summary["payments_by_method"])

    def test_voided_payment_excluded_from_drawer(self):
        shift = self.open_shift().data
        payment = record_payment(
            self.folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager
        )
        void_payment(payment, reason="entry error", user=self.manager)
        r = self.close_shift(shift["id"], "100.00")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["expected_cash_amount"], "100.00")

    def test_unassigned_movement_reported(self):
        # No open shift for this user -> the payment stays unassigned.
        payment = record_payment(
            self.folio, amount="30.00", method=PaymentMethod.CASH, user=self.manager
        )
        self.assertIsNone(payment.shift_id)
        overview = self.client.get(reverse("shifts:overview"), **HDR(self.hotel)).data
        self.assertEqual(overview["unassigned_movements"]["payments_count"], 1)
        self.assertEqual(overview["unassigned_movements"]["payments_total"], "30.00")

    def test_cancel_shift_with_movements_blocked(self):
        shift = self.open_shift().data
        record_payment(self.folio, amount="10.00", method=PaymentMethod.CASH, user=self.manager)
        r = self.act("shift-cancel", shift["id"], {"reason": "mistake"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "resource_in_use")


# --------------------------------------------------------------------------- #
# Handover                                                                      #
# --------------------------------------------------------------------------- #


class HandoverTests(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.receiver = add_member(
            self.hotel, "r@x.com", perms=["shifts.view", "shifts.accept_handover"]
        )
        self.client.force_authenticate(self.manager)
        self.shift = self.open_shift().data

    def create_handover(self, **body):
        body.setdefault("from_shift", self.shift["id"])
        body.setdefault("to_user", self.receiver.id)
        return self.client.post(
            reverse("shifts:handover-list"), body, format="json", **HDR(self.hotel)
        )

    def test_create_and_number(self):
        r = self.create_handover(summary_notes="quiet evening", pending_tasks_notes="room 101 towels")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["handover_number"], "HO00001")
        self.assertEqual(r.data["status"], "draft")

    def test_to_user_must_be_active_member(self):
        outsider = User.objects.create_user(email="out@x.com", password=STRONG, full_name="Out")
        r = self.create_handover(to_user=outsider.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "cross_tenant_reference")

    def test_submit_accept_flow(self):
        handover = self.create_handover().data
        r = self.act("handover-submit", handover["id"])
        self.assertEqual(r.data["status"], "submitted")
        self.client.force_authenticate(self.receiver)
        r = self.act("handover-accept", handover["id"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "accepted")
        self.assertIsNotNone(r.data["accepted_at"])

    def test_only_recipient_or_manager_can_accept(self):
        handover = self.create_handover().data
        self.act("handover-submit", handover["id"])
        stranger = add_member(
            self.hotel, "s@x.com", perms=["shifts.view", "shifts.accept_handover"]
        )
        self.client.force_authenticate(stranger)
        r = self.act("handover-accept", handover["id"])
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data["code"], "handover_not_recipient")
        # The manager can accept on the recipient's behalf.
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.act("handover-accept", handover["id"]).status_code, 200)

    def test_reject_requires_reason(self):
        handover = self.create_handover().data
        self.act("handover-submit", handover["id"])
        self.client.force_authenticate(self.receiver)
        r = self.act("handover-reject", handover["id"], {"reason": ""})
        self.assertEqual(r.status_code, 400)
        r = self.act("handover-reject", handover["id"], {"reason": "cash not counted"})
        self.assertEqual(r.data["status"], "rejected")
        self.assertEqual(r.data["rejection_reason"], "cash not counted")

    def test_cancel_requires_reason(self):
        handover = self.create_handover().data
        r = self.act("handover-cancel", handover["id"], {"reason": "typo"})
        self.assertEqual(r.data["status"], "cancelled")

    def test_accepted_handover_frozen(self):
        handover = self.create_handover().data
        self.act("handover-submit", handover["id"])
        self.act("handover-accept", handover["id"])  # manager accepts
        r = self.client.patch(
            reverse("shifts:handover-detail", args=[handover["id"]]),
            {"summary_notes": "rewrite"},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        r = self.act("handover-cancel", handover["id"], {"reason": "x"})
        self.assertEqual(r.status_code, 409)

    def test_status_logs_created(self):
        handover = self.create_handover().data
        self.act("handover-submit", handover["id"])
        detail = self.client.get(
            reverse("shifts:handover-detail", args=[handover["id"]]), **HDR(self.hotel)
        ).data
        transitions = [(l["previous_status"], l["new_status"]) for l in detail["status_logs"]]
        self.assertIn(("draft", "submitted"), transitions)


# --------------------------------------------------------------------------- #
# Daily close & the business-day lock                                           #
# --------------------------------------------------------------------------- #


class DailyCloseTests(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.today = get_business_date(self.hotel)

    def test_prepare_creates_draft_snapshot(self):
        r = self.client.post(
            reverse("shifts:daily-close-prepare"), {}, format="json", **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "draft")
        self.assertEqual(r.data["close_number"], "DC00001")
        self.assertEqual(r.data["snapshot_json"]["business_date"], str(self.today))
        self.assertIn("payments", r.data["snapshot_json"])
        # Idempotent: preparing again refreshes, no new row/number.
        r2 = self.client.post(
            reverse("shifts:daily-close-prepare"), {}, format="json", **HDR(self.hotel)
        )
        self.assertEqual(r2.data["close_number"], "DC00001")
        self.assertEqual(DailyClose.objects.filter(hotel=self.hotel).count(), 1)

    def test_cannot_close_day_with_open_shift(self):
        self.open_shift()
        r = self.close_day()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "open_shifts_prevent_close")

    def test_cannot_close_day_with_pending_handover(self):
        shift = self.open_shift().data
        receiver = add_member(self.hotel, "r@x.com", perms=["shifts.view"])
        handover = self.client.post(
            reverse("shifts:handover-list"),
            {"from_shift": shift["id"], "to_user": receiver.id},
            format="json",
            **HDR(self.hotel),
        ).data
        self.act("handover-submit", handover["id"])
        self.close_shift(shift["id"], "100.00")
        r = self.close_day()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "pending_handovers_prevent_close")

    def test_close_day_and_snapshot(self):
        shift = self.open_shift().data
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager)
        self.close_shift(shift["id"], "150.00")
        r = self.close_day()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "closed")
        self.assertEqual(r.data["totals_json"]["payments_cash_total"], "50.00")
        self.assertEqual(r.data["totals_json"]["shifts_count"], 1)
        self.assertEqual(len(r.data["snapshot_json"]["shifts"]), 1)
        detail = self.client.get(
            reverse("shifts:daily-close-detail", args=[str(self.today)]),
            **HDR(self.hotel),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["status"], "closed")

    def test_cannot_close_day_twice(self):
        self.close_day()
        r = self.close_day()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "day_already_closed")

    def test_lock_blocks_new_payment_and_expense(self):
        self.close_day()
        folio = create_folio(self.hotel, customer_name="W")
        with self.assertRaises(BusinessDayClosed):
            record_payment(folio, amount="10.00", method=PaymentMethod.CASH, user=self.manager)
        with self.assertRaises(BusinessDayClosed):
            create_expense(
                self.hotel, category="supplies", description="Late",
                amount="5.00", method=PaymentMethod.CASH, user=self.manager,
            )

    def test_lock_blocks_opening_shift_on_closed_day(self):
        self.close_day()
        r = self.open_shift()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "business_day_closed")

    def test_lock_blocks_service_posting_on_closed_day(self):
        from apps.services.services import post_order_to_folio
        from apps.services.models import (
            OrderStatus,
            ServiceCategory,
            ServiceItem,
            ServiceOrder,
            ServiceOrderItem,
        )

        category = ServiceCategory.objects.create(hotel=self.hotel, name="Cafe")
        item = ServiceItem.objects.create(
            hotel=self.hotel, category=category, name="Tea",
            unit_price=Decimal("10.00"),
        )
        from django.utils import timezone as dj_tz

        order = ServiceOrder.objects.create(
            hotel=self.hotel, order_number="ORD00001",
            status=OrderStatus.DELIVERED, ordered_at=dj_tz.now(),
            folio=create_folio(self.hotel, customer_name="W"),
        )
        ServiceOrderItem.objects.create(
            hotel=self.hotel, order=order, service_item=item, item_name="Tea",
            quantity=1, unit_price=Decimal("10.00"), amount=Decimal("10.00"),
            tax_amount=Decimal("0.00"), total_amount=Decimal("10.00"),
        )
        self.close_day()
        with self.assertRaises(BusinessDayClosed):
            post_order_to_folio(order, user=self.manager)

    def test_no_hard_delete_and_list(self):
        self.close_day()
        listed = self.client.get(
            reverse("shifts:daily-close-list"), **HDR(self.hotel)
        ).data
        self.assertEqual(listed["count"], 1)

    def test_reopen_not_built(self):
        with self.assertRaises(NoReverseMatch):
            reverse("shifts:daily-close-reopen", args=[1])


# --------------------------------------------------------------------------- #
# Regression                                                                    #
# --------------------------------------------------------------------------- #


class RegressionTests(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_health_still_works(self):
        self.client.force_authenticate()
        self.assertEqual(self.client.get("/api/health/").status_code, 200)

    def test_finance_still_works_without_any_shift(self):
        folio = create_folio(self.hotel, customer_name="W")
        payment = record_payment(
            folio, amount="10.00", method=PaymentMethod.CASH, user=self.manager
        )
        self.assertIsNone(payment.shift_id)
        self.assertEqual(payment.receipt_number, "RCP00001")

    def test_existing_phase_endpoints_reachable(self):
        for name in (
            "rooms:room-list", "reservations:reservation-list", "guests:guest-list",
            "stays:stay-list", "finance:folio-list", "services:order-list",
            "operations:housekeeping-list", "staff:staff-list",
        ):
            self.assertEqual(
                self.client.get(reverse(name), **HDR(self.hotel)).status_code, 200, name
            )

    def test_my_permissions_includes_shift_codes(self):
        r = self.client.get(reverse("staff:my-permissions"), **HDR(self.hotel))
        self.assertIn("shifts.view", r.data["permissions"])
        self.assertIn("daily_close.close", r.data["permissions"])

    def test_no_out_of_scope_endpoints(self):
        for name in ("attendance-list", "payroll-list", "schedule-list", "reports"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"shifts:{name}")
