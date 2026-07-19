"""Operations API views (Phase 10), under /api/v1/hotel/operations/.

Scoped to the caller's hotel, guarded by ``housekeeping.*`` / ``maintenance.*``
/ ``lost_found.*`` permissions. A suspended hotel is read-only. All mutations
go through the domain services; room status is never written from a view.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import (
    CrossTenantReference,
    PermissionDenied,
)
from apps.guests.models import Guest
from apps.rbac.permissions import HasHotelMembership, HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomStatus
from apps.stays.models import Stay
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .models import (
    HousekeepingStatus,
    HousekeepingTask,
    HousekeepingTaskType,
    LostFoundCategory,
    LostFoundItem,
    LostFoundStatus,
    LostReport,
    LostReportStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
    OperationPriority,
)
from .serializers import (
    AssignSerializer,
    CancelSerializer,
    HousekeepingComeBackLaterSerializer,
    HousekeepingCompleteSerializer,
    HousekeepingCreateSerializer,
    HousekeepingStatusSerializer,
    HousekeepingTaskListSerializer,
    HousekeepingTaskSerializer,
    HousekeepingUpdateSerializer,
    LostFoundClaimSerializer,
    LostFoundCloseSerializer,
    LostFoundCreateSerializer,
    LostFoundDisposeSerializer,
    LostFoundItemListSerializer,
    LostFoundItemSerializer,
    LostFoundStatusSerializer,
    LostFoundUpdateSerializer,
    LostReportCreateSerializer,
    LostReportHandoverSerializer,
    LostReportListSerializer,
    LostReportMatchSerializer,
    LostReportReasonSerializer,
    LostReportSerializer,
    LostReportStatusSerializer,
    LostReportUpdateSerializer,
    MaintenanceCloseSerializer,
    MaintenanceCreateSerializer,
    MaintenanceRequestListSerializer,
    MaintenanceRequestSerializer,
    MaintenanceResolveSerializer,
    MaintenanceStatusSerializer,
    MaintenanceUpdateSerializer,
)

User = get_user_model()

HkView = HasHotelPermission("housekeeping.view")
HkCreate = HasHotelPermission("housekeeping.create")
HkUpdate = HasHotelPermission("housekeeping.update")
HkCancel = HasHotelPermission("housekeeping.cancel")
HkStatus = HasHotelPermission("housekeeping.status_update")
HkAssign = HasHotelPermission("housekeeping.assign")
HkInspect = HasHotelPermission("housekeeping.inspect")

MtView = HasHotelPermission("maintenance.view")
MtCreate = HasHotelPermission("maintenance.create")
MtUpdate = HasHotelPermission("maintenance.update")
MtCancel = HasHotelPermission("maintenance.cancel")
MtStatus = HasHotelPermission("maintenance.status_update")
MtAssign = HasHotelPermission("maintenance.assign")
MtClose = HasHotelPermission("maintenance.close")

LfView = HasHotelPermission("lost_found.view")
LfCreate = HasHotelPermission("lost_found.create")
LfUpdate = HasHotelPermission("lost_found.update")
LfStatus = HasHotelPermission("lost_found.status_update")
LfClose = HasHotelPermission("lost_found.close")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _get(model, request, pk):
    return generics.get_object_or_404(model, pk=pk, hotel=request.hotel)


def _resolve_user(user_id):
    """An assignee id must at least be a real user; membership is checked in
    the domain service (both failures surface as cross_tenant_reference)."""
    if user_id is None:
        return None
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise CrossTenantReference({"field": "assigned_to"})
    return user


def _detail(serializer_cls, obj, request):
    """Render a DETAIL serializer WITH the request in context so the WP6
    disclosure gates (internal_notes / claimed_by_phone) can evaluate the
    caller's permissions. Fail-closed if the request is ever absent."""
    return serializer_cls(obj, context={"request": request}).data


def _guard_initial_assign(request, assigned_to, assign_code: str) -> None:
    """Initial-assign guard (WP6, goal A): supplying a non-empty ``assigned_to``
    at CREATE time requires the caller to ALSO hold the domain's assign
    permission, on top of ``.create``. A caller with ``.create`` but not
    ``.assign`` may still create the item WITHOUT an assignee; a create that
    DOES carry an assignee without ``.assign`` is refused 403 — never silently
    dropped, never accepted. Reassignment later already requires ``.assign``."""
    if assigned_to is not None and not has_hotel_permission(
        request.user, request.hotel, assign_code
    ):
        raise PermissionDenied()


# --- Housekeeping ---------------------------------------------------------------

# The cleaning card's "upcoming arrival" hint covers arrivals from the hotel
# business date through this many days ahead (today + tomorrow). Kept explicit
# and named so the near-window is auditable, not a magic number.
UPCOMING_ARRIVAL_WINDOW_DAYS = 1


class HousekeepingListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [HkCreate()] if self.request.method == "POST" else [HkView()]

    def get_serializer_class(self):
        return HousekeepingTaskListSerializer

    def get_queryset(self):
        # select_related walks room -> room_type / floor (and assigned_to) so the
        # list serializer reads room_type_name / floor_name / floor_number / the
        # assignee with NO per-row query. Occupancy + upcoming-arrival are NOT
        # here — they are page-level batch maps built in ``list`` below.
        qs = HousekeepingTask.objects.filter(hotel=self.request.hotel).select_related(
            "room__room_type", "room__floor", "assigned_to"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in HousekeepingStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("task_type") in {c for c, _ in HousekeepingTaskType.choices}:
            qs = qs.filter(task_type=p["task_type"])
        if p.get("priority") in {c for c, _ in OperationPriority.choices}:
            qs = qs.filter(priority=p["priority"])
        if p.get("room") and str(p["room"]).isdigit():
            qs = qs.filter(room_id=int(p["room"]))
        if p.get("assigned_to") and str(p["assigned_to"]).isdigit():
            qs = qs.filter(assigned_to_id=int(p["assigned_to"]))
        # Final closure: an attendant's own queue in one flag.
        if p.get("mine") == "true":
            qs = qs.filter(assigned_to=self.request.user)
        if p.get("date"):
            qs = qs.filter(requested_at__date=p["date"])
        if p.get("search"):
            qs = (
                qs.filter(task_number__icontains=p["search"])
                | qs.filter(room__number__icontains=p["search"])
                | qs.filter(notes__icontains=p["search"])
            )
        ordering = p.get("ordering")
        if ordering in ("priority", "-priority"):
            # Shared severity ordering (urgent → high → normal → low), never the
            # raw CharField. Tie-break: newest first then -id (deterministic).
            qs = services.order_by_priority_rank(
                qs, ordering=ordering, time_field="requested_at"
            )
        elif ordering in (
            "requested_at", "-requested_at", "task_number", "-task_number",
        ):
            qs = qs.order_by(ordering)
        return qs.distinct()

    def list(self, request: Request, *args, **kwargs) -> Response:
        """Return the page plus TWO page-level batch maps so occupancy and the
        upcoming-arrival hint cost a CONSTANT number of queries regardless of how
        many tasks the page holds (no N+1):

        * ``occupied_room_ids`` — ONE query over the page's rooms for in-house
          ``Stay`` rows (occupancy stays derived from ``Stay``, never a status).
        * ``upcoming_arrival_map`` — ONE query over the page's rooms for CONFIRMED
          reservations arriving within the near window; keyed room_id -> soonest
          arrival date/time. It carries NO reservation number (HK-only privacy).

        Both are scoped to ``request.hotel`` AND to the page's room_ids, then
        passed to the serializer via context where the ``SerializerMethodField``s
        read them O(1).
        """
        from apps.reservations.models import ReservationRoomLine, ReservationStatus
        from apps.shifts.services import get_business_date
        from apps.stays.models import Stay, StayStatus

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        tasks = page if page is not None else list(queryset)

        room_ids = {t.room_id for t in tasks if t.room_id is not None}
        occupied_room_ids: set[int] = set()
        upcoming_arrival_map: dict[int, dict] = {}
        if room_ids:
            occupied_room_ids = set(
                Stay.objects.filter(
                    hotel=request.hotel,
                    room_id__in=room_ids,
                    status=StayStatus.IN_HOUSE,
                ).values_list("room_id", flat=True)
            )
            business_date = get_business_date(request.hotel)
            window_end = business_date + timedelta(days=UPCOMING_ARRIVAL_WINDOW_DAYS)
            arrival_rows = (
                ReservationRoomLine.objects.filter(
                    hotel=request.hotel,
                    room_id__in=room_ids,
                    reservation__status=ReservationStatus.CONFIRMED,
                    reservation__check_in_date__gte=business_date,
                    reservation__check_in_date__lte=window_end,
                )
                .order_by(
                    "reservation__check_in_date",
                    "reservation__expected_arrival_time",
                    "reservation_id",
                )
                .values_list(
                    "room_id",
                    "reservation__check_in_date",
                    "reservation__expected_arrival_time",
                )
            )
            for room_id, check_in_date, arrival_time in arrival_rows:
                # Rows are soonest-first; keep only the earliest arrival per room.
                if room_id not in upcoming_arrival_map:
                    upcoming_arrival_map[room_id] = {
                        "arrival_date": check_in_date,
                        "arrival_time": arrival_time,
                    }

        context = {
            **self.get_serializer_context(),
            "occupied_room_ids": occupied_room_ids,
            "upcoming_arrival_map": upcoming_arrival_map,
        }
        serializer = self.get_serializer_class()(tasks, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = HousekeepingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _guard_initial_assign(request, data.get("assigned_to"), "housekeeping.assign")
        task = services.create_housekeeping_task(
            request.hotel,
            user=request.user,
            room=_get(Room, request, data["room"]),
            stay=_get(Stay, request, data["stay"]) if data.get("stay") else None,
            task_type=data["task_type"],
            priority=data["priority"],
            assigned_to=_resolve_user(data.get("assigned_to")),
            notes=data.get("notes", ""),
            internal_notes=data.get("internal_notes", ""),
        )
        return Response(
            _detail(HousekeepingTaskSerializer, task, request),
            status=http_status.HTTP_201_CREATED,
        )


class HousekeepingDetailView(APIView):
    def get_permissions(self):
        return [HkUpdate()] if self.request.method == "PATCH" else [HkView()]

    def get(self, request: Request, pk: int) -> Response:
        task = _get(HousekeepingTask, request, pk)
        return Response(_detail(HousekeepingTaskSerializer, task, request))

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = HousekeepingUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = services.update_housekeeping_task(
            task, user=request.user, **serializer.validated_data
        )
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class HousekeepingStatusView(APIView):
    permission_classes = [HkStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = HousekeepingStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = services.change_housekeeping_status(
            task,
            new_status=serializer.validated_data["status"],
            user=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class HousekeepingAssignView(APIView):
    permission_classes = [HkAssign]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = services.assign_housekeeping_task(
            task,
            assigned_to=_resolve_user(serializer.validated_data["assigned_to"]),
            user=request.user,
        )
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class HousekeepingCompleteView(APIView):
    permission_classes = [HkStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = HousekeepingCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = services.complete_housekeeping_task(
            task,
            user=request.user,
            mark_room_available=serializer.validated_data["mark_room_available"],
            note=serializer.validated_data.get("note", ""),
            service_outcome=serializer.validated_data["service_outcome"],
        )
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class HousekeepingComeBackLaterView(APIView):
    # Non-terminal defer event — same permission as other status updates.
    permission_classes = [HkStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = HousekeepingComeBackLaterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = services.come_back_later_housekeeping_task(
            task,
            user=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class HousekeepingCancelView(APIView):
    permission_classes = [HkCancel]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = services.cancel_housekeeping_task(
            task, reason=serializer.validated_data["reason"], user=request.user
        )
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class HousekeepingInspectApproveView(APIView):
    permission_classes = [HkInspect]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        note = str(request.data.get("note", "") or "")[:255]
        task = services.approve_inspection(task, user=request.user, note=note)
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class HousekeepingInspectRejectView(APIView):
    permission_classes = [HkInspect]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = CancelSerializer(data=request.data)  # {"reason": ...}
        serializer.is_valid(raise_exception=True)
        task = services.reject_inspection(
            task, reason=serializer.validated_data["reason"], user=request.user
        )
        return Response(_detail(HousekeepingTaskSerializer, task, request))


class ArrivalRoomsNotReadyView(APIView):
    """Rooms pinned to a CONFIRMED arrival on the hotel business date that are
    not yet ready for check-in (not manually available, or still occupied).
    Derived on the fly from existing data — nothing is stored."""

    permission_classes = [HkView]

    def get(self, request: Request) -> Response:
        from apps.reservations.models import Reservation, ReservationStatus
        from apps.shifts.services import get_business_date
        from apps.stays.models import Stay, StayStatus

        today = get_business_date(request.hotel)
        # WP6 disclosure gate (goal B): the FULL reservation number is a booking
        # reference. A housekeeping-only caller still sees the operational info
        # (room / unit + arrival presence & date) but NOT the full number — that
        # is present ONLY for a caller who also holds ``reservations.view``. No
        # RBAC change: the field's PRESENCE is gated by the existing permission.
        can_see_reservation_number = has_hotel_permission(
            request.user, request.hotel, "reservations.view"
        )
        pinned = (
            Reservation.objects.filter(
                hotel=request.hotel,
                status=ReservationStatus.CONFIRMED,
                check_in_date=today,
            )
            .prefetch_related("lines__room")
        )
        occupied = set(
            Stay.objects.filter(
                hotel=request.hotel, status=StayStatus.IN_HOUSE
            ).values_list("room_id", flat=True)
        )
        rows = []
        seen = set()
        for reservation in pinned:
            for line in reservation.lines.all():
                room = line.room
                if room is None or room.id in seen:
                    continue
                not_ready = (
                    room.status != RoomStatus.AVAILABLE or room.id in occupied
                )
                if not_ready:
                    seen.add(room.id)
                    row = {
                        "room": room.id,
                        "room_number": room.number,
                        "room_status": room.status,
                        "occupied": room.id in occupied,
                        # Operational arrival info, safe for a housekeeping-only
                        # caller (these are pinned to the hotel business date).
                        "arrival_date": (
                            reservation.check_in_date.isoformat()
                            if reservation.check_in_date
                            else None
                        ),
                    }
                    if can_see_reservation_number:
                        row["reservation_number"] = reservation.reservation_number
                    rows.append(row)
        rows.sort(key=lambda r: r["room_number"])
        return Response(rows)


# --- Maintenance ------------------------------------------------------------------


class MaintenanceListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [MtCreate()] if self.request.method == "POST" else [MtView()]

    def get_serializer_class(self):
        return MaintenanceRequestListSerializer

    def get_queryset(self):
        # The list serializer's added ``description`` / ``started_at`` are DIRECT
        # columns on MaintenanceRequest, so the existing room/assignee joins are
        # sufficient — no extra select_related, no per-row query.
        qs = MaintenanceRequest.objects.filter(hotel=self.request.hotel).select_related(
            "room", "assigned_to"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in MaintenanceStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("category") in {c for c, _ in MaintenanceCategory.choices}:
            qs = qs.filter(category=p["category"])
        if p.get("priority") in {c for c, _ in OperationPriority.choices}:
            qs = qs.filter(priority=p["priority"])
        if p.get("room") and str(p["room"]).isdigit():
            qs = qs.filter(room_id=int(p["room"]))
        if p.get("assigned_to") and str(p["assigned_to"]).isdigit():
            qs = qs.filter(assigned_to_id=int(p["assigned_to"]))
        if p.get("affects_room_availability") in ("true", "false"):
            qs = qs.filter(
                affects_room_availability=p["affects_room_availability"] == "true"
            )
        if p.get("search"):
            qs = (
                qs.filter(request_number__icontains=p["search"])
                | qs.filter(title__icontains=p["search"])
                | qs.filter(description__icontains=p["search"])
                | qs.filter(room__number__icontains=p["search"])
            )
        ordering = p.get("ordering")
        if ordering in ("priority", "-priority"):
            # Same shared severity ordering as housekeeping (urgent → high →
            # normal → low), never the raw CharField (alphabetical would give
            # high < low < normal < urgent). Tie-break: newest first then -id.
            qs = services.order_by_priority_rank(
                qs, ordering=ordering, time_field="reported_at"
            )
        elif ordering in (
            "reported_at", "-reported_at", "request_number", "-request_number",
        ):
            qs = qs.order_by(ordering)
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = MaintenanceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _guard_initial_assign(request, data.get("assigned_to"), "maintenance.assign")
        obj = services.create_maintenance_request(
            request.hotel,
            user=request.user,
            room=_get(Room, request, data["room"]) if data.get("room") else None,
            stay=_get(Stay, request, data["stay"]) if data.get("stay") else None,
            title=data["title"],
            description=data.get("description", ""),
            category=data["category"],
            priority=data["priority"],
            affects_room_availability=data["affects_room_availability"],
            room_block_status=data["room_block_status"],
            assigned_to=_resolve_user(data.get("assigned_to")),
            internal_notes=data.get("internal_notes", ""),
        )
        return Response(
            _detail(MaintenanceRequestSerializer, obj, request),
            status=http_status.HTTP_201_CREATED,
        )


class MaintenanceDetailView(APIView):
    def get_permissions(self):
        return [MtUpdate()] if self.request.method == "PATCH" else [MtView()]

    def get(self, request: Request, pk: int) -> Response:
        obj = _get(MaintenanceRequest, request, pk)
        return Response(_detail(MaintenanceRequestSerializer, obj, request))

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        obj = _get(MaintenanceRequest, request, pk)
        serializer = MaintenanceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = services.update_maintenance_request(
            obj, user=request.user, **serializer.validated_data
        )
        return Response(_detail(MaintenanceRequestSerializer, obj, request))


class MaintenanceStatusView(APIView):
    permission_classes = [MtStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        obj = _get(MaintenanceRequest, request, pk)
        serializer = MaintenanceStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = services.change_maintenance_status(
            obj,
            new_status=serializer.validated_data["status"],
            user=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(_detail(MaintenanceRequestSerializer, obj, request))


class MaintenanceAssignView(APIView):
    permission_classes = [MtAssign]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        obj = _get(MaintenanceRequest, request, pk)
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = services.assign_maintenance_request(
            obj,
            assigned_to=_resolve_user(serializer.validated_data["assigned_to"]),
            user=request.user,
        )
        return Response(_detail(MaintenanceRequestSerializer, obj, request))


class MaintenanceResolveView(APIView):
    permission_classes = [MtStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        obj = _get(MaintenanceRequest, request, pk)
        serializer = MaintenanceResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = services.resolve_maintenance_request(
            obj,
            user=request.user,
            resolution_notes=serializer.validated_data.get("resolution_notes", ""),
            note=serializer.validated_data.get("note", ""),
        )
        return Response(_detail(MaintenanceRequestSerializer, obj, request))


class MaintenanceCloseView(APIView):
    permission_classes = [MtClose]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        obj = _get(MaintenanceRequest, request, pk)
        serializer = MaintenanceCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = services.close_maintenance_request(
            obj,
            user=request.user,
            room_next_status=serializer.validated_data["room_next_status"],
            note=serializer.validated_data.get("note", ""),
        )
        return Response(_detail(MaintenanceRequestSerializer, obj, request))


class MaintenanceCancelView(APIView):
    permission_classes = [MtCancel]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        obj = _get(MaintenanceRequest, request, pk)
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = services.cancel_maintenance_request(
            obj, reason=serializer.validated_data["reason"], user=request.user
        )
        return Response(_detail(MaintenanceRequestSerializer, obj, request))


# --- Lost & Found -----------------------------------------------------------------


class LostFoundListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [LfCreate()] if self.request.method == "POST" else [LfView()]

    def get_serializer_class(self):
        return LostFoundItemListSerializer

    def get_queryset(self):
        # ``found_by`` is select_related so the list serializer's ``found_by_name``
        # (found_by.full_name) adds NO per-row query. ``description`` /
        # ``claimed_by_name`` are direct columns and need no join.
        qs = LostFoundItem.objects.filter(hotel=self.request.hotel).select_related(
            "room", "guest", "found_by"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in LostFoundStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("category") in {c for c, _ in LostFoundCategory.choices}:
            qs = qs.filter(category=p["category"])
        if p.get("room") and str(p["room"]).isdigit():
            qs = qs.filter(room_id=int(p["room"]))
        if p.get("guest") and str(p["guest"]).isdigit():
            qs = qs.filter(guest_id=int(p["guest"]))
        if p.get("date"):
            qs = qs.filter(found_at__date=p["date"])
        if p.get("search"):
            qs = (
                qs.filter(item_number__icontains=p["search"])
                | qs.filter(title__icontains=p["search"])
                | qs.filter(description__icontains=p["search"])
                | qs.filter(found_location__icontains=p["search"])
                | qs.filter(stored_location__icontains=p["search"])
            )
        ordering = p.get("ordering")
        if ordering in ("found_at", "-found_at", "item_number", "-item_number"):
            qs = qs.order_by(ordering)
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = LostFoundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        item = services.create_lost_found_item(
            request.hotel,
            user=request.user,
            title=data["title"],
            description=data.get("description", ""),
            category=data["category"],
            status=data["status"],
            found_at=data.get("found_at"),
            found_location=data.get("found_location", ""),
            room=_get(Room, request, data["room"]) if data.get("room") else None,
            stay=_get(Stay, request, data["stay"]) if data.get("stay") else None,
            guest=_get(Guest, request, data["guest"]) if data.get("guest") else None,
            stored_location=data.get("stored_location", ""),
            notes=data.get("notes", ""),
            internal_notes=data.get("internal_notes", ""),
        )
        return Response(
            _detail(LostFoundItemSerializer, item, request),
            status=http_status.HTTP_201_CREATED,
        )


class LostFoundDetailView(APIView):
    def get_permissions(self):
        return [LfUpdate()] if self.request.method == "PATCH" else [LfView()]

    def get(self, request: Request, pk: int) -> Response:
        item = _get(LostFoundItem, request, pk)
        return Response(_detail(LostFoundItemSerializer, item, request))

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        item = _get(LostFoundItem, request, pk)
        serializer = LostFoundUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refs = {}
        for field, model in (("room", Room), ("stay", Stay), ("guest", Guest)):
            if field in data:
                refs[field] = (
                    _get(model, request, data[field]) if data[field] else None
                )
        meta = {k: v for k, v in data.items() if k not in ("room", "stay", "guest")}
        item = services.update_lost_found_item(
            item, user=request.user, refs=refs, **meta
        )
        return Response(_detail(LostFoundItemSerializer, item, request))


class LostFoundStatusView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        item = _get(LostFoundItem, request, pk)
        serializer = LostFoundStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.change_lost_found_status(
            item,
            new_status=serializer.validated_data["status"],
            user=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(_detail(LostFoundItemSerializer, item, request))


class LostFoundClaimView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        item = _get(LostFoundItem, request, pk)
        serializer = LostFoundClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.claim_lost_found_item(
            item, user=request.user, **serializer.validated_data
        )
        return Response(_detail(LostFoundItemSerializer, item, request))


class LostFoundReturnView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        item = _get(LostFoundItem, request, pk)
        serializer = LostFoundClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.return_lost_found_item(
            item, user=request.user, **serializer.validated_data
        )
        return Response(_detail(LostFoundItemSerializer, item, request))


class LostFoundDisposeView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        item = _get(LostFoundItem, request, pk)
        serializer = LostFoundDisposeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.dispose_lost_found_item(
            item, reason=serializer.validated_data.get("reason", ""), user=request.user
        )
        return Response(_detail(LostFoundItemSerializer, item, request))


class LostFoundCloseView(APIView):
    permission_classes = [LfClose]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        item = _get(LostFoundItem, request, pk)
        serializer = LostFoundCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.close_lost_found_item(
            item, user=request.user, note=serializer.validated_data.get("note", "")
        )
        return Response(_detail(LostFoundItemSerializer, item, request))


# --- Lost report (LR — the "I lost X" cycle + safe manual matching) ----------
#
# PERMISSION REUSE (owner decision — NO new codes, NO RBAC change): the lost
# report reuses the SAME ``lost_found.*`` permissions as the found item —
#   view / candidates      -> lost_found.view      (LfView)
#   create (file a report)  -> lost_found.create    (LfCreate)
#   edit (PATCH metadata)   -> lost_found.update     (LfUpdate)
#   status / match / unmatch / handover / close-unfound / cancel
#                           -> lost_found.status_update (LfStatus)
# so a role that can act on lost-and-found can act on lost reports too.


class LostReportListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [LfCreate()] if self.request.method == "POST" else [LfView()]

    def get_serializer_class(self):
        return LostReportListSerializer

    def get_queryset(self):
        # select_related feeds the list serializer's guest_name /
        # reservation_number / room_number (via stay->room) and the matched-item
        # summary with NO per-row query.
        qs = LostReport.objects.filter(hotel=self.request.hotel).select_related(
            "guest", "reservation", "stay__room", "matched_found_item"
        )
        p = self.request.query_params
        if p.get("status") in {c for c, _ in LostReportStatus.choices}:
            qs = qs.filter(status=p["status"])
        if p.get("category") in {c for c, _ in LostFoundCategory.choices}:
            qs = qs.filter(category=p["category"])
        if p.get("guest") and str(p["guest"]).isdigit():
            qs = qs.filter(guest_id=int(p["guest"]))
        if p.get("stay") and str(p["stay"]).isdigit():
            qs = qs.filter(stay_id=int(p["stay"]))
        if p.get("date"):
            qs = qs.filter(created_at__date=p["date"])
        if p.get("search"):
            qs = (
                qs.filter(report_number__icontains=p["search"])
                | qs.filter(description__icontains=p["search"])
                | qs.filter(reporter_name__icontains=p["search"])
                | qs.filter(last_seen_location__icontains=p["search"])
            )
        ordering = p.get("ordering")
        if ordering in ("created_at", "-created_at", "report_number", "-report_number"):
            qs = qs.order_by(ordering)
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = LostReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report = services.create_lost_report(
            request.hotel,
            user=request.user,
            category=data["category"],
            description=data.get("description", ""),
            distinctive_marks=data.get("distinctive_marks", ""),
            last_seen_location=data.get("last_seen_location", ""),
            lost_at=data.get("lost_at"),
            reporter_name=data.get("reporter_name", ""),
            reporter_phone=data.get("reporter_phone", ""),
            guest=_get(Guest, request, data["guest"]) if data.get("guest") else None,
            stay=_get(Stay, request, data["stay"]) if data.get("stay") else None,
            reservation=(
                _get(Reservation, request, data["reservation"])
                if data.get("reservation")
                else None
            ),
            internal_notes=data.get("internal_notes", ""),
        )
        return Response(
            _detail(LostReportSerializer, report, request),
            status=http_status.HTTP_201_CREATED,
        )


class LostReportDetailView(APIView):
    def get_permissions(self):
        return [LfUpdate()] if self.request.method == "PATCH" else [LfView()]

    def get(self, request: Request, pk: int) -> Response:
        report = _get(LostReport, request, pk)
        return Response(_detail(LostReportSerializer, report, request))

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        report = _get(LostReport, request, pk)
        serializer = LostReportUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        refs = {}
        for field, model in (
            ("guest", Guest),
            ("stay", Stay),
            ("reservation", Reservation),
        ):
            if field in data:
                refs[field] = _get(model, request, data[field]) if data[field] else None
        meta = {
            k: v for k, v in data.items() if k not in ("guest", "stay", "reservation")
        }
        report = services.update_lost_report(
            report, user=request.user, refs=refs, **meta
        )
        return Response(_detail(LostReportSerializer, report, request))


class LostReportStatusView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        report = _get(LostReport, request, pk)
        serializer = LostReportStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.change_lost_report_status(
            report,
            new_status=serializer.validated_data["status"],
            user=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(_detail(LostReportSerializer, report, request))


class LostReportMatchView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        report = _get(LostReport, request, pk)
        serializer = LostReportMatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The found item is fetched hotel-scoped (404 for a cross-tenant id); the
        # service re-checks same-hotel + matchability under the row lock.
        found_item = _get(LostFoundItem, request, serializer.validated_data["found_item"])
        report = services.confirm_match(report, found_item, user=request.user)
        return Response(_detail(LostReportSerializer, report, request))


class LostReportUnmatchView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        report = _get(LostReport, request, pk)
        serializer = LostReportReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.unmatch(
            report, reason=serializer.validated_data.get("reason", ""), user=request.user
        )
        return Response(_detail(LostReportSerializer, report, request))


class LostReportHandoverView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        report = _get(LostReport, request, pk)
        serializer = LostReportHandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.hand_over_matched_report(
            report, user=request.user, **serializer.validated_data
        )
        return Response(_detail(LostReportSerializer, report, request))


class LostReportCloseUnfoundView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        report = _get(LostReport, request, pk)
        serializer = LostReportReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.close_unfound(
            report, reason=serializer.validated_data.get("reason", ""), user=request.user
        )
        return Response(_detail(LostReportSerializer, report, request))


class LostReportCancelView(APIView):
    permission_classes = [LfStatus]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        report = _get(LostReport, request, pk)
        serializer = LostReportReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.cancel_lost_report(
            report, reason=serializer.validated_data.get("reason", ""), user=request.user
        )
        return Response(_detail(LostReportSerializer, report, request))


#: Safety cap on the candidate picker payload — a bounded shortlist, never the
#: whole store. The ``search`` / ``category`` filters narrow it further.
CANDIDATE_LIMIT = 100


class LostReportCandidatesView(APIView):
    """Matchable FOUND items in the SAME hotel for a report's manual match.

    Returns items that are still holdable (NOT returned/disposed/closed) and NOT
    already actively matched by another report, via ``LostFoundItemListSerializer``
    (so NO phone / proof / unsafe oracle leaks). ``lost_found.view`` gates it —
    the same read permission as the lists."""

    permission_classes = [LfView]

    def get(self, request: Request, pk: int) -> Response:
        # 404s a cross-tenant / unknown report id, keeping the picker hotel-scoped.
        _get(LostReport, request, pk)
        already_matched_ids = LostReport.objects.filter(
            hotel=request.hotel,
            status=LostReportStatus.MATCHED,
            matched_found_item__isnull=False,
        ).values_list("matched_found_item_id", flat=True)
        qs = (
            LostFoundItem.objects.filter(hotel=request.hotel)
            .exclude(status__in=services.NON_MATCHABLE_FOUND_STATUSES)
            .exclude(id__in=already_matched_ids)
            .select_related("room", "guest", "found_by")
        )
        p = self.request.query_params
        if p.get("category") in {c for c, _ in LostFoundCategory.choices}:
            qs = qs.filter(category=p["category"])
        if p.get("search"):
            qs = (
                qs.filter(item_number__icontains=p["search"])
                | qs.filter(title__icontains=p["search"])
                | qs.filter(description__icontains=p["search"])
                | qs.filter(found_location__icontains=p["search"])
            )
        qs = qs.distinct().order_by("-found_at", "-id")[:CANDIDATE_LIMIT]
        data = LostFoundItemListSerializer(
            qs, many=True, context={"request": request}
        ).data
        return Response(data)


# --- Overview ---------------------------------------------------------------------


class CanViewOperationsOverview(HasHotelMembership):
    """ANY of the three view permissions unlocks the shared overview counters.

    A plain permission-class ``|`` would break here: ``BaseHotelPermission``
    raises (rather than returns False) on a missing code, which would
    short-circuit the OR before the next permission is tried.
    """

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        for code in ("housekeeping.view", "maintenance.view", "lost_found.view"):
            if has_hotel_permission(request.user, request.hotel, code):
                return True
        raise PermissionDenied()


class OperationsOverviewView(APIView):
    permission_classes = [CanViewOperationsOverview]

    def get(self, request: Request) -> Response:
        hotel = request.hotel
        rooms = Room.objects.filter(hotel=hotel, is_active=True)
        hk = HousekeepingTask.objects.filter(hotel=hotel)
        mt = MaintenanceRequest.objects.filter(hotel=hotel)
        lf = LostFoundItem.objects.filter(hotel=hotel)
        lr = LostReport.objects.filter(hotel=hotel)
        return Response(
            {
                "dirty_rooms": rooms.filter(status=RoomStatus.DIRTY).count(),
                "hk_pending": hk.filter(
                    status__in=[
                        HousekeepingStatus.PENDING,
                        HousekeepingStatus.ASSIGNED,
                    ]
                ).count(),
                "hk_in_progress": hk.filter(
                    status=HousekeepingStatus.IN_PROGRESS
                ).count(),
                "open_maintenance": mt.filter(
                    status__in=services.OPEN_MAINTENANCE_STATUSES
                ).count(),
                "rooms_under_maintenance": rooms.filter(
                    status__in=[RoomStatus.MAINTENANCE, RoomStatus.OUT_OF_SERVICE]
                ).count(),
                "lost_found_open": lf.filter(
                    status__in=[LostFoundStatus.FOUND, LostFoundStatus.STORED]
                ).count(),
                # LOST-REPORT statcards (additive):
                "open_lost_reports": lr.filter(
                    status__in=[
                        LostReportStatus.OPEN,
                        LostReportStatus.SEARCHING,
                    ]
                ).count(),
                "stored_found_items": lf.filter(
                    status__in=[LostFoundStatus.FOUND, LostFoundStatus.STORED]
                ).count(),
                "confirmed_matches": lr.filter(
                    status=LostReportStatus.MATCHED
                ).count(),
                "returned_reports": lr.filter(
                    status=LostReportStatus.RETURNED
                ).count(),
                "urgent_tasks": (
                    hk.filter(
                        priority=OperationPriority.URGENT,
                        status__in=services.ACTIVE_HK_STATUSES,
                    ).count()
                    + mt.filter(
                        priority=OperationPriority.URGENT,
                        status__in=services.OPEN_MAINTENANCE_STATUSES,
                    ).count()
                ),
            }
        )
