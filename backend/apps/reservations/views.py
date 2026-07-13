"""Reservations & availability API views (Phase 6), under /api/v1/hotel/.

All endpoints are scoped to the caller's hotel context and guarded by
``reservations.*`` / ``availability.view`` permissions. A suspended hotel is
read-only. There is **no hard-delete** endpoint — cancelling is the only way to
remove a reservation. This phase has no check-in/out, no guest profile, and no
money.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import PermissionDenied
from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .availability import AvailabilityService, blocking_q
from .models import Reservation, ReservationSource, ReservationStatus
from .serializers import (
    AvailabilityQuerySerializer,
    CancelReservationSerializer,
    ReservationSerializer,
    ReservationStatusLogSerializer,
    ReservationWriteSerializer,
    TypeAvailabilitySerializer,
)

CanView = HasHotelPermission("reservations.view")
CanCreate = HasHotelPermission("reservations.create")
CanUpdate = HasHotelPermission("reservations.update")
CanConfirm = HasHotelPermission("reservations.confirm")
CanCancel = HasHotelPermission("reservations.cancel")
CanAvailability = HasHotelPermission("availability.view")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _guard_assignment(request: Request, lines) -> None:
    """Assigning a specific room (Phase 6.1) requires reservations.assign_room."""
    if any(ln.get("room") for ln in lines):
        if not has_hotel_permission(
            request.user, request.hotel, "reservations.assign_room"
        ):
            raise PermissionDenied()


def _get_reservation(request: Request, pk: int) -> Reservation:
    return generics.get_object_or_404(Reservation, pk=pk, hotel=request.hotel)


def _business_day_range(hotel) -> tuple[datetime.datetime, datetime.datetime]:
    """The [start, end) datetimes of the hotel's CURRENT business date, in the
    hotel's timezone — "created today" must follow the hotel clock, never the
    client's (reservations section reorg)."""
    from apps.shifts.services import get_business_date

    day = get_business_date(hotel)
    tz_name = ""
    hotel_settings = getattr(hotel, "settings", None)
    if hotel_settings is not None:
        tz_name = (hotel_settings.timezone or "").strip()
    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.get_current_timezone()
    except (ValueError, KeyError):
        tz = timezone.get_current_timezone()
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=tz)
    return start, start + datetime.timedelta(days=1)


# --- Reservations -----------------------------------------------------------


class ReservationListCreateView(generics.ListCreateAPIView):
    serializer_class = ReservationSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [CanCreate()]
        return [CanView()]

    def get_queryset(self):
        qs = (
            Reservation.objects.filter(hotel=self.request.hotel)
            .prefetch_related("lines__room_type")
        )
        params = self.request.query_params

        status_filter = params.get("status")
        valid = {c for c, _ in ReservationStatus.choices}
        if status_filter in valid:
            qs = qs.filter(status=status_filter)

        # Comma-separated multi-status (e.g. cancelled,expired) — validated
        # against the real choices (reservations section reorg, read-only).
        statuses = params.get("statuses")
        if statuses:
            wanted = [s for s in statuses.split(",") if s in valid]
            if wanted:
                qs = qs.filter(status__in=wanted)

        source = params.get("source")
        if source in {c for c, _ in ReservationSource.choices}:
            qs = qs.filter(source=source)

        room_type = params.get("room_type")
        if room_type and str(room_type).isdigit():
            qs = qs.filter(lines__room_type_id=int(room_type)).distinct()

        room = params.get("room")
        if room and str(room).isdigit():
            qs = qs.filter(lines__room_id=int(room)).distinct()

        date_from = params.get("date_from")
        date_to = params.get("date_to")
        if date_from:
            qs = qs.filter(check_out_date__gt=date_from)
        if date_to:
            qs = qs.filter(check_in_date__lt=date_to)

        # Creation-date filters (owner reorg: "today's reservations" =
        # CREATED today, per the hotel business date — not arrivals).
        if params.get("created_today") == "true":
            start, end = _business_day_range(self.request.hotel)
            qs = qs.filter(created_at__gte=start, created_at__lt=end)
        created_from = params.get("created_from")
        if created_from:
            qs = qs.filter(created_at__date__gte=created_from)
        created_to = params.get("created_to")
        if created_to:
            qs = qs.filter(created_at__date__lte=created_to)

        # Pending public cancel requests (final closure): a request only
        # matters while the reservation still blocks (held/confirmed) — a
        # cancelled one was already accepted.
        if params.get("cancel_requested") == "true":
            qs = qs.filter(
                public_cancel_requested_at__isnull=False,
                status__in=[
                    ReservationStatus.HELD,
                    ReservationStatus.CONFIRMED,
                ],
            )

        # Future view: arrival strictly after the hotel business date.
        if params.get("upcoming") == "true":
            from apps.shifts.services import get_business_date

            qs = qs.filter(check_in_date__gt=get_business_date(self.request.hotel))

        search = params.get("search")
        if search:
            qs = (
                qs.filter(reservation_number__icontains=search)
                | qs.filter(primary_guest_name__icontains=search)
                | qs.filter(primary_guest_phone__icontains=search)
                # Room-number search reaches assigned room lines.
                | qs.filter(lines__room__number__icontains=search)
            )
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = ReservationWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lines = data.pop("lines")
        _guard_assignment(request, lines)
        res_status = data.pop("status")
        reservation = services.create_reservation(
            request.hotel, lines=lines, status=res_status, user=request.user, **data
        )
        return Response(
            ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED
        )


class ReservationDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve or update a reservation. No destroy — cancelling is the path."""

    serializer_class = ReservationSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [CanUpdate()]
        return [CanView()]

    def get_queryset(self):
        return Reservation.objects.filter(hotel=self.request.hotel).prefetch_related(
            "lines__room_type"
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        reservation = self.get_object()
        serializer = ReservationWriteSerializer(
            reservation, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lines = data.pop("lines", None)
        if lines is not None:
            _guard_assignment(request, lines)
        data.pop("status", None)  # status is changed only via confirm/cancel/hold
        services.update_reservation(
            reservation, lines=lines, user=request.user, **data
        )
        reservation.refresh_from_db()
        return Response(ReservationSerializer(reservation).data)


class ReservationConfirmView(APIView):
    def get_permissions(self):
        return [CanConfirm()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        reservation = _get_reservation(request, pk)
        services.confirm_reservation(reservation, user=request.user)
        reservation.refresh_from_db()
        return Response(ReservationSerializer(reservation).data)


class ReservationCancelView(APIView):
    def get_permissions(self):
        return [CanCancel()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        reservation = _get_reservation(request, pk)
        serializer = CancelReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_reservation(
            reservation, reason=serializer.validated_data["reason"], user=request.user
        )
        reservation.refresh_from_db()
        return Response(ReservationSerializer(reservation).data)


class ReservationHoldView(APIView):
    """Place or refresh a temporary hold (extends ``hold_expires_at``).

    Holds are normally created at creation time (``status=held``); this endpoint
    refreshes an existing hold's expiry after re-checking availability, which
    matters when a hold has lapsed and its inventory must be re-acquired.
    """

    def get_permissions(self):
        return [CanUpdate()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        reservation = _get_reservation(request, pk)
        expires = request.data.get("hold_expires_at")
        services.hold_reservation(reservation, hold_expires_at=expires, user=request.user)
        reservation.refresh_from_db()
        return Response(ReservationSerializer(reservation).data)


class ReservationLogsView(APIView):
    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        reservation = _get_reservation(request, pk)
        logs = reservation.status_logs.all()
        return Response(ReservationStatusLogSerializer(logs, many=True).data)


class ReservationOverviewView(APIView):
    """Small dashboard summary for the reservations console."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        from apps.shifts.services import get_business_date

        hotel = request.hotel
        base = Reservation.objects.filter(hotel=hotel)
        today = timezone.localdate()
        counts = {s: 0 for s, _ in ReservationStatus.choices}
        for row in base.values("status"):
            counts[row["status"]] = counts.get(row["status"], 0) + 1

        blocking = base.filter(blocking_q())
        arrivals = (
            blocking.filter(check_in_date__gte=today)
            .order_by("check_in_date")[:10]
        )
        departures = (
            blocking.filter(check_out_date__gte=today)
            .order_by("check_out_date")[:10]
        )
        return Response(
            {
                "total": base.count(),
                "held": counts.get(ReservationStatus.HELD, 0),
                "confirmed": counts.get(ReservationStatus.CONFIRMED, 0),
                "cancelled": counts.get(ReservationStatus.CANCELLED, 0),
                "expired": counts.get(ReservationStatus.EXPIRED, 0),
                # Additive source count: hotel-scoped reservations that came
                # from the public website, across ALL statuses (this overlaps
                # the status counts above — it is NOT a mutually-exclusive
                # bucket). Same request.hotel scope as every other count.
                "website": base.filter(
                    source=ReservationSource.PUBLIC_WEBSITE
                ).count(),
                # The hotel's operational "today" — the immediate-reservation
                # wizard prefixes its arrival date with this (the client
                # clock can differ from the hotel timezone).
                "business_date": str(get_business_date(hotel)),
                "arrivals": ReservationSerializer(arrivals, many=True).data,
                "departures": ReservationSerializer(departures, many=True).data,
            }
        )


# --- Availability -----------------------------------------------------------


class AvailabilityView(APIView):
    def get_permissions(self):
        return [CanAvailability()]

    def get(self, request: Request) -> Response:
        serializer = AvailabilityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        room_type = None
        rt_id = data.get("room_type")
        if rt_id is not None:
            from apps.rooms.models import RoomType

            room_type = RoomType.objects.filter(
                pk=rt_id, hotel=request.hotel
            ).first()
            if room_type is None:
                return Response({"results": []})
        results = AvailabilityService.check_availability(
            request.hotel,
            data["check_in_date"],
            data["check_out_date"],
            room_type=room_type,
        )
        return Response(
            {"results": TypeAvailabilitySerializer(results, many=True).data}
        )


class AvailabilityCalendarView(APIView):
    """A simple per-day availability grid (bounded range). No drag/drop UI."""

    MAX_DAYS = 62

    def get_permissions(self):
        return [CanAvailability()]

    def get(self, request: Request) -> Response:
        from datetime import timedelta

        serializer = AvailabilityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        start = data["check_in_date"]
        end = data["check_out_date"]
        span = (end - start).days
        if span > self.MAX_DAYS:
            end = start + timedelta(days=self.MAX_DAYS)

        room_type = None
        rt_id = data.get("room_type")
        if rt_id is not None:
            from apps.rooms.models import RoomType

            room_type = RoomType.objects.filter(
                pk=rt_id, hotel=request.hotel
            ).first()
            if room_type is None:
                return Response({"days": []})

        days = []
        cursor = start
        while cursor < end:
            nxt = cursor + timedelta(days=1)
            per_type = AvailabilityService.check_availability(
                request.hotel, cursor, nxt, room_type=room_type
            )
            days.append(
                {
                    "date": cursor.isoformat(),
                    "types": TypeAvailabilitySerializer(per_type, many=True).data,
                }
            )
            cursor = nxt
        return Response({"days": days})
