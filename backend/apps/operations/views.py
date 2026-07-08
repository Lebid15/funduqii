"""Operations API views (Phase 10), under /api/v1/hotel/operations/.

Scoped to the caller's hotel, guarded by ``housekeeping.*`` / ``maintenance.*``
/ ``lost_found.*`` permissions. A suspended hotel is read-only. All mutations
go through the domain services; room status is never written from a view.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework import status as http_status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import (
    CrossTenantReference,
    HotelSuspended,
    PermissionDenied,
)
from apps.guests.models import Guest
from apps.rbac.permissions import HasHotelMembership, HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.rooms.models import Room, RoomStatus
from apps.stays.models import Stay
from apps.tenancy.models import HotelStatus

from . import services
from .models import (
    HousekeepingStatus,
    HousekeepingTask,
    HousekeepingTaskType,
    LostFoundCategory,
    LostFoundItem,
    LostFoundStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
    OperationPriority,
)
from .serializers import (
    AssignSerializer,
    CancelSerializer,
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
    if request.hotel.status == HotelStatus.SUSPENDED:
        raise HotelSuspended()


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


# --- Housekeeping ---------------------------------------------------------------


class HousekeepingListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [HkCreate()] if self.request.method == "POST" else [HkView()]

    def get_serializer_class(self):
        return HousekeepingTaskListSerializer

    def get_queryset(self):
        qs = HousekeepingTask.objects.filter(hotel=self.request.hotel).select_related(
            "room", "assigned_to"
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
        if p.get("date"):
            qs = qs.filter(requested_at__date=p["date"])
        if p.get("search"):
            qs = (
                qs.filter(task_number__icontains=p["search"])
                | qs.filter(room__number__icontains=p["search"])
                | qs.filter(notes__icontains=p["search"])
            )
        ordering = p.get("ordering")
        if ordering in (
            "requested_at", "-requested_at", "task_number", "-task_number",
            "priority", "-priority",
        ):
            qs = qs.order_by(ordering)
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = HousekeepingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
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
            HousekeepingTaskSerializer(task).data, status=http_status.HTTP_201_CREATED
        )


class HousekeepingDetailView(APIView):
    def get_permissions(self):
        return [HkUpdate()] if self.request.method == "PATCH" else [HkView()]

    def get(self, request: Request, pk: int) -> Response:
        task = _get(HousekeepingTask, request, pk)
        return Response(HousekeepingTaskSerializer(task).data)

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        task = _get(HousekeepingTask, request, pk)
        serializer = HousekeepingUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = services.update_housekeeping_task(
            task, user=request.user, **serializer.validated_data
        )
        return Response(HousekeepingTaskSerializer(task).data)


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
        return Response(HousekeepingTaskSerializer(task).data)


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
        return Response(HousekeepingTaskSerializer(task).data)


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
        )
        return Response(HousekeepingTaskSerializer(task).data)


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
        return Response(HousekeepingTaskSerializer(task).data)


# --- Maintenance ------------------------------------------------------------------


class MaintenanceListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [MtCreate()] if self.request.method == "POST" else [MtView()]

    def get_serializer_class(self):
        return MaintenanceRequestListSerializer

    def get_queryset(self):
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
        if ordering in (
            "reported_at", "-reported_at", "request_number", "-request_number",
            "priority", "-priority",
        ):
            qs = qs.order_by(ordering)
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = MaintenanceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
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
            MaintenanceRequestSerializer(obj).data, status=http_status.HTTP_201_CREATED
        )


class MaintenanceDetailView(APIView):
    def get_permissions(self):
        return [MtUpdate()] if self.request.method == "PATCH" else [MtView()]

    def get(self, request: Request, pk: int) -> Response:
        obj = _get(MaintenanceRequest, request, pk)
        return Response(MaintenanceRequestSerializer(obj).data)

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        obj = _get(MaintenanceRequest, request, pk)
        serializer = MaintenanceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = services.update_maintenance_request(
            obj, user=request.user, **serializer.validated_data
        )
        return Response(MaintenanceRequestSerializer(obj).data)


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
        return Response(MaintenanceRequestSerializer(obj).data)


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
        return Response(MaintenanceRequestSerializer(obj).data)


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
        return Response(MaintenanceRequestSerializer(obj).data)


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
        return Response(MaintenanceRequestSerializer(obj).data)


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
        return Response(MaintenanceRequestSerializer(obj).data)


# --- Lost & Found -----------------------------------------------------------------


class LostFoundListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [LfCreate()] if self.request.method == "POST" else [LfView()]

    def get_serializer_class(self):
        return LostFoundItemListSerializer

    def get_queryset(self):
        qs = LostFoundItem.objects.filter(hotel=self.request.hotel).select_related(
            "room", "guest"
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
            LostFoundItemSerializer(item).data, status=http_status.HTTP_201_CREATED
        )


class LostFoundDetailView(APIView):
    def get_permissions(self):
        return [LfUpdate()] if self.request.method == "PATCH" else [LfView()]

    def get(self, request: Request, pk: int) -> Response:
        item = _get(LostFoundItem, request, pk)
        return Response(LostFoundItemSerializer(item).data)

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
        return Response(LostFoundItemSerializer(item).data)


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
        return Response(LostFoundItemSerializer(item).data)


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
        return Response(LostFoundItemSerializer(item).data)


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
        return Response(LostFoundItemSerializer(item).data)


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
        return Response(LostFoundItemSerializer(item).data)


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
        return Response(LostFoundItemSerializer(item).data)


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
