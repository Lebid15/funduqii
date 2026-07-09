"""Stays / front-desk API views (Phase 7), under /api/v1/hotel/.

Scoped to the caller's hotel and guarded by ``stays.*`` permissions. A suspended
hotel is read-only. Check-in/out go through the central services. This phase is
operational only — no money, no folio, no invoices.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.guests.models import Guest
from apps.rbac.permissions import HasHotelPermission
from apps.reservations.models import Reservation, ReservationRoomLine, ReservationStatus
from apps.reservations.serializers import ReservationSerializer
from apps.rooms.models import Room
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import Stay, StayStatus
from .serializers import (
    CheckInSerializer,
    CheckOutSerializer,
    StayNotesSerializer,
    StaySerializer,
    StayStatusLogSerializer,
)
from .services import CheckInService, CheckOutService

CanView = HasHotelPermission("stays.view")
CanCheckIn = HasHotelPermission("stays.check_in")
CanCheckOut = HasHotelPermission("stays.check_out")
CanUpdate = HasHotelPermission("stays.update")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _stay_qs(hotel):
    return Stay.objects.filter(hotel=hotel).select_related(
        "room", "room__room_type", "primary_guest", "reservation"
    ).prefetch_related("guests__guest")


# --- Stays list & views -----------------------------------------------------


class StayListView(generics.ListAPIView):
    serializer_class = StaySerializer

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        qs = _stay_qs(self.request.hotel)
        params = self.request.query_params
        status_filter = params.get("status")
        valid = {c for c, _ in StayStatus.choices}
        if status_filter in valid:
            qs = qs.filter(status=status_filter)
        room = params.get("room")
        if room and str(room).isdigit():
            qs = qs.filter(room_id=int(room))
        checkout = params.get("planned_check_out_date")
        if checkout:
            qs = qs.filter(planned_check_out_date=checkout)
        search = params.get("search")
        if search:
            qs = (
                qs.filter(primary_guest__full_name__icontains=search)
                | qs.filter(reservation__reservation_number__icontains=search)
                | qs.filter(room__number__icontains=search)
            )
        return qs.distinct()


class CurrentResidentsView(generics.ListAPIView):
    serializer_class = StaySerializer

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        return _stay_qs(self.request.hotel).filter(status=StayStatus.IN_HOUSE)


class DeparturesTodayView(generics.ListAPIView):
    serializer_class = StaySerializer

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        today = timezone.localdate()
        return _stay_qs(self.request.hotel).filter(
            status=StayStatus.IN_HOUSE, planned_check_out_date=today
        )


class ArrivalsTodayView(APIView):
    """Confirmed reservations arriving today that are not fully checked in."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        reservations = (
            Reservation.objects.filter(
                hotel=request.hotel,
                status=ReservationStatus.CONFIRMED,
                check_in_date=today,
            )
            .prefetch_related("lines__room_type", "lines__room", "stays")
        )
        pending = []
        for res in reservations:
            requested = sum(line.quantity for line in res.lines.all())
            admitted = sum(
                1 for s in res.stays.all() if s.status != StayStatus.CANCELLED
            )
            if admitted < requested:
                pending.append(res)
        return Response(ReservationSerializer(pending, many=True).data)


class StayDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve a stay, or PATCH only its internal notes."""

    serializer_class = StaySerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [CanUpdate()] if self.request.method == "PATCH" else [CanView()]

    def get_queryset(self):
        return _stay_qs(self.request.hotel)

    def update(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        stay = self.get_object()
        serializer = StayNotesSerializer(stay, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        stay.refresh_from_db()
        return Response(StaySerializer(stay).data)


class StayLogsView(APIView):
    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        return Response(
            StayStatusLogSerializer(stay.status_logs.all(), many=True).data
        )


# --- Check-in / check-out ---------------------------------------------------


class CheckInView(APIView):
    def get_permissions(self):
        return [CanCheckIn()]

    def post(self, request: Request) -> Response:
        _guard_write(request)
        serializer = CheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        hotel = request.hotel

        reservation = generics.get_object_or_404(
            Reservation, pk=data["reservation"], hotel=hotel
        )
        line = None
        if data.get("reservation_line"):
            line = generics.get_object_or_404(
                ReservationRoomLine, pk=data["reservation_line"], hotel=hotel
            )
        room = None
        if data.get("room"):
            room = generics.get_object_or_404(Room, pk=data["room"], hotel=hotel)
        primary_guest = generics.get_object_or_404(
            Guest, pk=data["primary_guest"], hotel=hotel
        )
        companions = [
            generics.get_object_or_404(Guest, pk=cid, hotel=hotel)
            for cid in data.get("companions", [])
        ]

        stay = CheckInService.execute(
            hotel,
            reservation=reservation,
            reservation_line=line,
            room=room,
            primary_guest=primary_guest,
            companions=companions,
            check_in_notes=data.get("check_in_notes", ""),
            user=request.user,
        )
        return Response(StaySerializer(stay).data, status=status.HTTP_201_CREATED)


class CheckOutView(APIView):
    def get_permissions(self):
        return [CanCheckOut()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        serializer = CheckOutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        CheckOutService.execute(
            stay,
            check_out_notes=serializer.validated_data.get("check_out_notes", ""),
            checkout_reason=serializer.validated_data.get("checkout_reason", ""),
            user=request.user,
        )
        stay.refresh_from_db()
        return Response(StaySerializer(stay).data)
