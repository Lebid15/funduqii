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
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import PermissionDenied, ReservationHasActiveStay
from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .availability import AvailabilityService, blocking_q, overlap_q
from .models import (
    Reservation,
    ReservationRoomLine,
    ReservationSource,
    ReservationStatus,
)
from .serializers import (
    AvailabilityQuerySerializer,
    CancelReservationSerializer,
    ReservationDepositSerializer,
    ReservationSerializer,
    ReservationStatusLogSerializer,
    ReservationWriteSerializer,
    RoomAvailabilityQuerySerializer,
    TypeAvailabilitySerializer,
)

CanView = HasHotelPermission("reservations.view")
CanCreate = HasHotelPermission("reservations.create")
CanUpdate = HasHotelPermission("reservations.update")
CanConfirm = HasHotelPermission("reservations.confirm")
CanCancel = HasHotelPermission("reservations.cancel")
CanAvailability = HasHotelPermission("availability.view")
# §27 deposit-for-future — recording money requires the payment permission
# (a foreign-currency manual FX rate additionally requires exchange_rate.override,
# enforced in the view). NEVER a reservations.* write permission for money (§42).
CanPaymentCreate = HasHotelPermission("finance.payment_create")


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


def _collect_reservation_payments(request: Request, reservation) -> list:
    """Every Payment on the reservation's folio(s), oldest first, with FX.

    Includes voided/reversed rows for an honest ledger in the details/edit view;
    the derived ``paid`` total counts only POSTED amounts (see
    ``reservation_financials``). Uses the prefetched ``folios__payments`` cache
    when present, so no N+1 on the list path.
    """
    from apps.finance.serializers import PaymentSerializer

    payments = []
    for folio in reservation.folios.all():
        payments.extend(folio.payments.all())
    payments.sort(key=lambda p: (p.paid_at, p.id))
    return PaymentSerializer(payments, many=True, context={"request": request}).data


def _financial_summary_payload(request: Request, reservation) -> dict:
    """Build the reservation financial-summary response (§26/§31/§35/§39).

    Money is gated by ``finance.view``: an unauthorized caller still sees the
    non-sensitive shape (currency / nights / is_priced / payment count) but all
    money fields are null and the payments list is empty — masked SERVER-SIDE,
    fail-closed. All amounts are Decimal-as-string (money() upstream)."""
    from .services import reservation_financials

    hotel = request.hotel
    can_money = has_hotel_permission(request.user, hotel, "finance.view")
    fin = reservation_financials(reservation, hotel=hotel)

    def s(value):
        return str(value) if value is not None else None

    payload = {
        "reservation": reservation.id,
        "reservation_number": reservation.reservation_number,
        "currency": fin["currency"],
        "nights": fin["nights"],
        "is_priced": fin["is_priced"],
        "can_view_money": can_money,
    }
    if can_money:
        payload.update(
            {
                "nightly_rate": s(fin["nightly_rate"]),
                "reservation_total": s(fin["reservation_total"]),
                "paid": s(fin["paid"]),
                "remaining": s(fin["remaining"]),
                "payment_status": fin["payment_status"],
                "payments": _collect_reservation_payments(request, reservation),
            }
        )
    else:
        payload.update(
            {
                "nightly_rate": None,
                "reservation_total": None,
                "paid": None,
                "remaining": None,
                "payment_status": None,
                "payments": [],
            }
        )
    return payload


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
            # ``folios__payments`` + ``stays`` feed the derived financial summary
            # (paid/remaining/status) and ``stay_status`` on the read serializer
            # without an N+1 (RESERVATIONS-FORM-UX-CORRECTION §25/§35).
            .prefetch_related(
                "lines__room_type", "occupants", "folios__payments", "stays"
            )
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
        # ``occupants`` is not a Reservation model field — it must be passed
        # explicitly, never spread into the model create via ``**data``.
        occupants = data.pop("occupants", None)
        _guard_assignment(request, lines)
        res_status = data.pop("status")
        reservation = services.create_reservation(
            request.hotel,
            lines=lines,
            status=res_status,
            user=request.user,
            occupants=occupants,
            **data,
        )
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
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
            "lines__room_type", "occupants", "folios__payments", "stays"
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
        occupants = data.pop("occupants", None)
        if lines is not None:
            _guard_assignment(request, lines)
        data.pop("status", None)  # status is changed only via confirm/cancel/hold
        services.update_reservation(
            reservation, lines=lines, occupants=occupants, user=request.user, **data
        )
        reservation.refresh_from_db()
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data
        )


class ReservationConfirmView(APIView):
    def get_permissions(self):
        return [CanConfirm()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        reservation = _get_reservation(request, pk)
        services.confirm_reservation(reservation, user=request.user)
        reservation.refresh_from_db()
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data
        )


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
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data
        )


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
        return Response(
            ReservationSerializer(reservation, context={"request": request}).data
        )


class ReservationPaymentCreateView(APIView):
    """Record a pre-arrival DEPOSIT on a future/held/confirmed reservation that
    has NO stay yet (RESERVATIONS-FORM-UX-CORRECTION §27).

    ``POST /api/v1/hotel/reservations/<pk>/payments/`` reuses the sanctioned
    finance money path ``record_reservation_payment`` — which gets/creates the
    reservation's ONE open pre-arrival folio (``ensure_reservation_folio``) and is
    the SAME folio reused at check-in — so no duplicate ledger is created and the
    balance stays derived (invariant #1). Requires ``finance.payment_create``; a
    foreign-currency deposit with a manual FX rate additionally requires
    ``exchange_rate.override`` (mirrors ``stays.ImmediateCheckInView._authorize_deposit``).
    A deposit is refused once the reservation has an in-house stay (that money goes
    through the stay/folio path) and on a cancelled/expired reservation. A zero
    tender is rejected by the serializer. Returns the created payment + the updated
    derived financial summary.
    """

    def get_permissions(self):
        return [CanPaymentCreate()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        reservation = _get_reservation(request, pk)

        # A started stay's money goes through the stay/folio path — never a
        # pre-arrival deposit here (§27, invariant #5).
        if services.has_in_house_stay(reservation):
            raise ReservationHasActiveStay(
                {"reservation": reservation.id, "reason": "deposit_via_stay_folio"}
            )
        # Only a live booking may take a deposit — a cancelled/expired one cannot
        # grow new money.
        if reservation.status not in (
            ReservationStatus.HELD,
            ReservationStatus.CONFIRMED,
        ):
            raise DRFValidationError(
                {
                    "reservation": (
                        "A deposit can only be recorded on a held or confirmed "
                        "reservation."
                    )
                }
            )

        serializer = ReservationDepositSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        deposit = dict(serializer.validated_data)
        self._authorize_deposit(request, request.hotel, deposit)

        from apps.finance.serializers import PaymentSerializer
        from apps.finance.services import record_reservation_payment

        payment = record_reservation_payment(
            reservation,
            amount=deposit.get("amount"),
            method=deposit["method"],
            currency=(deposit.get("currency") or None),
            original_amount=deposit.get("original_amount"),
            exchange_rate=deposit.get("exchange_rate"),
            rate_basis=(deposit.get("rate_basis") or ""),
            payer_name=(deposit.get("payer_name") or ""),
            reference=(deposit.get("reference") or ""),
            notes=(deposit.get("notes") or ""),
            user=request.user,
        )
        return Response(
            {
                "payment": PaymentSerializer(
                    payment, context={"request": request}
                ).data,
                "financial_summary": _financial_summary_payload(request, reservation),
            },
            status=status.HTTP_201_CREATED,
        )

    def _authorize_deposit(self, request: Request, hotel, deposit) -> None:
        # Recording money requires the payment permission (also the view perm); a
        # manual FX rate on a foreign-currency deposit additionally requires the
        # override permission — identical to the immediate-check-in deposit rule.
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


class ReservationFinancialSummaryView(APIView):
    """Full DERIVED financial summary for the details/edit screen (§26/§31/§35/§39).

    ``GET /api/v1/hotel/reservations/<pk>/financial-summary/`` — permission
    ``reservations.view`` to reach the reservation; the MONEY block (rate, total,
    paid, remaining, status, payments+FX) is additionally gated by ``finance.view``
    and masked server-side otherwise. Read-only; nothing is created; the balance is
    re-derived, never stored."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        reservation = generics.get_object_or_404(
            Reservation.objects.filter(hotel=request.hotel).prefetch_related(
                "lines__room_type", "folios__payments"
            ),
            pk=pk,
        )
        return Response(_financial_summary_payload(request, reservation))


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

        # Prefetch what the read serializer's derived fields need so the two
        # small (<=10) lists do not N+1 on lines/folios/payments/stays.
        blocking = base.filter(blocking_q()).prefetch_related(
            "lines__room_type", "occupants", "folios__payments", "stays"
        )
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
                "arrivals": ReservationSerializer(
                    arrivals, many=True, context={"request": request}
                ).data,
                "departures": ReservationSerializer(
                    departures, many=True, context={"request": request}
                ).data,
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


class RoomAvailabilityView(APIView):
    """Per-room availability for a period (RESERVATIONS-FORM-REWORK).

    ``GET /room-availability/?check_in=&check_out=&floor=&room_type=`` lists the
    candidate rooms (optionally filtered by floor / room type) with a per-room
    ``available`` flag for the half-open range ``[check_in, check_out)``. A room
    is available when it is physically bookable, is NOT specifically pinned by a
    blocking overlapping reservation line, and is NOT held by an in-house stay
    overlapping the range. Read-only; behind the reservations-read permission.
    """

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        from apps.rooms.models import Room, RoomStatus
        from apps.stays.models import Stay, StayStatus

        serializer = RoomAvailabilityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        check_in = data["check_in"]
        check_out = data["check_out"]
        hotel = request.hotel
        now = timezone.now()

        rooms = (
            Room.objects.filter(hotel=hotel, is_active=True)
            .exclude(status=RoomStatus.ARCHIVED)
            .select_related("floor", "room_type")
        )
        floor_id = data.get("floor")
        if floor_id is not None:
            rooms = rooms.filter(floor_id=floor_id)
        rt_id = data.get("room_type")
        if rt_id is not None:
            rooms = rooms.filter(room_type_id=rt_id)
        rooms = list(rooms)

        # Rooms specifically pinned by a blocking, overlapping reservation line.
        blocking = (
            Reservation.objects.filter(hotel=hotel)
            .filter(overlap_q(check_in, check_out))
            .filter(blocking_q(now))
        )
        assigned_room_ids = set(
            ReservationRoomLine.objects.filter(
                hotel=hotel, reservation__in=blocking, room__isnull=False
            ).values_list("room_id", flat=True)
        )
        # Rooms held by an in-house stay overlapping the range (planned dates).
        stay_room_ids = set(
            Stay.objects.filter(
                hotel=hotel,
                status=StayStatus.IN_HOUSE,
                planned_check_in_date__lt=check_out,
                planned_check_out_date__gt=check_in,
            ).values_list("room_id", flat=True)
        )

        # Physically bookable rooms, computed once per room type in play.
        bookable_by_type: dict[int, set[int]] = {}
        for room in rooms:
            if room.room_type_id not in bookable_by_type:
                bookable_by_type[room.room_type_id] = (
                    AvailabilityService.bookable_room_ids(hotel, room.room_type)
                )

        currency = (
            getattr(getattr(hotel, "settings", None), "default_currency", "") or ""
        )

        results = []
        for room in rooms:
            rt = room.room_type
            bookable = room.id in bookable_by_type.get(room.room_type_id, set())
            available = (
                bookable
                and room.id not in assigned_room_ids
                and room.id not in stay_room_ids
            )
            results.append(
                {
                    "id": room.id,
                    "number": room.number,
                    "floor_name": room.floor.name if room.floor_id else None,
                    "floor_number": room.floor.number if room.floor_id else None,
                    "room_type_id": rt.id,
                    "room_type_name": rt.name,
                    "base_capacity": rt.base_capacity,
                    "max_capacity": rt.max_capacity,
                    "amenities": rt.amenities,
                    # Decimal as string (matches the DecimalField convention).
                    "base_rate": str(rt.base_rate) if rt.base_rate is not None else None,
                    "currency": currency,
                    "available": available,
                }
            )
        return Response({"results": results})


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
