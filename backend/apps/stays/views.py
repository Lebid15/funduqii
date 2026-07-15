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

from apps.common.exceptions import PermissionDenied
from apps.guests.models import Guest
from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.reservations.availability import AvailabilityService
from apps.reservations.models import Reservation, ReservationRoomLine, ReservationStatus
from apps.reservations.serializers import ReservationSerializer
from apps.rooms.models import Room, RoomStatus
from apps.shifts.services import get_business_date
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import Stay, StayStatus
from .orchestration import execute_immediate_check_in
from .serializers import (
    CheckInSerializer,
    CheckOutSerializer,
    ImmediateCheckInSerializer,
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
    ReverseCheckInService,
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
CanReverseCheckIn = HasHotelPermission("stays.reverse_check_in")
# Immediate atomic check-in performs BOTH a reservation create and a check-in,
# so it requires BOTH capabilities (a deposit adds finance.payment_create, and a
# foreign-currency manual FX rate adds exchange_rate.override — enforced below).
CanCreateReservation = HasHotelPermission("reservations.create")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _stay_qs(hotel, *, with_folio=False):
    qs = Stay.objects.filter(hotel=hotel).select_related(
        "room", "room__room_type", "primary_guest", "reservation",
        "checked_in_by", "checked_out_by",
    ).prefetch_related("guests__guest", "reservation__documents")
    if with_folio:
        # Operational-card finance block (§12): prefetch each stay's OPEN folio
        # with its POSTED charges + payments so the whole list builds its folio
        # summaries with a fixed number of queries — never one (or three) per
        # card. Adding residents must not grow the query count linearly.
        from django.db.models import Prefetch

        from apps.finance.models import (
            Folio,
            FolioCharge,
            FolioStatus,
            Payment,
            PostingStatus,
            RefundableInsurance,
        )

        qs = qs.prefetch_related(
            Prefetch(
                "folios",
                queryset=Folio.objects.filter(status=FolioStatus.OPEN)
                .order_by("id")
                .prefetch_related(
                    Prefetch(
                        "charges",
                        queryset=FolioCharge.objects.filter(status=PostingStatus.POSTED),
                    ),
                    Prefetch(
                        "payments",
                        queryset=Payment.objects.filter(status=PostingStatus.POSTED),
                    ),
                ),
                to_attr="open_folios_prefetched",
            ),
            # FIX-3 (§12 card clearance must account for held insurance). Two
            # BOUNDED prefetches — one for insurance linked directly to the stay,
            # one for insurance taken at booking against the reservation while the
            # stay was not yet linked (``stay`` NULL) — mirror ``held_insurance_qs``
            # so the card's non-finance clearance flag is honest WITHOUT a per-card
            # query (no N+1). ``held_amount`` is derived, so the rows are fetched
            # and the held test is done in Python (a handful of rows per stay).
            Prefetch(
                "insurances",
                queryset=RefundableInsurance.objects.all(),
                to_attr="held_insurances_prefetched",
            ),
            Prefetch(
                "reservation__insurances",
                queryset=RefundableInsurance.objects.filter(stay__isnull=True),
                to_attr="reservation_held_insurances_prefetched",
            ),
        )
    return qs


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

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "with_folio": True}

    def get_queryset(self):
        return _stay_qs(self.request.hotel, with_folio=True).filter(
            status=StayStatus.IN_HOUSE
        )


class StaysOverviewView(APIView):
    """Six smart-card counts for the operations page (§6/§50) — a fixed set of
    queries, based on the hotel's current business date."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        from .services import stays_overview

        return Response(stays_overview(request.hotel))


class DeparturesTodayView(generics.ListAPIView):
    serializer_class = StaySerializer

    def get_permissions(self):
        return [CanView()]

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "with_folio": True}

    def get_queryset(self):
        today = get_business_date(self.request.hotel)
        return _stay_qs(self.request.hotel, with_folio=True).filter(
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
        return Response(
            ReservationSerializer(
                pending, many=True, context={"request": request}
            ).data
        )


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


def _stay_folio_summary(request, stay) -> dict:
    """Build the checkout dialog's folio + insurance snapshot for a stay.

    STAYS ITEM-4 (financial-detail RBAC). Every MONETARY value below — balances,
    currencies, insurance amounts, settlement/payment detail — is returned ONLY to
    a viewer holding ``finance.view``. A viewer with ``stays.view`` /
    ``stays.check_out`` but WITHOUT ``finance.view`` receives abstract OPERATIONAL
    states only; the monetary keys are OMITTED entirely (never zeroed/nulled) so no
    amount, currency or sensitive movement leaks through a placeholder.

    The clearance flags are computed the SAME way regardless of who is looking, so
    the backend stays the single, final arbiter of checkout readiness:
    ``can_check_out`` mirrors the financial gate the checkout service enforces
    (a settled balance, no folio awaiting final charges, no insurance still held).
    """
    from apps.finance.models import Folio, FolioStatus
    from apps.finance.services import folio_balance, held_insurance_qs

    folios = Folio.objects.filter(hotel=request.hotel, stay=stay)
    open_summaries = []
    total = 0
    awaiting_final_charges = False
    for folio in folios.filter(status=FolioStatus.OPEN).order_by("id"):
        balance = folio_balance(folio)["balance"]
        total += balance
        if folio.awaiting_final_charges:
            awaiting_final_charges = True
        open_summaries.append(
            {
                "id": folio.id,
                "folio_number": folio.folio_number,
                "status": folio.status,
                "currency": folio.currency,
                "balance": str(balance),
                "awaiting_final_charges": folio.awaiting_final_charges,
                "awaiting_final_charges_note": folio.awaiting_final_charges_note,
            }
        )
    # Refundable insurance that blocks this stay must be settled before the
    # guest departs (§35). This uses the SAME shared query as
    # ``CheckOutService.execute`` (``held_insurance_qs``) — including insurance
    # taken at booking against the reservation while the stay was not yet linked
    # (``stay`` NULL) — so ``can_check_out`` here can never disagree with the
    # gate the checkout service actually enforces. Surface held items so the
    # checkout dialog can drive refund/deduction without a second round-trip.
    insurances = []
    insurance_pending = False
    insurance_held = False
    for ins in held_insurance_qs(stay).order_by("id"):
        held = ins.held_amount
        if held > 0:
            insurance_pending = True
            insurance_held = True
        insurances.append(
            {
                "id": ins.id,
                "currency": ins.currency,
                "amount": str(ins.amount),
                "deducted_amount": str(ins.deducted_amount),
                "refunded_amount": str(ins.refunded_amount),
                "held_amount": str(held),
                "status": ins.status,
            }
        )
    business_date = get_business_date(request.hotel)

    # Financial clearance = a settled balance AND no folio awaiting final charges
    # AND no insurance still held. This is the same truth for every viewer.
    financial_clearance_complete = (
        total == 0 and not awaiting_final_charges and not insurance_held
    )
    can_see_finance = has_hotel_permission(
        request.user, request.hotel, "finance.view"
    )

    summary = {
        "business_date": str(business_date),
        "is_early_departure": (
            stay.status == StayStatus.IN_HOUSE
            and business_date < stay.planned_check_out_date
        ),
        "has_folio": folios.exists(),
        # Operational, non-monetary states — always present for every viewer.
        "financial_details_visible": can_see_finance,
        "financial_clearance_complete": financial_clearance_complete,
        "requires_financial_action": not financial_clearance_complete,
        "can_check_out": financial_clearance_complete,
    }
    if can_see_finance:
        # Full monetary detail exactly as before (unchanged shape).
        summary["open_folios"] = open_summaries
        summary["balance"] = str(total)
        summary["awaiting_final_charges"] = awaiting_final_charges
        summary["insurances"] = insurances
        summary["insurance_pending"] = insurance_pending
    else:
        # Non-monetary operational skeleton only: folio identifiers + the
        # awaiting flag (NO balance, NO currency, NO status, NO note); the
        # awaiting bool; and NOTHING about insurance amounts or existence.
        summary["open_folios"] = [
            {
                "id": f["id"],
                "folio_number": f["folio_number"],
                "awaiting_final_charges": f["awaiting_final_charges"],
            }
            for f in open_summaries
        ]
        summary["awaiting_final_charges"] = awaiting_final_charges
    return summary


class StayFolioSummaryView(APIView):
    """The stay's open-folio balance + business-date context for the checkout
    dialog. Read-only; nothing is created here."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        return Response(_stay_folio_summary(request, stay))


class StayEnsureRoomChargesView(APIView):
    """Post every room night that has become DUE by the hotel business date, then
    return the refreshed folio summary (owner correction §24): the checkout dialog
    calls this on open so the front desk always settles the real, complete amount
    — the folio is never missing a consumed night just because the daily close has
    not run. Idempotent; never posts a future night. Requires ``stays.check_out``."""

    def get_permissions(self):
        return [CanCheckOut()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        from apps.finance.services import ensure_due_room_charges

        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        ensure_due_room_charges(stay, user=request.user)
        return Response(_stay_folio_summary(request, stay))


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


class ImmediateCheckInView(APIView):
    """Atomic immediate check-in (RESERVATIONS-FORM-REWORK).

    ``POST .../stays/immediate-check-in/`` composes, all-or-nothing, a confirmed
    instant reservation + an optional pre-arrival deposit + an in-house stay on
    ONE folio (the deposit folio is reused, never duplicated). Kept entirely
    separate from :class:`CheckInView`, which is unchanged.

    Requires BOTH ``reservations.create`` AND ``stays.check_in``. When a deposit
    is supplied it additionally requires ``finance.payment_create``; a
    foreign-currency deposit with a manual FX rate also requires
    ``exchange_rate.override``.
    """

    def get_permissions(self):
        return [CanCreateReservation(), CanCheckIn()]

    def post(self, request: Request) -> Response:
        _guard_write(request)
        serializer = ImmediateCheckInSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        hotel = request.hotel

        res_data = dict(data["reservation"])
        lines = res_data.pop("lines")
        occupants = res_data.pop("occupants", None)
        primary_guest = res_data.pop("primary_guest", None)
        res_data.pop("status", None)  # forced to confirmed in the orchestration
        res_data.pop("booking_kind", None)  # forced to instant in the orchestration

        room = None
        if data.get("room"):
            room = generics.get_object_or_404(Room, pk=data["room"], hotel=hotel)

        deposit = data.get("deposit") or None
        if deposit:
            deposit = dict(deposit)
            self._authorize_deposit(request, hotel, deposit)

        result = execute_immediate_check_in(
            hotel,
            lines=lines,
            primary_guest=primary_guest,
            occupants=occupants,
            room=room,
            line_index=data.get("line_index"),
            deposit=deposit,
            check_in_notes=data.get("check_in_notes", ""),
            user=request.user,
            **res_data,
        )
        return Response(
            self._serialize_result(request, result),
            status=status.HTTP_201_CREATED,
        )

    def _authorize_deposit(self, request: Request, hotel, deposit) -> None:
        # Recording money requires the payment permission; a manual FX rate on a
        # foreign-currency deposit additionally requires the override permission.
        if not has_hotel_permission(request.user, hotel, "finance.payment_create"):
            raise PermissionDenied()
        currency = (deposit.get("currency") or "").strip().upper()
        base = (
            getattr(getattr(hotel, "settings", None), "default_currency", "")
            or "USD"
        ).upper()
        if currency and currency != base and deposit.get("exchange_rate") is not None:
            if not has_hotel_permission(request.user, hotel, "exchange_rate.override"):
                raise PermissionDenied()

    def _serialize_result(self, request: Request, result) -> dict:
        from apps.finance.services import folio_balance

        folio = result["folio"]
        folio_data = None
        if folio is not None:
            folio_data = {
                "id": folio.id,
                "folio_number": folio.folio_number,
                "status": folio.status,
                "currency": folio.currency,
                # Balance stays DERIVED (never stored) — invariant #1.
                "balance": str(folio_balance(folio)["balance"]),
            }
        return {
            "reservation": ReservationSerializer(
                result["reservation"], context={"request": request}
            ).data,
            "stay": StaySerializer(result["stay"]).data,
            "folio": folio_data,
        }


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


class ReverseCheckInView(APIView):
    """Reverse a mistaken check-in (§30) — POST stays/<id>/reverse-check-in/ with
    a mandatory ``reason``. Requires ``stays.reverse_check_in``."""

    def get_permissions(self):
        return [CanReverseCheckIn()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        stay = generics.get_object_or_404(Stay, pk=pk, hotel=request.hotel)
        ReverseCheckInService.execute(
            stay, reason=(request.data.get("reason") or ""), user=request.user
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
