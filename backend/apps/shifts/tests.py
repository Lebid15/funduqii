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

from datetime import timedelta
from decimal import Decimal

from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.common.exceptions import BusinessDateMismatch, BusinessDayClosed
from apps.finance.models import PaymentMethod
from apps.finance.services import (
    create_expense,
    create_expense_type,
    create_folio,
    record_payment,
    void_payment,
)
from apps.hotels.models import HotelSettings
from apps.rbac.services import grant_permission
from apps.shifts.models import (
    DailyClose,
    DailyCloseStatus,
    Shift,
    ShiftHandover,
    ShiftStatus,
)
from apps.shifts.services import ensure_business_day_open, get_business_date
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

    def prepare(self, business_date=None, hotel=None):
        body = {"business_date": str(business_date)} if business_date else {}
        return self.client.post(
            reverse("shifts:daily-close-prepare"), body, format="json",
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

    def test_prepare_allowed_on_suspended_hotel(self):
        # Prepare is READ-ONLY now — a suspended (read-only) hotel may preview.
        r = self.prepare()
        self.assertEqual(r.status_code, 200)
        self.assertIn("can_close", r.data)
        self.assertIn("blocking_errors", r.data)


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

    def test_closed_shift_is_fully_read_only(self):
        # Shifts final closure: a closed shift is fully read-only — NO field,
        # not even the internal note, may change after close.
        shift = self.open_shift().data
        self.close_shift(shift["id"], "100.00")
        for payload in ({"opening_cash_amount": "999.00"}, {"internal_notes": "late remark"}):
            r = self.client.patch(
                reverse("shifts:shift-detail", args=[shift["id"]]),
                payload, format="json", **HDR(self.hotel),
            )
            self.assertEqual(r.status_code, 409, payload)
            self.assertEqual(r.data["code"], "operation_not_editable")

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
        etype = create_expense_type(self.hotel, name="Supplies", user=self.manager)
        expense = create_expense(
            self.hotel, expense_type=etype, description="Water",
            amount="20.00", method=PaymentMethod.CASH, user=self.manager,
        )
        self.assertEqual(expense.shift_id, shift["id"])

    def test_expected_cash_math(self):
        shift = self.open_shift().data  # opening 100
        record_payment(self.folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager)
        record_payment(self.folio, amount="80.00", method=PaymentMethod.CARD, user=self.manager)
        etype = create_expense_type(self.hotel, name="Supplies", user=self.manager)
        create_expense(
            self.hotel, expense_type=etype, description="Water",
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
        self.settings = HotelSettings.objects.create(
            hotel=self.hotel, default_currency="USD", timezone="UTC"
        )
        self.today = get_business_date(self.hotel)
        self.settings.business_date = self.today
        self.settings.save(update_fields=["business_date"])
        # Drop the cached reverse OneToOne so later reads see the seeded value.
        self.hotel = Hotel.objects.get(pk=self.hotel.pk)

    def fresh_hotel(self):
        # A hotel instance with NO cached settings — needed after a close has
        # rolled the stored business_date via a different instance.
        return Hotel.objects.get(pk=self.hotel.pk)

    # --- business_date (stored) ------------------------------------------

    def test_get_business_date_reads_stored(self):
        self.settings.business_date = self.today + timedelta(days=10)
        self.settings.save(update_fields=["business_date"])
        self.assertEqual(get_business_date(self.fresh_hotel()), self.today + timedelta(days=10))

    def test_get_business_date_fallback_when_unset_does_not_persist(self):
        self.settings.business_date = None
        self.settings.save(update_fields=["business_date"])
        self.assertIsNotNone(get_business_date(self.fresh_hotel()))
        self.settings.refresh_from_db()
        self.assertIsNone(self.settings.business_date)

    def test_migration_backfill_from_last_close_and_localdate(self):
        # Exercise the backfill helper directly (no closed day → localdate;
        # with a closed day → latest + 1).
        from django.apps import apps as dj_apps
        from importlib import import_module

        mod = import_module("apps.hotels.migrations.0005_hotelsettings_business_date")
        # no closed day -> localdate seed
        self.settings.business_date = None
        self.settings.save(update_fields=["business_date"])
        mod.backfill_business_date(dj_apps, None)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.business_date, self.today)
        # a closed day -> latest closed + 1
        DailyClose.objects.create(
            hotel=self.hotel, close_number="DC00050",
            business_date=self.today, status=DailyCloseStatus.CLOSED,
            snapshot_json={}, totals_json={},
        )
        self.settings.business_date = None
        self.settings.save(update_fields=["business_date"])
        mod.backfill_business_date(dj_apps, None)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.business_date, self.today + timedelta(days=1))

    # --- Prepare (read-only) ---------------------------------------------

    def test_prepare_is_read_only(self):
        r = self.prepare()
        self.assertEqual(r.status_code, 200)
        for key in ("business_date", "can_close", "blocking_errors",
                    "warnings", "informational_alerts", "preview_totals"):
            self.assertIn(key, r.data)
        self.assertEqual(r.data["business_date"], str(self.today))
        self.assertTrue(r.data["can_close"])
        self.assertEqual(DailyClose.objects.filter(hotel=self.hotel).count(), 0)

    def test_prepare_repeatable_no_side_effects(self):
        self.prepare()
        self.prepare()
        self.assertEqual(DailyClose.objects.filter(hotel=self.hotel).count(), 0)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.business_date, self.today)

    def test_prepare_flags_open_shift_blocking(self):
        self.open_shift()
        r = self.prepare()
        self.assertFalse(r.data["can_close"])
        self.assertIn("open_shifts", [b["code"] for b in r.data["blocking_errors"]])

    # --- The one blocker: open shift -------------------------------------

    def test_open_shift_blocks_close_no_roll(self):
        self.open_shift()
        r = self.close_day()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "open_shifts_prevent_close")
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.business_date, self.today)

    # --- Pending handover is a WARNING, not a blocker --------------------

    def test_pending_handover_is_warning_not_block(self):
        shift = self.open_shift().data
        receiver = add_member(self.hotel, "r@x.com", perms=["shifts.view"])
        handover = self.client.post(
            reverse("shifts:handover-list"),
            {"from_shift": shift["id"], "to_user": receiver.id},
            format="json", **HDR(self.hotel),
        ).data
        self.act("handover-submit", handover["id"])
        self.close_shift(shift["id"], "100.00")
        prep = self.prepare()
        self.assertTrue(prep.data["can_close"])
        self.assertIn("pending_handovers", [w["code"] for w in prep.data["warnings"]])
        r = self.close_day()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "closed")

    # --- Close contract: roll, idempotency, mismatch ---------------------

    def test_close_rolls_business_date_one_day(self):
        r = self.close_day()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "closed")
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.business_date, self.today + timedelta(days=1))
        self.assertEqual(get_business_date(self.fresh_hotel()), self.today + timedelta(days=1))

    def test_close_rejects_future_date(self):
        r = self.close_day(self.today + timedelta(days=3))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "business_date_mismatch")

    def test_close_rejects_past_date_after_roll(self):
        self.close_day()
        r = self.close_day(self.today)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "business_date_mismatch")

    def test_close_rejects_already_closed_current_date(self):
        DailyClose.objects.create(
            hotel=self.hotel, close_number="DC00099",
            business_date=self.today, status=DailyCloseStatus.CLOSED,
            snapshot_json={}, totals_json={},
        )
        r = self.close_day(self.today)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "day_already_closed")

    def test_forced_failure_rolls_back_fully(self):
        from unittest.mock import patch

        from apps.shifts.services import close_business_day

        with patch("apps.notifications.services.record_activity", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                close_business_day(self.hotel, self.today, user=self.manager)
        self.assertEqual(
            DailyClose.objects.filter(hotel=self.hotel, status=DailyCloseStatus.CLOSED).count(), 0
        )
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.business_date, self.today)

    # --- New activity after close lands on the new open day --------------

    def test_new_activity_after_close_uses_next_day(self):
        self.close_day()
        nxt = self.today + timedelta(days=1)
        hotel = self.fresh_hotel()
        folio = create_folio(hotel, customer_name="W")
        p = record_payment(folio, amount="10.00", method=PaymentMethod.CASH, user=self.manager)
        self.assertEqual(p.business_date, nxt)
        r = self.open_shift()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["business_date"], str(nxt))

    def test_closed_day_guard_refuses_explicit_old_date(self):
        self.close_day()
        with self.assertRaises(BusinessDayClosed):
            ensure_business_day_open(self.fresh_hotel(), self.today)

    # --- Snapshot: shape, totals, immutability ---------------------------

    def test_close_records_totals_and_snapshot_sections(self):
        shift = self.open_shift().data
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager)
        self.close_shift(shift["id"], "150.00")
        r = self.close_day()
        self.assertEqual(r.status_code, 200)
        snap = r.data["snapshot_json"]
        for key in ("identity", "shifts", "payments", "expenses",
                    "restaurant", "folios", "operations", "exceptions"):
            self.assertIn(key, snap)
        self.assertEqual(snap["identity"]["business_date"], str(self.today))
        self.assertEqual(snap["identity"]["next_business_date"], str(self.today + timedelta(days=1)))
        self.assertEqual(snap["identity"]["currency"], "USD")
        self.assertEqual(r.data["totals_json"]["payments_cash_total"], "50.00")
        self.assertEqual(r.data["totals_json"]["shifts_count"], 1)
        self.assertEqual(len(snap["shifts"]["items"]), 1)
        detail = self.client.get(
            reverse("shifts:daily-close-detail", args=[str(self.today)]), **HDR(self.hotel)
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["status"], "closed")

    def test_snapshot_separates_reversals(self):
        from apps.finance.models import Payment

        folio = create_folio(self.hotel, customer_name="W")
        orig = record_payment(folio, amount="40.00", method=PaymentMethod.CASH, user=self.manager)
        Payment.objects.create(
            hotel=self.hotel, folio=folio, receipt_number="RV00001",
            amount=Decimal("-40.00"), currency="USD", method=PaymentMethod.CASH,
            paid_at=orig.paid_at, business_date=self.today, reverses=orig,
        )
        r = self.close_day()
        pay = r.data["snapshot_json"]["payments"]
        self.assertEqual(pay["reversals_count"], 1)
        self.assertEqual(pay["reversals_total"], "-40.00")
        self.assertEqual(pay["cash_total"], "40.00")

    def test_unassigned_cash_reported_not_blocking(self):
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="30.00", method=PaymentMethod.CASH, user=self.manager)
        r = self.close_day()
        self.assertEqual(r.status_code, 200)
        un = r.data["snapshot_json"]["exceptions"]["unassigned_movements"]
        self.assertEqual(un["cash_payments"]["count"], 1)
        self.assertEqual(un["cash_payments"]["total"], "30.00")
        self.assertEqual(un["net_cash"], "30.00")

    def test_open_folio_with_balance_does_not_block(self):
        from apps.finance.services import add_charge

        folio = create_folio(self.hotel, customer_name="W")
        add_charge(
            folio, charge_type="service", description="svc",
            quantity=1, unit_amount="200.00", user=self.manager,
        )
        r = self.close_day()
        self.assertEqual(r.status_code, 200)
        fol = r.data["snapshot_json"]["folios"]
        self.assertEqual(fol["open_folios_count"], 1)
        self.assertEqual(fol["positive_balance_count"], 1)
        self.assertEqual(fol["positive_balance_amount"], "200.00")

    # --- Room charges & taxes -------------------------------------------

    def test_close_creates_no_room_charge(self):
        from apps.finance.models import FolioCharge

        before = FolioCharge.objects.filter(hotel=self.hotel).count()
        self.close_day()
        self.assertEqual(FolioCharge.objects.filter(hotel=self.hotel, type="room").count(), 0)
        self.assertEqual(FolioCharge.objects.filter(hotel=self.hotel).count(), before)

    def test_close_does_not_recompute_tax(self):
        from apps.finance.services import add_charge

        folio = create_folio(self.hotel, customer_name="W")
        charge = add_charge(
            folio, charge_type="service", description="svc",
            quantity=1, unit_amount="100.00", tax_rate="10.00", user=self.manager,
        )
        tax_before = charge.tax_amount
        self.close_day()
        charge.refresh_from_db()
        self.assertEqual(charge.tax_amount, tax_before)

    # --- Operations: overdue departure is a warning ----------------------

    def test_overdue_departure_is_warning_and_unchanged(self):
        from django.utils import timezone as dj_tz

        from apps.guests.models import Guest
        from apps.rooms.models import Floor, Room, RoomType
        from apps.stays.models import Stay, StayStatus

        rt = RoomType.objects.create(
            hotel=self.hotel, name="Std", code="STD", base_capacity=2, max_capacity=2
        )
        floor = Floor.objects.create(hotel=self.hotel, name="G", number="0")
        room = Room.objects.create(hotel=self.hotel, floor=floor, room_type=rt, number="101")
        guest = Guest.objects.create(hotel=self.hotel, full_name="Guest")
        stay = Stay.objects.create(
            hotel=self.hotel, room=room, primary_guest=guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=self.today - timedelta(days=2),
            planned_check_out_date=self.today,
            actual_check_in_at=dj_tz.now(),
        )
        prep = self.prepare()
        self.assertTrue(prep.data["can_close"])
        self.assertIn("overdue_departures", [w["code"] for w in prep.data["warnings"]])
        r = self.close_day()
        self.assertEqual(r.status_code, 200)
        stay.refresh_from_db()
        self.assertEqual(stay.status, StayStatus.IN_HOUSE)

    # --- Print / permissions / isolation / reopen ------------------------

    def test_statement_reads_stored_snapshot(self):
        self.close_day()
        dc = DailyClose.objects.get(hotel=self.hotel, business_date=self.today)
        r = self.client.get(
            reverse("shifts:daily-close-statement", args=[dc.id]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["document"], "daily_close_statement")
        self.assertIn("snapshot_json", r.data["close"])
        self.assertEqual(
            r.data["close"]["snapshot_json"]["identity"]["business_date"], str(self.today)
        )

    def test_statement_requires_view_permission(self):
        self.close_day()
        dc = DailyClose.objects.get(hotel=self.hotel, business_date=self.today)
        staff = add_member(self.hotel, "noview@x.com", perms=["shifts.view"])
        self.client.force_authenticate(staff)
        r = self.client.get(
            reverse("shifts:daily-close-statement", args=[dc.id]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 403)

    def test_view_only_cannot_prepare_or_close(self):
        viewer = add_member(self.hotel, "v@x.com", perms=["daily_close.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(self.prepare().status_code, 403)
        self.assertEqual(self.close_day().status_code, 403)

    def test_isolation_between_hotels(self):
        other = make_hotel(slug="o2")
        HotelSettings.objects.create(
            hotel=other, default_currency="USD", timezone="UTC", business_date=self.today
        )
        self.close_day()
        osettings = HotelSettings.objects.get(hotel=other)
        self.assertEqual(osettings.business_date, self.today)
        self.assertEqual(DailyClose.objects.filter(hotel=other).count(), 0)

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


# --------------------------------------------------------------------------- #
# Shifts final closure round                                                   #
# --------------------------------------------------------------------------- #

from apps.notifications.models import ActivityEvent


class ClosureBase(APITestCase, ShiftsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def _types(self, hotel=None):
        return set(
            ActivityEvent.objects.filter(hotel=hotel or self.hotel).values_list(
                "event_type", flat=True
            )
        )


class ClosedShiftReadOnlyTests(ClosureBase):
    def test_open_shift_still_editable(self):
        shift = self.open_shift().data
        r = self.client.patch(
            reverse("shifts:shift-detail", args=[shift["id"]]),
            {"internal_notes": "while open", "opening_notes": "float ok"},
            format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["internal_notes"], "while open")

    def test_closed_shift_rejects_every_field(self):
        shift = self.open_shift().data
        self.close_shift(shift["id"], "100.00")
        for payload in (
            {"internal_notes": "x"}, {"opening_notes": "x"},
            {"opening_cash_amount": "5.00"},
        ):
            r = self.client.patch(
                reverse("shifts:shift-detail", args=[shift["id"]]),
                payload, format="json", **HDR(self.hotel),
            )
            self.assertEqual(r.status_code, 409, payload)
            self.assertEqual(r.data["code"], "operation_not_editable")

    def test_cancelled_shift_rejects_every_field(self):
        shift = self.open_shift().data
        self.act("shift-cancel", shift["id"], {"reason": "mistake"})
        r = self.client.patch(
            reverse("shifts:shift-detail", args=[shift["id"]]),
            {"internal_notes": "x"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "operation_not_editable")


class ClosureActivityTests(ClosureBase):
    def test_shift_opened_and_cancelled_events(self):
        shift = self.open_shift().data
        self.assertIn("shift.opened", self._types())
        self.act("shift-cancel", shift["id"], {"reason": "opened by mistake"})
        types = self._types()
        self.assertIn("shift.cancelled", types)
        ev = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="shift.cancelled"
        ).latest("id")
        self.assertIn("opened by mistake", ev.message)

    def test_handover_lifecycle_events(self):
        # opener + recipient
        shift = self.open_shift().data
        recipient = add_member(self.hotel, "rec@x.com", perms=["shifts.view", "shifts.accept_handover"])
        rec_m = recipient
        h = self.client.post(
            reverse("shifts:handover-list"),
            {"from_shift": shift["id"], "to_user": recipient.id, "summary_notes": "all good"},
            format="json", **HDR(self.hotel),
        ).data
        self.act("handover-submit", h["id"])
        self.assertIn("handover.submitted", self._types())
        # accept as recipient
        self.client.force_authenticate(recipient)
        self.act("handover-accept", h["id"], {"note": "received"})
        self.assertIn("handover.accepted", self._types())

    def test_handover_reject_and_cancel_events(self):
        shift = self.open_shift().data
        recipient = add_member(self.hotel, "rec2@x.com", perms=["shifts.view", "shifts.accept_handover"])
        # reject path
        h1 = self.client.post(
            reverse("shifts:handover-list"),
            {"from_shift": shift["id"], "to_user": recipient.id}, format="json", **HDR(self.hotel),
        ).data
        self.act("handover-submit", h1["id"])
        self.client.force_authenticate(recipient)
        self.act("handover-reject", h1["id"], {"reason": "wrong recipient"})
        self.assertIn("handover.rejected", self._types())
        # cancel path (manager cancels a draft)
        self.client.force_authenticate(self.manager)
        h2 = self.client.post(
            reverse("shifts:handover-list"),
            {"from_shift": shift["id"], "to_user": recipient.id}, format="json", **HDR(self.hotel),
        ).data
        self.act("handover-cancel", h2["id"], {"reason": "not needed"})
        self.assertIn("handover.cancelled", self._types())

    def test_closed_event_still_present(self):
        shift = self.open_shift().data
        self.close_shift(shift["id"], "100.00")
        self.assertIn("shift.closed", self._types())


class ShiftPrintTests(ClosureBase):
    def test_shift_statement(self):
        shift = self.open_shift(opening_cash_amount="100.00").data
        # take a cash payment so the drawer moves
        folio = create_folio(self.hotel, customer_name="W", user=self.manager)
        record_payment(folio, amount="40.00", method=PaymentMethod.CASH, user=self.manager)
        self.close_shift(shift["id"], "140.00")
        r = self.client.get(
            reverse("shifts:shift-statement", args=[shift["id"]]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["document"], "shift_statement")
        self.assertIn("hotel_name", r.data["hotel"])
        self.assertEqual(r.data["cash_summary"]["expected_cash"], "140.00")
        self.assertEqual(r.data["shift"]["actual_cash_amount"], "140.00")
        self.assertEqual(r.data["shift"]["cash_difference"], "0.00")

    def test_handover_voucher(self):
        shift = self.open_shift().data
        recipient = add_member(self.hotel, "rv@x.com", perms=["shifts.view"])
        h = self.client.post(
            reverse("shifts:handover-list"),
            {"from_shift": shift["id"], "to_user": recipient.id,
             "summary_notes": "night notes", "pending_tasks_notes": "restock"},
            format="json", **HDR(self.hotel),
        ).data
        r = self.client.get(
            reverse("shifts:handover-voucher", args=[h["id"]]), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["document"], "handover_voucher")
        self.assertEqual(r.data["handover"]["summary_notes"], "night notes")

    def test_print_requires_view_permission(self):
        shift = self.open_shift().data
        staff = add_member(self.hotel, "noview@x.com")  # no shifts.view
        self.client.force_authenticate(staff)
        self.assertEqual(
            self.client.get(
                reverse("shifts:shift-statement", args=[shift["id"]]), **HDR(self.hotel)
            ).status_code, 403,
        )
        viewer = add_member(self.hotel, "viewer@x.com", perms=["shifts.view"])
        self.client.force_authenticate(viewer)
        self.assertEqual(
            self.client.get(
                reverse("shifts:shift-statement", args=[shift["id"]]), **HDR(self.hotel)
            ).status_code, 200,
        )

    def test_print_hotel_isolated(self):
        shift = self.open_shift().data
        other = make_hotel(slug="other")
        add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        om = User.objects.get(email="om@x.com")
        self.client.force_authenticate(om)
        r = self.client.get(
            reverse("shifts:shift-statement", args=[shift["id"]]), **HDR(other)
        )
        self.assertEqual(r.status_code, 404)
