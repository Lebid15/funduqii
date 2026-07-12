"""Report API views (Phase 13), under /api/v1/hotel/reports/ — READ-ONLY.

Scoped to the caller's hotel, guarded by ``reports.*`` permissions. There are
no write operations in this app, so a SUSPENDED hotel may read every report
its permissions allow — including CSV export, which is read-only by nature
(documented decision).
"""
from __future__ import annotations

import csv
import datetime

from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.models import Payment, PostingStatus
from apps.rbac.permissions import HasHotelPermission
from apps.reservations.models import Reservation
from apps.shifts.models import DailyClose, Shift

from . import services

ReportsView = HasHotelPermission("reports.view")
ReportsFinance = HasHotelPermission("reports.finance")
ReportsOperations = HasHotelPermission("reports.operations")
ReportsShifts = HasHotelPermission("reports.shifts")
ReportsExport = HasHotelPermission("reports.export")

#: CSV rows are capped to keep exports safe and snappy (documented).
EXPORT_ROW_CAP = 5000


class RangeSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    page = serializers.IntegerField(required=False, min_value=1, default=1)

    def validate(self, data):
        date_from, date_to = data.get("date_from"), data.get("date_to")
        if (date_from is None) != (date_to is None):
            raise serializers.ValidationError(
                {"date_from": "Provide both date_from and date_to, or neither."}
            )
        if date_from is not None:
            if date_from > date_to:
                raise serializers.ValidationError(
                    {"date_from": "date_from must not be after date_to."}
                )
            if (date_to - date_from).days + 1 > services.MAX_RANGE_DAYS:
                raise serializers.ValidationError(
                    {"date_to": f"The range is limited to {services.MAX_RANGE_DAYS} days."}
                )
        return data


def _range(request: Request) -> tuple[datetime.date, datetime.date, int]:
    serializer = RangeSerializer(data=request.query_params.dict())
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if data.get("date_from") is None:
        date_from, date_to = services.default_range(request.hotel)
    else:
        date_from, date_to = data["date_from"], data["date_to"]
    return date_from, date_to, data["page"]


class OverviewReportView(APIView):
    permission_classes = [ReportsView]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.overview_report(request.hotel, date_from, date_to))


class ReservationsReportView(APIView):
    permission_classes = [ReportsView]

    def get(self, request: Request) -> Response:
        date_from, date_to, page = _range(request)
        return Response(
            services.reservations_report(request.hotel, date_from, date_to, page=page)
        )


class OccupancyReportView(APIView):
    permission_classes = [ReportsView]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.occupancy_report(request.hotel, date_from, date_to))


class GuestsReportView(APIView):
    permission_classes = [ReportsView]

    def get(self, request: Request) -> Response:
        date_from, date_to, page = _range(request)
        return Response(
            services.guests_report(request.hotel, date_from, date_to, page=page)
        )


class FinanceReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.finance_report(request.hotel, date_from, date_to))


class ServicesReportView(APIView):
    permission_classes = [ReportsView]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.services_report(request.hotel, date_from, date_to))


class OperationsReportView(APIView):
    permission_classes = [ReportsOperations]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.operations_report(request.hotel, date_from, date_to))


class ShiftsReportView(APIView):
    permission_classes = [ReportsShifts]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.shifts_report(request.hotel, date_from, date_to))


class DailyCloseReportListView(APIView):
    permission_classes = [ReportsShifts]

    def get(self, request: Request) -> Response:
        date_from, date_to, page = _range(request)
        return Response(
            services.daily_close_list(request.hotel, date_from, date_to, page=page)
        )


class DailyCloseReportDetailView(APIView):
    permission_classes = [ReportsShifts]

    def get(self, request: Request, business_date: str) -> Response:
        try:
            on_date = datetime.date.fromisoformat(business_date)
        except ValueError:
            raise NotFound("Invalid business date.")
        close = DailyClose.objects.filter(
            hotel=request.hotel, business_date=on_date
        ).select_related("closed_by").first()
        if close is None:
            raise NotFound("No daily close for this date.")
        return Response(
            {
                "id": close.id,
                "close_number": close.close_number,
                "business_date": str(close.business_date),
                "status": close.status,
                "closed_by": close.closed_by.full_name if close.closed_by else "",
                "closed_at": close.closed_at,
                "notes": close.notes,
                "snapshot": close.snapshot_json,
                "totals": close.totals_json,
            }
        )


# --- Finance reports (business_date-keyed, under reports.finance) ---------------


class FinanceOverviewView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.finance_overview(request.hotel, date_from, date_to))


class RevenueReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.revenue_report(request.hotel, date_from, date_to))


class PaymentsReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.payments_report(request.hotel, date_from, date_to))


class ExpensesReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.expenses_report(request.hotel, date_from, date_to))


class TaxReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.tax_report(request.hotel, date_from, date_to))


class FolioBalancesReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.folio_balances_report(request.hotel, date_from, date_to))


class RestaurantCafeReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        date_from, date_to, _ = _range(request)
        return Response(services.restaurant_cafe_report(request.hotel, date_from, date_to))


class ComparisonsReportView(APIView):
    permission_classes = [ReportsFinance]

    def get(self, request: Request) -> Response:
        return Response(services.comparisons_report(request.hotel))


# --- CSV export (simple, read-only, capped) -------------------------------------


def _csv_response(filename: str, header: list[str], rows) -> HttpResponse:
    # UTF-8 BOM so Excel renders Arabic correctly.
    response = HttpResponse("﻿", content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return response


def _log_financial_export(request: Request, report_id: str, date_from, date_to, row_count: int) -> None:
    """Audit trail for sensitive financial exports (owner decision). Only the
    export ACTION is logged — never the exported figures."""
    from apps.notifications.services import record_activity

    record_activity(
        request.hotel,
        event_type="report.exported",
        category="finance",
        severity="info",
        title=f"Financial report exported: {report_id}",
        message=f"{date_from} → {date_to} · csv · {row_count} rows",
        actor=request.user,
        related_url="/hotel/reports",
    )


class ReservationsExportView(APIView):
    permission_classes = [ReportsExport, ReportsView]

    def get(self, request: Request) -> HttpResponse:
        date_from, date_to, _ = _range(request)
        qs = Reservation.objects.filter(
            hotel=request.hotel, created_at__date__range=(date_from, date_to)
        ).order_by("-created_at")[:EXPORT_ROW_CAP]
        return _csv_response(
            f"reservations_{date_from}_{date_to}.csv",
            ["reservation_number", "guest_name", "status", "source",
             "booking_kind", "check_in_date", "check_out_date", "nights"],
            (
                [r.reservation_number, r.primary_guest_name, r.status, r.source,
                 r.booking_kind, r.check_in_date, r.check_out_date, r.nights]
                for r in qs
            ),
        )


class PaymentsExportView(APIView):
    permission_classes = [ReportsExport, ReportsFinance]

    def get(self, request: Request) -> HttpResponse:
        date_from, date_to, _ = _range(request)
        rows = list(
            Payment.objects.filter(
                services._pay_bd_range(date_from, date_to), hotel=request.hotel
            ).select_related("folio").order_by("-paid_at")[:EXPORT_ROW_CAP]
        )
        _log_financial_export(request, "payments", date_from, date_to, len(rows))
        return _csv_response(
            f"payments_{request.hotel.id}_{date_from}_{date_to}.csv",
            ["receipt_number", "folio_number", "business_date", "paid_at",
             "method", "status", "amount", "currency"],
            (
                [p.receipt_number, p.folio.folio_number,
                 (str(p.business_date) if p.business_date else ""),
                 p.paid_at.isoformat(), p.method, p.status, str(p.amount), p.currency]
                for p in rows
            ),
        )


class ShiftsExportView(APIView):
    permission_classes = [ReportsExport, ReportsShifts]

    def get(self, request: Request) -> HttpResponse:
        date_from, date_to, _ = _range(request)
        rows = list(
            Shift.objects.filter(
                hotel=request.hotel, business_date__range=(date_from, date_to)
            ).select_related("responsible_user").order_by("-opened_at")[:EXPORT_ROW_CAP]
        )
        _log_financial_export(request, "shifts", date_from, date_to, len(rows))
        return _csv_response(
            f"shifts_{request.hotel.id}_{date_from}_{date_to}.csv",
            ["shift_number", "business_date", "status", "responsible",
             "opening_cash", "expected_cash", "actual_cash", "cash_difference",
             "difference_reason"],
            (
                [s.shift_number, s.business_date, s.status,
                 s.responsible_user.full_name, str(s.opening_cash_amount),
                 str(s.expected_cash_amount),
                 str(s.actual_cash_amount) if s.actual_cash_amount is not None else "",
                 str(s.cash_difference), s.difference_reason]
                for s in rows
            ),
        )
