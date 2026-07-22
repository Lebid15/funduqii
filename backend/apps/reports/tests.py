"""Tests for reports & analytics (Phase 13) — READ-ONLY aggregation.

Covers access per permission section, tenant isolation, the suspended-hotel
read rule, date-range validation, the occupancy derivation from stays (never
Room.status), Decimal-only finance math with voided records excluded, the
"cashflow not profit" naming, CSV export gating, and regression.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.finance.models import (
    ChargeType,
    Expense,
    ExpenseType,
    Folio,
    Payment,
    PaymentMethod,
    PostingStatus,
    normalize_expense_type_name,
)
from apps.finance.services import (
    add_charge,
    create_expense,
    create_folio,
    record_payment,
    void_payment,
)
from apps.guests.models import Guest
from apps.hotels.models import HotelSettings
from apps.notifications.models import ActivityEvent
from apps.rbac.services import grant_permission
from apps.reservations.models import Reservation, ReservationStatus
from apps.rooms.models import Floor, Room, RoomStatus, RoomType
from apps.shifts.models import DailyClose, DailyCloseStatus
from apps.shifts.services import close_business_day, get_business_date, open_shift, close_shift
from apps.stays.models import Stay, StayStatus
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

HDR = lambda h: {"HTTP_X_HOTEL_ID": str(h.id)}  # noqa: E731

STRONG = "StrongPass!234"


def make_hotel(slug="hotel", status=HotelStatus.ACTIVE):
    return Hotel.objects.create(name="Hotel", slug=slug, status=status)


def expense_type(hotel, name="Supplies"):
    """EXPENSES-CLOSURE: new expenses reference a manageable ExpenseType instead
    of the legacy fixed ``category`` enum. Idempotent per (hotel, normalized name)."""
    et, _ = ExpenseType.objects.get_or_create(
        hotel=hotel,
        name_normalized=normalize_expense_type_name(name),
        defaults={"name": name},
    )
    return et


def add_member(hotel, email, *, kind=MembershipType.STAFF, perms=()):
    user = User.objects.create_user(email=email, password=STRONG, full_name="Member")
    m = HotelMembership.objects.create(
        user=user, hotel=hotel, membership_type=kind, is_active=True
    )
    for code in perms:
        grant_permission(m, code)
    return user


def make_room(hotel, number="101", status=RoomStatus.AVAILABLE):
    floor = Floor.objects.create(hotel=hotel, name="G", number="0")
    rt = RoomType.objects.create(
        hotel=hotel, name="Std", code=f"S{number}", base_capacity=2, max_capacity=2
    )
    return Room.objects.create(
        hotel=hotel, floor=floor, room_type=rt, number=number, status=status
    )


def make_stay(hotel, room, *, days_ago_in=1, days_ago_out=None):
    guest = Guest.objects.create(
        hotel=hotel, full_name=f"G{room.number}", nationality="SY",
        email=f"g{room.number}@x.com",
    )
    now = timezone.now()
    stay = Stay.objects.create(
        hotel=hotel,
        room=room,
        primary_guest=guest,
        status=StayStatus.CHECKED_OUT if days_ago_out is not None else StayStatus.IN_HOUSE,
        planned_check_in_date=(now - datetime.timedelta(days=days_ago_in)).date(),
        planned_check_out_date=now.date(),
        actual_check_in_at=now - datetime.timedelta(days=days_ago_in),
        actual_check_out_at=(
            now - datetime.timedelta(days=days_ago_out) if days_ago_out is not None else None
        ),
    )
    return stay


def make_reservation(hotel, status=ReservationStatus.CONFIRMED, **kw):
    today = timezone.localdate()
    defaults = dict(
        hotel=hotel,
        reservation_number=f"RES{Reservation.objects.count() + 1:05d}",
        status=status,
        primary_guest_name="John Guest",
        check_in_date=today,
        check_out_date=today + datetime.timedelta(days=2),
    )
    defaults.update(kw)
    return Reservation.objects.create(**defaults)


class ReportsMixin:
    def get_report(self, name, hotel=None, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = reverse(f"reports:{name}") + (f"?{query}" if query else "")
        return self.client.get(url, **HDR(hotel or self.hotel))


# --------------------------------------------------------------------------- #
# Access / permissions                                                          #
# --------------------------------------------------------------------------- #


class AccessTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)

    def test_unauthenticated_denied(self):
        self.assertEqual(self.get_report("overview").status_code, 401)

    def test_no_membership_denied(self):
        lonely = User.objects.create_user(email="l@x.com", password=STRONG, full_name="L")
        self.client.force_authenticate(lonely)
        self.assertEqual(self.get_report("overview").status_code, 403)

    def test_platform_owner_without_membership_denied(self):
        owner = User.objects.create_user(email="p@x.com", password=STRONG, full_name="P")
        owner.account_type = AccountType.PLATFORM_OWNER
        owner.save(update_fields=["account_type"])
        self.client.force_authenticate(owner)
        self.assertEqual(self.get_report("overview").status_code, 403)

    def test_manager_can_view_all_reports(self):
        self.client.force_authenticate(self.manager)
        for name in (
            "overview", "reservations", "occupancy", "guests", "finance",
            "services", "operations", "shifts", "daily-close",
        ):
            self.assertEqual(self.get_report(name).status_code, 200, name)

    def test_staff_without_reports_view_denied(self):
        worker = add_member(self.hotel, "w@x.com", perms=["rooms.view"])
        self.client.force_authenticate(worker)
        self.assertEqual(self.get_report("overview").status_code, 403)

    def test_reports_view_unlocks_basic_only(self):
        viewer = add_member(self.hotel, "v@x.com", perms=["reports.view"])
        self.client.force_authenticate(viewer)
        for name in ("overview", "reservations", "occupancy", "guests", "services"):
            self.assertEqual(self.get_report(name).status_code, 200, name)
        for name in ("finance", "operations", "shifts", "daily-close"):
            self.assertEqual(self.get_report(name).status_code, 403, name)

    def test_section_permissions(self):
        fin = add_member(self.hotel, "f@x.com", perms=["reports.finance"])
        self.client.force_authenticate(fin)
        self.assertEqual(self.get_report("finance").status_code, 200)
        self.assertEqual(self.get_report("operations").status_code, 403)
        ops = add_member(self.hotel, "o@x.com", perms=["reports.operations"])
        self.client.force_authenticate(ops)
        self.assertEqual(self.get_report("operations").status_code, 200)
        self.assertEqual(self.get_report("shifts").status_code, 403)
        sh = add_member(self.hotel, "s@x.com", perms=["reports.shifts"])
        self.client.force_authenticate(sh)
        self.assertEqual(self.get_report("shifts").status_code, 200)
        self.assertEqual(self.get_report("daily-close").status_code, 200)
        self.assertEqual(self.get_report("finance").status_code, 403)

    def test_hotel_a_cannot_see_hotel_b_numbers(self):
        other = make_hotel(slug="o")
        make_reservation(other)
        room = make_room(other, "900")
        make_stay(other, room)
        self.client.force_authenticate(self.manager)
        data = self.get_report("overview").data
        self.assertEqual(data["reservations_count"], 0)
        self.assertEqual(data["in_house_count"], 0)
        self.assertEqual(data["rooms_total"], 0)

    def test_export_requires_export_permission(self):
        viewer = add_member(self.hotel, "ex@x.com", perms=["reports.view"])
        self.client.force_authenticate(viewer)
        r = self.client.get(
            reverse("reports:reservations-export"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 403)
        grant_permission(
            HotelMembership.objects.get(user=viewer, hotel=self.hotel), "reports.export"
        )
        r = self.client.get(
            reverse("reports:reservations-export"), **HDR(self.hotel)
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])

    def test_export_needs_underlying_section_too(self):
        # export + view but NOT finance -> payments export refused.
        viewer = add_member(
            self.hotel, "ex2@x.com", perms=["reports.view", "reports.export"]
        )
        self.client.force_authenticate(viewer)
        r = self.client.get(reverse("reports:payments-export"), **HDR(self.hotel))
        self.assertEqual(r.status_code, 403)

    def test_suspended_hotel_can_read_reports(self):
        hotel = make_hotel(slug="susp", status=HotelStatus.SUSPENDED)
        manager = add_member(hotel, "sm@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(manager)
        # Reports are read-only: reading AND CSV export stay allowed
        # (documented decision).
        self.assertEqual(self.get_report("overview", hotel=hotel).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("reports:reservations-export"), **HDR(hotel)
            ).status_code,
            200,
        )


# --------------------------------------------------------------------------- #
# Filters                                                                       #
# --------------------------------------------------------------------------- #


class FilterTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_from_after_to_rejected(self):
        r = self.get_report("overview", date_from="2026-07-10", date_to="2026-07-01")
        self.assertEqual(r.status_code, 400)

    def test_half_range_rejected(self):
        r = self.get_report("overview", date_from="2026-07-01")
        self.assertEqual(r.status_code, 400)

    def test_range_cap(self):
        r = self.get_report("overview", date_from="2024-01-01", date_to="2026-07-01")
        self.assertEqual(r.status_code, 400)

    def test_empty_range_returns_zeros(self):
        r = self.get_report("overview", date_from="2020-01-01", date_to="2020-01-31")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["reservations_count"], 0)
        # Financial totals moved to finance-overview (reports.finance).
        fin = self.get_report(
            "finance-overview", date_from="2020-01-01", date_to="2020-01-31"
        )
        self.assertEqual(fin.data["net_payments"], "0.00")
        self.assertEqual(fin.data["net_cashflow"], "0.00")

    def test_default_range_is_current_month(self):
        r = self.get_report("overview")
        today = get_business_date(self.hotel)
        self.assertEqual(r.data["date_from"], str(today.replace(day=1)))
        self.assertEqual(r.data["date_to"], str(today))


# --------------------------------------------------------------------------- #
# Overview / reservations / occupancy / guests                                  #
# --------------------------------------------------------------------------- #


class OverviewTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.room = make_room(self.hotel, "101")

    def test_counts_and_cashflow(self):
        make_reservation(self.hotel)
        make_reservation(self.hotel, status=ReservationStatus.CANCELLED)
        make_stay(self.hotel, self.room)  # in-house arrival today-1
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="100.00", method=PaymentMethod.CASH, user=self.manager)
        create_expense(
            self.hotel, expense_type=expense_type(self.hotel), description="Soap",
            amount="30.00", method=PaymentMethod.CASH, user=self.manager,
        )
        data = self.get_report("overview").data
        self.assertEqual(data["reservations_count"], 2)
        self.assertEqual(data["confirmed_reservations_count"], 1)
        self.assertEqual(data["cancelled_reservations_count"], 1)
        self.assertEqual(data["arrivals_count"], 1)
        self.assertEqual(data["in_house_count"], 1)
        # Financial totals live in finance-overview (reports.finance), not the
        # operational overview (leak fix, final closure).
        self.assertNotIn("total_payments", data)
        fin = self.get_report("finance-overview").data
        self.assertEqual(fin["net_payments"], "100.00")
        self.assertEqual(fin["net_expenses"], "30.00")
        self.assertEqual(fin["net_cashflow"], "70.00")
        # The word "profit" must never appear in the payload.
        self.assertNotIn("profit", str(fin).lower())

    def test_room_status_counts(self):
        make_room(self.hotel, "102", status=RoomStatus.DIRTY)
        make_room(self.hotel, "103", status=RoomStatus.MAINTENANCE)
        data = self.get_report("overview").data
        self.assertEqual(data["rooms_total"], 3)
        self.assertEqual(data["rooms_available"], 1)
        self.assertEqual(data["rooms_dirty"], 1)
        self.assertEqual(data["rooms_maintenance"], 1)


class ReservationsReportTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_aggregations(self):
        make_reservation(self.hotel, source="phone", booking_kind="future")
        make_reservation(self.hotel, source="direct", booking_kind="instant")
        make_reservation(
            self.hotel, status=ReservationStatus.CANCELLED, booking_kind="instant"
        )
        data = self.get_report("reservations").data
        by_status = {row["key"]: row["count"] for row in data["by_status"]}
        self.assertEqual(by_status["confirmed"], 2)
        self.assertEqual(by_status["cancelled"], 1)
        by_kind = {row["key"]: row["count"] for row in data["by_booking_kind"]}
        self.assertEqual(by_kind["instant"], 2)
        self.assertEqual(by_kind["future"], 1)
        self.assertEqual(data["average_nights"], "2.00")
        self.assertEqual(data["list"]["count"], 3)
        self.assertEqual(len(data["list"]["results"]), 3)


class OccupancyTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.room = make_room(self.hotel, "101")

    def test_occupancy_derived_from_stays_not_room_status(self):
        # The room stays `available` (manual status) while a stay is in-house:
        # occupancy MUST come from the stay interval, not the room status.
        make_stay(self.hotel, self.room, days_ago_in=2)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, RoomStatus.AVAILABLE)
        data = self.get_report("occupancy").data
        today = str(get_business_date(self.hotel))
        self.assertEqual(data["occupied_by_day"][today], 1)
        self.assertEqual(data["in_house_now"], 1)
        self.assertNotEqual(data["occupancy_rate"], "0.00")

    def test_no_occupied_room_status_exists(self):
        self.assertNotIn("occupied", {c for c, _ in RoomStatus.choices})
        data = self.get_report("occupancy").data
        self.assertNotIn("occupied", data["room_status_now"])

    def test_status_counts(self):
        make_room(self.hotel, "102", status=RoomStatus.OUT_OF_SERVICE)
        data = self.get_report("occupancy").data
        self.assertEqual(data["room_status_now"]["out_of_service"], 1)
        # Sellable capacity EXCLUDES out-of-service (and maintenance/archived)
        # per the central availability definition (final closure).
        self.assertEqual(data["rooms_capacity"], 1)


class GuestsReportTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_guest_aggregations(self):
        room = make_room(self.hotel, "101")
        stay = make_stay(self.hotel, room, days_ago_in=3, days_ago_out=1)
        # A second stay for the same guest -> repeat guest.
        room2 = make_room(self.hotel, "102")
        Stay.objects.create(
            hotel=self.hotel, room=room2, primary_guest=stay.primary_guest,
            status=StayStatus.IN_HOUSE,
            planned_check_in_date=timezone.localdate(),
            planned_check_out_date=timezone.localdate() + datetime.timedelta(days=1),
            actual_check_in_at=timezone.now(),
        )
        data = self.get_report("guests").data
        # One guest profile (the second stay reuses it) -> new_guests = 1.
        self.assertEqual(data["new_guests_count"], 1)
        self.assertEqual(data["repeat_guests_count"], 1)
        self.assertEqual(data["current_residents_count"], 1)
        self.assertEqual(data["checked_out_count"], 1)
        self.assertTrue(any(row["key"] == "SY" for row in data["by_nationality"]))


# --------------------------------------------------------------------------- #
# Finance / services / operations / shifts                                      #
# --------------------------------------------------------------------------- #


class FinanceReportTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.folio = create_folio(self.hotel, customer_name="W")

    def test_totals_by_method_and_voided_excluded(self):
        record_payment(self.folio, amount="100.00", method=PaymentMethod.CASH, user=self.manager)
        record_payment(self.folio, amount="40.00", method=PaymentMethod.CARD, user=self.manager)
        voided = record_payment(
            self.folio, amount="999.00", method=PaymentMethod.CASH, user=self.manager
        )
        void_payment(voided, reason="entry error", user=self.manager)
        create_expense(
            self.hotel, expense_type=expense_type(self.hotel), description="Soap",
            amount="25.00", method=PaymentMethod.CASH, user=self.manager,
        )
        data = self.get_report("finance").data
        methods = {row["key"]: row for row in data["payments_by_method"]}
        self.assertEqual(methods["cash"]["total"], "100.00")
        self.assertEqual(methods["card"]["total"], "40.00")
        self.assertEqual(data["total_payments"], "140.00")
        self.assertEqual(data["total_expenses"], "25.00")
        self.assertEqual(data["net_cashflow_simple"], "115.00")
        self.assertEqual(data["voided"]["payments"], 1)
        self.assertNotIn("profit", str(data).lower())
        # Money is serialized as strings (Decimal-safe), never float.
        self.assertIsInstance(data["total_payments"], str)

    def test_expenses_grouped_by_manageable_type_name(self):
        """EXPENSES-CLOSURE: the expense breakdown keys on the MANAGEABLE type's
        NAME (not the legacy category enum), while the money totals are
        unchanged. Without this the grouping-key change is unprotected."""
        create_expense(
            self.hotel, expense_type=expense_type(self.hotel, name="Utilities"),
            description="Power", amount="30.00", method=PaymentMethod.CASH,
            user=self.manager,
        )
        create_expense(
            self.hotel, expense_type=expense_type(self.hotel, name="Supplies"),
            description="Soap", amount="20.00", method=PaymentMethod.CASH,
            user=self.manager,
        )
        data = self.get_report("finance").data
        rows = {row["key"]: row["total"] for row in data["expenses_by_category"]}
        self.assertEqual(rows["Utilities"], "30.00")
        self.assertEqual(rows["Supplies"], "20.00")
        # The legacy enum value is no longer the grouping key.
        self.assertNotIn("utilities", rows)
        self.assertNotIn("supplies", rows)
        # Money is unaffected by the key change.
        self.assertEqual(data["total_expenses"], "50.00")

    def test_per_day_series(self):
        record_payment(self.folio, amount="10.00", method=PaymentMethod.CASH, user=self.manager)
        data = self.get_report("finance").data
        self.assertEqual(len(data["payments_by_day"]), 1)
        self.assertEqual(data["payments_by_day"][0]["total"], "10.00")


class ServicesReportTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_orders_aggregation(self):
        from apps.services.models import ServiceCategory, ServiceItem
        from apps.services.services import create_order, change_status, post_order_to_folio

        category = ServiceCategory.objects.create(hotel=self.hotel, name="Cafe")
        item = ServiceItem.objects.create(
            hotel=self.hotel, category=category, name="Tea",
            unit_price=Decimal("10.00"),
        )
        stay = make_stay(self.hotel, make_room(self.hotel, "101"))
        order = create_order(
            self.hotel, user=self.manager, order_type="room",
            outlet="restaurant", stay=stay,
            items_data=[{"service_item": item, "quantity": 2}],
        )
        change_status(order, new_status="delivered", user=self.manager)
        post_order_to_folio(order, user=self.manager)
        data = self.get_report("services").data
        self.assertEqual(data["orders_count"], 1)
        self.assertEqual(data["delivered_posted"], 1)
        self.assertEqual(data["delivered_unposted"], 0)
        self.assertEqual(data["posted_to_folio_total"], "20.00")
        self.assertEqual(data["top_items"][0]["key"], "Tea")


class OperationsReportTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_operations_aggregation(self):
        from apps.operations.services import (
            create_housekeeping_task,
            create_lost_found_item,
            create_maintenance_request,
        )

        room = make_room(self.hotel, "101", status=RoomStatus.DIRTY)
        create_housekeeping_task(
            self.hotel, user=self.manager, room=room, priority="urgent"
        )
        create_maintenance_request(
            self.hotel, user=self.manager, room=room, title="AC",
            category="hvac", priority="normal",
        )
        create_lost_found_item(
            self.hotel, user=self.manager, title="Wallet", category="documents"
        )
        data = self.get_report("operations").data
        hk = {row["key"]: row["count"] for row in data["housekeeping_by_status"]}
        self.assertEqual(hk["pending"], 1)
        mt_cat = {row["key"]: row["count"] for row in data["maintenance_by_category"]}
        self.assertEqual(mt_cat["hvac"], 1)
        lf = {row["key"]: row["count"] for row in data["lost_found_by_status"]}
        self.assertEqual(lf["found"], 1)
        self.assertEqual(data["urgent_open_count"], 1)


class ShiftsReportTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_shifts_and_daily_close(self):
        shift = open_shift(
            self.hotel, user=self.manager, opening_cash_amount=Decimal("100.00")
        )
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager)
        close_shift(
            shift, user=self.manager, actual_cash_amount=Decimal("140.00"),
            difference_reason="shortage",
        )
        close_business_day(self.hotel, get_business_date(self.hotel), user=self.manager)
        data = self.get_report("shifts").data
        by_status = {row["key"]: row["count"] for row in data["shifts_by_status"]}
        self.assertEqual(by_status["closed"], 1)
        self.assertEqual(data["shifts_with_difference"], 1)
        self.assertEqual(data["total_expected_cash"], "150.00")
        self.assertEqual(data["total_actual_cash"], "140.00")
        self.assertEqual(data["total_cash_difference"], "-10.00")
        self.assertEqual(data["closed_days_count"], 1)
        listed = self.get_report("daily-close").data
        self.assertEqual(listed["count"], 1)
        detail = self.client.get(
            reverse(
                "reports:daily-close-detail",
                args=[str(get_business_date(self.hotel))],
            ),
            **HDR(self.hotel),
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["status"], "closed")
        self.assertIn("payments", detail.data["snapshot"])


# --------------------------------------------------------------------------- #
# Export & regression                                                           #
# --------------------------------------------------------------------------- #


class ExportTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_reservations_csv_respects_filters_and_isolation(self):
        make_reservation(self.hotel)
        other = make_hotel(slug="o")
        make_reservation(other, reservation_number="FOREIGN01")
        r = self.client.get(reverse("reports:reservations-export"), **HDR(self.hotel))
        body = r.content.decode()
        self.assertIn("RES", body)
        self.assertNotIn("FOREIGN01", body)
        # Out-of-range export is empty (header only), never a 500.
        r = self.client.get(
            reverse("reports:reservations-export")
            + "?date_from=2020-01-01&date_to=2020-01-31",
            **HDR(self.hotel),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.content.decode().strip().splitlines()), 1)

    def test_csv_has_no_sensitive_columns(self):
        r = self.client.get(reverse("reports:payments-export"), **HDR(self.hotel))
        header = r.content.decode().splitlines()[0].lower()
        for forbidden in ("password", "token", "secret", "email"):
            self.assertNotIn(forbidden, header)


class RegressionTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_health_still_works(self):
        self.client.force_authenticate()
        self.assertEqual(self.client.get("/api/health/").status_code, 200)

    def test_existing_phase_endpoints_reachable(self):
        for name in (
            "rooms:room-list", "reservations:reservation-list", "guests:guest-list",
            "stays:stay-list", "finance:folio-list", "services:order-list",
            "operations:housekeeping-list", "staff:staff-list", "shifts:shift-list",
        ):
            self.assertEqual(
                self.client.get(reverse(name), **HDR(self.hotel)).status_code, 200, name
            )

    def test_reports_are_get_only(self):
        r = self.client.post(reverse("reports:overview"), {}, **HDR(self.hotel))
        self.assertEqual(r.status_code, 405)

    def test_no_out_of_scope_endpoints(self):
        for name in ("scheduled", "designer", "email-export", "bi"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"reports:{name}")


# --------------------------------------------------------------------------- #
# Finance & Reports final closure — the unified business_date engine            #
# --------------------------------------------------------------------------- #


class FinanceEngineTests(APITestCase, ReportsMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.settings = HotelSettings.objects.create(
            hotel=self.hotel, default_currency="USD", timezone="UTC"
        )
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.today = get_business_date(self.hotel)
        self.settings.business_date = self.today
        self.settings.save(update_fields=["business_date"])
        self.hotel = Hotel.objects.get(pk=self.hotel.pk)

    def fresh(self):
        return Hotel.objects.get(pk=self.hotel.pk)

    def rng(self, d=None):
        d = d or self.today
        return {"date_from": str(d), "date_to": str(d)}

    # --- permissions / leak -------------------------------------------------

    def test_finance_reports_require_finance_perm(self):
        viewer = add_member(self.hotel, "v@x.com", perms=["reports.view"])
        self.client.force_authenticate(viewer)
        for name in ("finance-overview", "revenue", "payments", "expenses",
                     "taxes", "folio-balances", "restaurant-cafe"):
            self.assertEqual(self.get_report(name, **self.rng()).status_code, 403, name)
        self.assertEqual(self.get_report("comparisons").status_code, 403)

    def test_operational_overview_hides_financials(self):
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager)
        data = self.get_report("overview", **self.rng()).data
        for k in ("total_payments", "total_expenses", "net_cashflow_simple"):
            self.assertNotIn(k, data)

    # --- business_date keying ----------------------------------------------

    def test_finance_keyed_by_business_date_not_paid_at(self):
        folio = create_folio(self.hotel, customer_name="W")
        p = record_payment(folio, amount="70.00", method=PaymentMethod.CASH, user=self.manager)
        Payment.objects.filter(pk=p.pk).update(
            business_date=self.today - datetime.timedelta(days=1)
        )
        d = self.get_report("finance-overview", **self.rng()).data
        self.assertEqual(d["net_payments"], "0.00")

    # --- revenue / tax ------------------------------------------------------

    def test_revenue_by_category_from_charges(self):
        folio = create_folio(self.hotel, customer_name="W")
        add_charge(folio, charge_type=ChargeType.ROOM, description="room",
                   quantity=1, unit_amount="120.00", room_night=self.today,
                   user=self.manager)
        add_charge(folio, charge_type=ChargeType.SERVICE, description="svc",
                   quantity=1, unit_amount="40.00", user=self.manager)
        rev = self.get_report("revenue", **self.rng()).data
        self.assertEqual(rev["by_category"]["room"], "120.00")
        self.assertEqual(rev["by_category"]["services"], "40.00")
        self.assertEqual(rev["net_revenue"], "160.00")

    def test_tax_report_reads_stored_tax_amount(self):
        folio = create_folio(self.hotel, customer_name="W")
        add_charge(folio, charge_type=ChargeType.ROOM, description="r",
                   quantity=1, unit_amount="100.00", tax_rate="10.00",
                   room_night=self.today, user=self.manager)
        t = self.get_report("taxes", **self.rng()).data
        self.assertEqual(t["total_tax"], "10.00")
        self.assertEqual(t["net_revenue_ex_tax"], "100.00")

    def test_room_revenue_data_quality_when_no_room_charges(self):
        folio = create_folio(self.hotel, customer_name="W")
        add_charge(folio, charge_type=ChargeType.SERVICE, description="svc",
                   quantity=1, unit_amount="40.00", user=self.manager)
        d = self.get_report("finance-overview", **self.rng()).data
        self.assertEqual(d["kpis"]["room_revenue"], "0.00")
        self.assertFalse(d["data_quality"]["has_room_charges"])
        self.assertEqual(d["data_quality"]["room_revenue_source"], "manual_charges_only")
        self.assertEqual(d["adr"], "0.00")
        self.assertEqual(d["revpar"], "0.00")

    # --- payments / expenses reversals & voids -----------------------------

    def test_payments_reversals_separated(self):
        folio = create_folio(self.hotel, customer_name="W")
        orig = record_payment(folio, amount="80.00", method=PaymentMethod.CASH, user=self.manager)
        Payment.objects.create(
            hotel=self.hotel, folio=folio, receipt_number="RVU1",
            amount=Decimal("-80.00"), currency="USD", method=PaymentMethod.CASH,
            paid_at=orig.paid_at, business_date=self.today, reverses=orig,
        )
        p = self.get_report("payments", **self.rng()).data["payments"]
        self.assertEqual(p["gross"], "80.00")
        self.assertEqual(p["reversals"]["count"], 1)
        self.assertEqual(p["reversals"]["amount"], "-80.00")
        self.assertEqual(p["net"], "0.00")

    def test_expenses_reversals_separated(self):
        et = expense_type(self.hotel)
        e = create_expense(self.hotel, expense_type=et, description="x",
                           amount="20.00", method=PaymentMethod.CASH, user=self.manager)
        Expense.objects.create(
            hotel=self.hotel, expense_number="EXRU1", expense_type=et,
            category="supplies",
            description="rev", amount=Decimal("-20.00"), currency="USD",
            method=PaymentMethod.CASH, paid_at=e.paid_at, business_date=self.today,
            reverses=e,
        )
        exp = self.get_report("expenses", **self.rng()).data["expenses"]
        self.assertEqual(exp["gross"], "20.00")
        self.assertEqual(exp["reversals"]["count"], 1)
        self.assertEqual(exp["net"], "0.00")

    def test_voided_payment_excluded_and_counted(self):
        folio = create_folio(self.hotel, customer_name="W")
        p = record_payment(folio, amount="15.00", method=PaymentMethod.CASH, user=self.manager)
        void_payment(p, reason="mistake", user=self.manager)
        pay = self.get_report("payments", **self.rng()).data["payments"]
        self.assertEqual(pay["gross"], "0.00")
        self.assertEqual(pay["voided"]["count"], 1)

    # --- folio balances -----------------------------------------------------

    def test_folio_balances_buckets(self):
        folio = create_folio(self.hotel, customer_name="W")
        add_charge(folio, charge_type=ChargeType.SERVICE, description="s",
                   quantity=1, unit_amount="200.00", user=self.manager)
        d = self.get_report("folio-balances", **self.rng()).data
        self.assertEqual(d["open_folios_count"], 1)
        self.assertEqual(d["positive_balance_count"], 1)
        self.assertEqual(d["positive_balance_amount"], "200.00")

    def test_restaurant_cafe_report_shape(self):
        d = self.get_report("restaurant-cafe", **self.rng()).data
        for k in ("restaurant_sales", "cafe_sales", "direct_settlements",
                  "folio_postings", "open_orders_count", "cancelled_orders_count"):
            self.assertIn(k, d)

    # --- KPIs ---------------------------------------------------------------

    def test_adr_revpar_from_actuals(self):
        room = make_room(self.hotel, "201")
        make_stay(self.hotel, room, days_ago_in=0)
        folio = create_folio(self.hotel, customer_name="W")
        add_charge(folio, charge_type=ChargeType.ROOM, description="r",
                   quantity=1, unit_amount="150.00", room_night=self.today,
                   user=self.manager)
        d = self.get_report("finance-overview", **self.rng()).data
        self.assertEqual(d["kpis"]["room_revenue"], "150.00")
        self.assertEqual(d["adr"], "150.00")
        self.assertEqual(d["revpar"], "150.00")
        self.assertEqual(d["occupancy"], "100.00")

    def test_occupancy_excludes_blocked_rooms(self):
        make_room(self.hotel, "301")
        make_room(self.hotel, "302", status=RoomStatus.MAINTENANCE)
        make_room(self.hotel, "303", status=RoomStatus.OUT_OF_SERVICE)
        occ = self.get_report("occupancy", **self.rng()).data
        self.assertEqual(occ["rooms_capacity"], 1)

    def test_adr_revpar_zero_guard(self):
        d = self.get_report("finance-overview", **self.rng()).data
        self.assertEqual(d["adr"], "0.00")
        self.assertEqual(d["revpar"], "0.00")
        self.assertEqual(d["occupancy"], "0.00")

    # --- open vs closed vs mixed -------------------------------------------

    def test_closed_day_read_from_snapshot(self):
        folio = create_folio(self.hotel, customer_name="W")
        add_charge(folio, charge_type=ChargeType.ROOM, description="r",
                   quantity=1, unit_amount="90.00", room_night=self.today,
                   user=self.manager)
        record_payment(folio, amount="90.00", method=PaymentMethod.CASH, user=self.manager)
        close_business_day(self.fresh(), self.today, user=self.manager)
        d = self.get_report(
            "finance-overview", date_from=str(self.today), date_to=str(self.today)
        ).data
        self.assertEqual(d["source_status"], "snapshot")
        self.assertEqual(d["revenue"]["room"], "90.00")
        self.assertEqual(d["net_payments"], "90.00")

    def test_closed_day_snapshot_is_stable(self):
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="50.00", method=PaymentMethod.CASH, user=self.manager)
        close_business_day(self.fresh(), self.today, user=self.manager)
        rng = {"date_from": str(self.today), "date_to": str(self.today)}
        before = self.get_report("finance-overview", **rng).data["net_payments"]
        f2 = create_folio(self.fresh(), customer_name="W2")
        record_payment(f2, amount="999.00", method=PaymentMethod.CASH, user=self.manager)
        after = self.get_report("finance-overview", **rng).data["net_payments"]
        self.assertEqual(before, "50.00")
        self.assertEqual(after, "50.00")

    def test_days_missing_close_flagged(self):
        past = self.today - datetime.timedelta(days=3)
        d = self.get_report(
            "finance-overview", date_from=str(past), date_to=str(self.today)
        ).data
        self.assertIn(str(past), d["days_missing_close"])
        self.assertEqual(d["source_status"], "live")

    # --- comparisons --------------------------------------------------------

    def test_comparisons_minimal_with_zero_guard(self):
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="60.00", method=PaymentMethod.CASH, user=self.manager)
        d = self.get_report("comparisons").data
        self.assertIn("day_vs_previous", d)
        self.assertIn("mtd_vs_previous_month", d)
        self.assertEqual(d["day_vs_previous"]["net_payments"]["current"], "60.00")
        self.assertEqual(d["day_vs_previous"]["net_payments"]["previous"], "0.00")
        self.assertIsNone(d["day_vs_previous"]["net_payments"]["delta_pct"])

    # --- export / logging / isolation / no-write ---------------------------

    def test_csv_export_has_utf8_bom(self):
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="10.00", method=PaymentMethod.CASH, user=self.manager)
        r = self.client.get(reverse("reports:payments-export"), **HDR(self.hotel))
        self.assertTrue(r.content.startswith(b"\xef\xbb\xbf"))

    def test_financial_export_is_logged(self):
        before = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="report.exported"
        ).count()
        self.client.get(reverse("reports:payments-export"), **HDR(self.hotel))
        after = ActivityEvent.objects.filter(
            hotel=self.hotel, event_type="report.exported"
        ).count()
        self.assertEqual(after, before + 1)

    def test_finance_isolation(self):
        folio = create_folio(self.hotel, customer_name="W")
        record_payment(folio, amount="40.00", method=PaymentMethod.CASH, user=self.manager)
        other = make_hotel(slug="ofin")
        HotelSettings.objects.create(
            hotel=other, default_currency="USD", timezone="UTC", business_date=self.today
        )
        om = add_member(other, "om@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(om)
        d = self.get_report("finance-overview", hotel=other, **self.rng()).data
        self.assertEqual(d["net_payments"], "0.00")

    def test_reports_do_not_write(self):
        before = {m.__name__: m.objects.count() for m in (Payment, DailyClose, Folio)}
        for name in ("finance-overview", "revenue", "payments", "expenses",
                     "taxes", "folio-balances", "restaurant-cafe"):
            self.get_report(name, **self.rng())
        self.get_report("comparisons")
        after = {m.__name__: m.objects.count() for m in (Payment, DailyClose, Folio)}
        self.assertEqual(before, after)
