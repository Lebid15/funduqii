"""Shifts / handover / daily-close API views (Phase 12), under
/api/v1/hotel/shifts/.

Scoped to the caller's hotel, guarded by ``shifts.*`` / ``daily_close.*``
permissions. A suspended hotel is read-only. All mutations go through the
domain services; nothing here creates or mutates finance records.
"""
from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import (
    CrossTenantReference,
    PermissionDenied,
)
from apps.rbac.permissions import HasHotelMembership, HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .models import (
    DailyClose,
    DailyCloseStatus,
    HandoverStatus,
    Shift,
    ShiftHandover,
    ShiftStatus,
)
from .serializers import (
    DailyCloseActionSerializer,
    DailyCloseListSerializer,
    DailyCloseSerializer,
    HandoverCreateSerializer,
    HandoverListSerializer,
    HandoverSerializer,
    HandoverUpdateSerializer,
    NoteSerializer,
    ReasonSerializer,
    ShiftCloseSerializer,
    ShiftListSerializer,
    ShiftOpenSerializer,
    ShiftSerializer,
    ShiftUpdateSerializer,
)

User = get_user_model()

ShiftsView = HasHotelPermission("shifts.view")
ShiftsCreate = HasHotelPermission("shifts.create")
ShiftsUpdate = HasHotelPermission("shifts.update")
ShiftsClose = HasHotelPermission("shifts.close")
ShiftsCancel = HasHotelPermission("shifts.cancel")
ShiftsHandover = HasHotelPermission("shifts.handover")
ShiftsAcceptHandover = HasHotelPermission("shifts.accept_handover")

DailyCloseView = HasHotelPermission("daily_close.view")
DailyClosePrepare = HasHotelPermission("daily_close.prepare")
DailyCloseClose = HasHotelPermission("daily_close.close")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _get(model, request, pk):
    return generics.get_object_or_404(model, pk=pk, hotel=request.hotel)


def _resolve_user(user_id):
    if user_id is None:
        return None
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise CrossTenantReference({"field": "user"})
    return user


class CanViewShiftsOverview(HasHotelMembership):
    """ANY of the two view permissions unlocks the shared overview (the same
    any-of pattern as the operations overview — plain ``|`` composition would
    break because our permissions raise instead of returning False)."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        for code in ("shifts.view", "daily_close.view"):
            if has_hotel_permission(request.user, request.hotel, code):
                return True
        raise PermissionDenied()


# --- Overview / current --------------------------------------------------------


class ShiftsOverviewView(APIView):
    permission_classes = [CanViewShiftsOverview]

    def get(self, request: Request) -> Response:
        hotel = request.hotel
        today = services.get_business_date(hotel)
        shifts_today = Shift.objects.filter(hotel=hotel, business_date=today)
        open_shifts = Shift.objects.filter(hotel=hotel, status=ShiftStatus.OPEN)
        last_close = (
            DailyClose.objects.filter(hotel=hotel, status=DailyCloseStatus.CLOSED)
            .order_by("-business_date")
            .first()
        )
        today_close = DailyClose.objects.filter(
            hotel=hotel, business_date=today
        ).first()
        expected_total = sum(
            (services.shift_cash_summary(s)["expected_cash"] for s in open_shifts),
            services.ZERO,
        )
        actual_total = sum(
            (
                s.actual_cash_amount or services.ZERO
                for s in shifts_today.filter(status=ShiftStatus.CLOSED)
            ),
            services.ZERO,
        )
        unassigned = services.unassigned_movements(hotel, today)
        return Response(
            {
                "business_date": str(today),
                "open_shifts": open_shifts.count(),
                "today_shifts": shifts_today.count(),
                "pending_handovers": ShiftHandover.objects.filter(
                    hotel=hotel, status=HandoverStatus.SUBMITTED
                ).count(),
                "last_daily_close_date": (
                    str(last_close.business_date) if last_close else None
                ),
                "today_cash_expected": str(services.money(expected_total)),
                "today_cash_actual": str(services.money(actual_total)),
                "unassigned_movements": unassigned,
                "today_close_status": today_close.status if today_close else None,
            }
        )


class CurrentShiftView(APIView):
    permission_classes = [ShiftsView]

    def get(self, request: Request) -> Response:
        shift = services.get_open_shift_for(request.user, request.hotel)
        if shift is None:
            return Response({"shift": None})
        return Response(
            {
                "shift": ShiftSerializer(shift).data,
                "cash_summary": {
                    k: (str(v) if not isinstance(v, (int, dict)) else v)
                    for k, v in services.shift_cash_summary(shift).items()
                },
            }
        )


# --- Shifts ---------------------------------------------------------------------


class ShiftListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [ShiftsCreate()] if self.request.method == "POST" else [ShiftsView()]

    def get_serializer_class(self):
        return ShiftListSerializer

    def get_queryset(self):
        qs = Shift.objects.filter(hotel=self.request.hotel).select_related(
            "responsible_user"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in ShiftStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("business_date"):
            qs = qs.filter(business_date=p["business_date"])
        if p.get("responsible_user") and str(p["responsible_user"]).isdigit():
            qs = qs.filter(responsible_user_id=int(p["responsible_user"]))
        if p.get("search"):
            s = p["search"]
            qs = (
                qs.filter(shift_number__icontains=s)
                | qs.filter(responsible_user__full_name__icontains=s)
                | qs.filter(opening_notes__icontains=s)
                | qs.filter(closing_notes__icontains=s)
            )
        ordering = p.get("ordering")
        if ordering not in (
            "opened_at", "-opened_at", "business_date", "-business_date",
            "shift_number", "-shift_number",
        ):
            ordering = "-opened_at"
        return qs.order_by(ordering).distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = ShiftOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        responsible = (
            _resolve_user(data.get("responsible_user"))
            if data.get("responsible_user")
            else None
        )
        business_date = data.get("business_date")
        # Only a MANAGER may open a shift on someone else's behalf or pin an
        # explicit business date; everyone else opens their own shift on the
        # backend-computed date.
        if (
            (responsible is not None and responsible.id != request.user.id)
            or business_date is not None
        ):
            from apps.rbac.services import get_active_membership
            from apps.tenancy.models import MembershipType

            membership = get_active_membership(request.user, request.hotel)
            if not (membership and membership.membership_type == MembershipType.MANAGER):
                raise PermissionDenied()
        shift = services.open_shift(
            request.hotel,
            user=request.user,
            responsible_user=responsible,
            opening_cash_amount=data["opening_cash_amount"],
            opening_notes=data.get("opening_notes", ""),
            internal_notes=data.get("internal_notes", ""),
            business_date=business_date,
        )
        return Response(ShiftSerializer(shift).data, status=http_status.HTTP_201_CREATED)


class ShiftDetailView(APIView):
    def get_permissions(self):
        return [ShiftsUpdate()] if self.request.method == "PATCH" else [ShiftsView()]

    def get(self, request: Request, pk: int) -> Response:
        shift = _get(Shift, request, pk)
        return Response(ShiftSerializer(shift).data)

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        shift = _get(Shift, request, pk)
        serializer = ShiftUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        shift = services.update_shift(
            shift, user=request.user, **serializer.validated_data
        )
        return Response(ShiftSerializer(shift).data)


class ShiftCloseView(APIView):
    permission_classes = [ShiftsClose]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        shift = _get(Shift, request, pk)
        serializer = ShiftCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift = services.close_shift(
            shift,
            user=request.user,
            actual_cash_amount=serializer.validated_data["actual_cash_amount"],
            difference_reason=serializer.validated_data.get("difference_reason", ""),
            closing_notes=serializer.validated_data.get("closing_notes", ""),
        )
        return Response(ShiftSerializer(shift).data)


class ShiftCancelView(APIView):
    permission_classes = [ShiftsCancel]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        shift = _get(Shift, request, pk)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift = services.cancel_shift(
            shift, reason=serializer.validated_data["reason"], user=request.user
        )
        return Response(ShiftSerializer(shift).data)


class ShiftSummaryView(APIView):
    permission_classes = [ShiftsView]

    def get(self, request: Request, pk: int) -> Response:
        shift = _get(Shift, request, pk)
        summary = services.shift_cash_summary(shift)
        return Response(
            {
                "shift": ShiftListSerializer(shift).data,
                "cash_summary": {
                    k: (str(v) if not isinstance(v, (int, dict)) else v)
                    for k, v in summary.items()
                },
                "unassigned_movements": services.unassigned_movements(
                    request.hotel, shift.business_date
                ),
            }
        )


def _hotel_header(hotel) -> dict:
    s = getattr(hotel, "settings", None)
    return {
        "hotel_name": (getattr(s, "display_name", "") or hotel.name),
        "currency": getattr(s, "default_currency", "") or "USD",
        "phone": getattr(s, "phone", "") or "",
        "address": getattr(s, "address_line", "") or "",
    }


class ShiftStatementView(APIView):
    """The operational shift statement (print-friendly JSON, same document
    pattern as the finance receipt/statement). Read-only; nothing is
    recomputed as new financial truth — the drawer summary is derived."""

    permission_classes = [ShiftsView]

    def get(self, request: Request, pk: int) -> Response:
        shift = _get(Shift, request, pk)
        summary = services.shift_cash_summary(shift)
        return Response(
            {
                "document": "shift_statement",
                "hotel": _hotel_header(request.hotel),
                "shift": ShiftSerializer(shift).data,
                "cash_summary": {
                    k: (str(v) if not isinstance(v, (int, dict)) else v)
                    for k, v in summary.items()
                },
                "unassigned_movements": services.unassigned_movements(
                    request.hotel, shift.business_date
                ),
            }
        )


# --- Handovers -------------------------------------------------------------------


class HandoverListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [ShiftsHandover()] if self.request.method == "POST" else [ShiftsView()]

    def get_serializer_class(self):
        return HandoverListSerializer

    def get_queryset(self):
        qs = ShiftHandover.objects.filter(hotel=self.request.hotel).select_related(
            "from_shift", "to_user", "created_by"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in HandoverStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("from_shift") and str(p["from_shift"]).isdigit():
            qs = qs.filter(from_shift_id=int(p["from_shift"]))
        if p.get("to_user") and str(p["to_user"]).isdigit():
            qs = qs.filter(to_user_id=int(p["to_user"]))
        if p.get("date"):
            qs = qs.filter(created_at__date=p["date"])
        if p.get("search"):
            s = p["search"]
            qs = (
                qs.filter(handover_number__icontains=s)
                | qs.filter(summary_notes__icontains=s)
                | qs.filter(pending_tasks_notes__icontains=s)
            )
        ordering = p.get("ordering")
        if ordering not in ("created_at", "-created_at", "handover_number", "-handover_number"):
            ordering = "-created_at"
        return qs.order_by(ordering).distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = HandoverCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from_shift = _get(Shift, request, data["from_shift"])
        to_user = _resolve_user(data["to_user"])
        handover = services.create_handover(
            request.hotel,
            user=request.user,
            from_shift=from_shift,
            to_user=to_user,
            **{
                k: data.get(k, "")
                for k in (
                    "summary_notes", "pending_tasks_notes", "cash_notes",
                    "guest_notes", "maintenance_notes", "lost_found_notes",
                )
            },
        )
        return Response(
            HandoverSerializer(handover).data, status=http_status.HTTP_201_CREATED
        )


class HandoverDetailView(APIView):
    def get_permissions(self):
        return [ShiftsHandover()] if self.request.method == "PATCH" else [ShiftsView()]

    def get(self, request: Request, pk: int) -> Response:
        handover = _get(ShiftHandover, request, pk)
        return Response(HandoverSerializer(handover).data)

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        handover = _get(ShiftHandover, request, pk)
        serializer = HandoverUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        to_user = (
            _resolve_user(data.pop("to_user")) if data.get("to_user") is not None else None
        )
        data.pop("to_user", None)
        handover = services.update_handover(
            handover, user=request.user, to_user=to_user, **data
        )
        return Response(HandoverSerializer(handover).data)


class HandoverVoucherView(APIView):
    """The print-friendly handover voucher (same document pattern). Read-only."""

    permission_classes = [ShiftsView]

    def get(self, request: Request, pk: int) -> Response:
        handover = _get(ShiftHandover, request, pk)
        return Response(
            {
                "document": "handover_voucher",
                "hotel": _hotel_header(request.hotel),
                "handover": HandoverSerializer(handover).data,
            }
        )


class HandoverSubmitView(APIView):
    permission_classes = [ShiftsHandover]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        handover = _get(ShiftHandover, request, pk)
        handover = services.submit_handover(handover, user=request.user)
        return Response(HandoverSerializer(handover).data)


class HandoverAcceptView(APIView):
    permission_classes = [ShiftsAcceptHandover]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        handover = _get(ShiftHandover, request, pk)
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        handover = services.accept_handover(
            handover, user=request.user, note=serializer.validated_data.get("note", "")
        )
        return Response(HandoverSerializer(handover).data)


class HandoverRejectView(APIView):
    permission_classes = [ShiftsAcceptHandover]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        handover = _get(ShiftHandover, request, pk)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        handover = services.reject_handover(
            handover, user=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(HandoverSerializer(handover).data)


class HandoverCancelView(APIView):
    permission_classes = [ShiftsHandover]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        handover = _get(ShiftHandover, request, pk)
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        handover = services.cancel_handover(
            handover, user=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(HandoverSerializer(handover).data)


# --- Daily close -------------------------------------------------------------------


class DailyCloseListView(generics.ListAPIView):
    permission_classes = [DailyCloseView]

    def get_serializer_class(self):
        return DailyCloseListSerializer

    def get_queryset(self):
        qs = DailyClose.objects.filter(hotel=self.request.hotel).select_related(
            "closed_by"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in DailyCloseStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("business_date"):
            qs = qs.filter(business_date=p["business_date"])
        ordering = p.get("ordering")
        if ordering not in ("business_date", "-business_date"):
            ordering = "-business_date"
        return qs.order_by(ordering)


def _parse_business_date(value, hotel):
    if not value:
        return services.get_business_date(hotel)
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise NotFound("Invalid business date.")


class DailyClosePrepareView(APIView):
    permission_classes = [DailyClosePrepare]

    def post(self, request: Request) -> Response:
        _guard_write(request)
        serializer = DailyCloseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        business_date = _parse_business_date(
            serializer.validated_data.get("business_date"), request.hotel
        )
        close = services.prepare_daily_close(
            request.hotel,
            business_date,
            user=request.user,
            notes=serializer.validated_data.get("notes", ""),
        )
        return Response(DailyCloseSerializer(close).data)


class DailyCloseCloseView(APIView):
    permission_classes = [DailyCloseClose]

    def post(self, request: Request) -> Response:
        _guard_write(request)
        serializer = DailyCloseActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        business_date = _parse_business_date(
            serializer.validated_data.get("business_date"), request.hotel
        )
        close = services.close_business_day(
            request.hotel,
            business_date,
            user=request.user,
            notes=serializer.validated_data.get("notes", ""),
        )
        return Response(DailyCloseSerializer(close).data)


class DailyCloseDetailView(APIView):
    permission_classes = [DailyCloseView]

    def get(self, request: Request, business_date: str) -> Response:
        try:
            on_date = datetime.date.fromisoformat(business_date)
        except ValueError:
            raise NotFound("Invalid business date.")
        close = generics.get_object_or_404(
            DailyClose, hotel=request.hotel, business_date=on_date
        )
        return Response(DailyCloseSerializer(close).data)
