"""Reservations & availability API views (Phase 6), under /api/v1/hotel/.

All endpoints are scoped to the caller's hotel context and guarded by
``reservations.*`` / ``availability.view`` permissions. A suspended hotel is
read-only. There is **no hard-delete** endpoint — cancelling is the only way to
remove a reservation. This phase has no check-in/out, no guest profile, and no
money.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import HotelSuspended
from apps.rbac.permissions import HasHotelPermission
from apps.tenancy.models import HotelStatus

from . import services
from .availability import AvailabilityService, blocking_q
from .models import Reservation, ReservationStatus
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
    if request.hotel.status == HotelStatus.SUSPENDED:
        raise HotelSuspended()


def _get_reservation(request: Request, pk: int) -> Reservation:
    return generics.get_object_or_404(Reservation, pk=pk, hotel=request.hotel)


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

        room_type = params.get("room_type")
        if room_type and str(room_type).isdigit():
            qs = qs.filter(lines__room_type_id=int(room_type)).distinct()

        date_from = params.get("date_from")
        date_to = params.get("date_to")
        if date_from:
            qs = qs.filter(check_out_date__gt=date_from)
        if date_to:
            qs = qs.filter(check_in_date__lt=date_to)

        search = params.get("search")
        if search:
            qs = (
                qs.filter(reservation_number__icontains=search)
                | qs.filter(primary_guest_name__icontains=search)
                | qs.filter(primary_guest_phone__icontains=search)
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
