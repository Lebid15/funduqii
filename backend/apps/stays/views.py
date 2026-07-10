"""Stays / front-desk API views (Phase 7 + final closure), under /api/v1/hotel/.

Scoped to the caller's hotel and guarded by ``stays.*`` permissions. A suspended
hotel is read-only. Check-in/out and every in-house stay change go through the
central services. Every operational "today" is the HOTEL's business date —
never the server clock.
"""
from __future__ import annotations

from datetime import timedelta

from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.guests.models import Guest
from apps.rbac.permissions import HasHotelPermission
from apps.reservations.availability import AvailabilityService
from apps.reservations.models import Reservation, ReservationRoomLine, ReservationStatus
from apps.reservations.serializers import ReservationSerializer
from apps.rooms.models import Room, RoomStatus
from apps.shifts.services import get_business_date
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import Stay, StayStatus
from .serializers import (
    CheckInSerializer,
    CheckOutSerializer,
    StayDateChangeSerializer,
    StayMoveRoomSerializer,
    StayNotesSerializer,
    StaySerializer,
    StayStatusLogSerializer,
)
from .services import (
    CheckInService,
    CheckOutService,
    ExtendStayService,
    RoomMoveService,
    ShortenStayService,
)

CanView = HasHotelPermission("stays.view")
CanCheckIn = HasHotelPermission("stays.check_in")
CanCheckOut = HasHotelPermission("stays.check_out")
CanUpdate = HasHotelPermission("stays.update")
CanExtend = HasHotelPermission("stays.extend")
CanShorten = HasHotelPermission("stays.shorten")
CanMoveRoom = HasHotelPermission("stays.move_room")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _stay_qs(hotel):
    return Stay.objects.filter(hotel=hotel).select_related(
        "room", "room__room_type", "primary_guest", "reservation"
    ).prefetch_related("guests__guest")


def _free_rooms(hotel, room_type, check_in, check_out, *, exclude_reservation_id):
    """Rooms of ``room_type`` a guest can physically be admitted into for the
    given window: manually available, active, not derived-occupied, and not
    pinned by another blocking reservation. The check-in service re-checks all
    of this — this list only keeps the UI honest."""
    occupied = set(
        Stay.objects.filter(hotel=hotel, status=StayStatus.IN_HOUSE).values_list(
            "room_id", flat=True
        )
    )
    assigned, _unassigned = AvailabilityService.existing_usage(
        hotel,
        room_type,
        check_in,
        check_out,
        exclude_reservation_id=exclude_reservation_id,
    )
    return [
        room
        for room in Room.objects.filter(
            hotel=hotel,
            room_type=room_type,
            is_active=True,
            floor__is_active=True,
            status=RoomStatus.AVAILABLE,
        ).order_by("number")
        if room.id not in occupied and room.id not in assigned
    ]


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
        today = get_business_date(self.request.hotel)
        return _stay_qs(self.request.hotel).filter(
            status=StayStatus.IN_HOUSE, planned_check_out_date=today
        )


class ArrivalsTodayView(APIView):
    """Confirmed reservations arriving today that are not fully checked in."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        today = get_business_date(request.hotel)
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


class StayFolioSummaryView(APIView):
    """The stay's open-folio balance + business-date context for the checkout
    dialog. Read-only; nothing is created here."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        from apps.finance.models import Folio, FolioStatus
        from apps.finance.services import folio_balance

        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        folios = Folio.objects.filter(hotel=request.hotel, stay=stay)
        open_summaries = []
        total = 0
        for folio in folios.filter(status=FolioStatus.OPEN).order_by("id"):
            balance = folio_balance(folio)["balance"]
            total += balance
            open_summaries.append(
                {
                    "id": folio.id,
                    "folio_number": folio.folio_number,
                    "status": folio.status,
                    "currency": folio.currency,
                    "balance": str(balance),
                }
            )
        business_date = get_business_date(request.hotel)
        return Response(
            {
                "business_date": str(business_date),
                "is_early_departure": (
                    stay.status == StayStatus.IN_HOUSE
                    and business_date < stay.planned_check_out_date
                ),
                "has_folio": folios.exists(),
                "open_folios": open_summaries,
                "balance": str(total),
            }
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


class CheckInRoomsView(APIView):
    """Rooms actually admissible for a reservation line — feeds the check-in
    dialog so it never offers a derived-occupied or conflicted room. The
    service's own re-checks remain the final word."""

    def get_permissions(self):
        return [CanCheckIn()]

    def get(self, request: Request) -> Response:
        res_id = request.query_params.get("reservation")
        line_id = request.query_params.get("line")
        if not (res_id and str(res_id).isdigit() and line_id and str(line_id).isdigit()):
            return Response([], status=status.HTTP_200_OK)
        reservation = generics.get_object_or_404(
            Reservation, pk=int(res_id), hotel=request.hotel
        )
        line = generics.get_object_or_404(
            ReservationRoomLine, pk=int(line_id), hotel=request.hotel
        )
        if line.reservation_id != reservation.id:
            return Response([])
        rooms = _free_rooms(
            request.hotel,
            line.room_type,
            reservation.check_in_date,
            reservation.check_out_date,
            exclude_reservation_id=reservation.id,
        )
        return Response(
            [{"id": room.id, "number": room.number} for room in rooms]
        )


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


# --- In-house stay changes (final closure) ----------------------------------


class StayExtendView(APIView):
    def get_permissions(self):
        return [CanExtend()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        serializer = StayDateChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ExtendStayService.execute(
            stay,
            new_check_out_date=serializer.validated_data["new_check_out_date"],
            reason=serializer.validated_data.get("reason", ""),
            user=request.user,
        )
        stay.refresh_from_db()
        return Response(StaySerializer(stay).data)


class StayShortenView(APIView):
    def get_permissions(self):
        return [CanShorten()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        serializer = StayDateChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ShortenStayService.execute(
            stay,
            new_check_out_date=serializer.validated_data["new_check_out_date"],
            reason=serializer.validated_data.get("reason", ""),
            user=request.user,
        )
        stay.refresh_from_db()
        return Response(StaySerializer(stay).data)


class StayMoveRoomView(APIView):
    def get_permissions(self):
        return [CanMoveRoom()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        serializer = StayMoveRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_room = generics.get_object_or_404(
            Room, pk=serializer.validated_data["room"], hotel=request.hotel
        )
        RoomMoveService.execute(
            stay,
            new_room=new_room,
            reason=serializer.validated_data["reason"],
            user=request.user,
        )
        stay.refresh_from_db()
        return Response(StaySerializer(stay).data)


class StayMoveCandidatesView(APIView):
    """Rooms a stay can move into RIGHT NOW (any type with enough capacity) —
    feeds the room-move dialog. The move service re-checks everything."""

    def get_permissions(self):
        return [CanMoveRoom()]

    def get(self, request: Request, pk: int) -> Response:
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        if stay.status != StayStatus.IN_HOUSE:
            return Response([])
        business_date = get_business_date(request.hotel)
        window_end = max(
            stay.planned_check_out_date, business_date + timedelta(days=1)
        )
        guest_count = stay.guests.count() or 1
        candidates = []
        room_types = {}
        for room in (
            Room.objects.filter(
                hotel=request.hotel,
                is_active=True,
                floor__is_active=True,
                room_type__is_active=True,
                status=RoomStatus.AVAILABLE,
            )
            .exclude(pk=stay.room_id)
            .select_related("room_type")
            .order_by("number")
        ):
            if room.room_type.max_capacity < guest_count:
                continue
            room_types.setdefault(room.room_type_id, []).append(room)
        occupied = set(
            Stay.objects.filter(
                hotel=request.hotel, status=StayStatus.IN_HOUSE
            ).values_list("room_id", flat=True)
        )
        for type_id, rooms in room_types.items():
            assigned, _ = AvailabilityService.existing_usage(
                request.hotel,
                rooms[0].room_type,
                business_date,
                window_end,
                exclude_reservation_id=stay.reservation_id,
            )
            for room in rooms:
                if room.id in occupied or room.id in assigned:
                    continue
                candidates.append(
                    {
                        "id": room.id,
                        "number": room.number,
                        "room_type_name": room.room_type.name,
                        "max_capacity": room.room_type.max_capacity,
                    }
                )
        candidates.sort(key=lambda c: c["number"])
        return Response(candidates)
