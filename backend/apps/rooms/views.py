"""Rooms API views (Phase 5), mounted under /api/v1/hotel/.

Floors, room types and rooms — all scoped to the caller's hotel context and
guarded by ``rooms.*`` permissions. A suspended hotel is read-only. This is
inventory only: no reservations, availability, guests or money.
"""
from __future__ import annotations

from django.db.models import ProtectedError
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import (
    BulkRequestTooLarge,
    PermissionDenied,
    ResourceInUse,
)
from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .models import Floor, Room, RoomStatus, RoomType
from .serializers import (
    FloorSerializer,
    RoomBulkCreateSerializer,
    RoomSerializer,
    RoomStatusUpdateSerializer,
    RoomTypeSerializer,
    RoomWriteSerializer,
)

CanView = HasHotelPermission("rooms.view")
CanCreate = HasHotelPermission("rooms.create")
CanUpdate = HasHotelPermission("rooms.update")
CanDelete = HasHotelPermission("rooms.delete")
CanStatus = HasHotelPermission("rooms.status_update")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _require_status_update_for(request: Request, initial_statuses) -> None:
    """H1: creating a room in a NON-available initial status is a status change,
    so it also requires ``rooms.status_update`` (in addition to ``rooms.create``)
    — checked BEFORE any write, for both single and bulk create. ``rooms.create``
    alone covers a plain available room. ``initial_statuses`` is the iterable of
    requested initial statuses."""
    needs_status = any(
        st and st != RoomStatus.AVAILABLE for st in initial_statuses
    )
    if needs_status and not has_hotel_permission(
        request.user, request.hotel, "rooms.status_update"
    ):
        raise PermissionDenied()


def _safe_delete(instance, reason: str) -> None:
    """Delete ``instance``, converting any residual PROTECT violation into a
    409 ``ResourceInUse`` instead of an unhandled 500. The explicit
    ``ensure_deletable_*`` guards already cover the enumerated relations; this
    is the safety net for any unenumerated PROTECT foreign key."""
    try:
        instance.delete()
    except ProtectedError as exc:
        raise ResourceInUse({"reason": reason}) from exc


class _HotelScopedMixin:
    """Per-method permissions + hotel-scoped queryset + write serializer ctx."""

    list_permission = CanView
    create_permission = CanCreate
    update_permission = CanUpdate
    delete_permission = CanDelete

    def get_permissions(self):
        method = self.request.method
        if method in ("POST",):
            return [self.create_permission()]
        if method in ("PUT", "PATCH"):
            return [self.update_permission()]
        if method == "DELETE":
            return [self.delete_permission()]
        return [self.list_permission()]


# --- Floors -----------------------------------------------------------------


class FloorListCreateView(_HotelScopedMixin, generics.ListCreateAPIView):
    serializer_class = FloorSerializer

    def get_queryset(self):
        qs = Floor.objects.filter(hotel=self.request.hotel)
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        return qs

    def perform_create(self, serializer):
        _guard_write(self.request)
        serializer.save(hotel=self.request.hotel)


class FloorDetailView(_HotelScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FloorSerializer

    def get_queryset(self):
        return Floor.objects.filter(hotel=self.request.hotel)

    def perform_update(self, serializer):
        _guard_write(self.request)
        serializer.save()

    def perform_destroy(self, instance):
        _guard_write(self.request)
        services.ensure_deletable_floor(instance)
        _safe_delete(instance, "floor_protected")


# --- Room types -------------------------------------------------------------


class RoomTypeListCreateView(_HotelScopedMixin, generics.ListCreateAPIView):
    serializer_class = RoomTypeSerializer

    def get_queryset(self):
        qs = RoomType.objects.filter(hotel=self.request.hotel)
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        return qs

    def perform_create(self, serializer):
        _guard_write(self.request)
        serializer.save(hotel=self.request.hotel)


class RoomTypeDetailView(_HotelScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomTypeSerializer

    def get_queryset(self):
        return RoomType.objects.filter(hotel=self.request.hotel)

    def perform_update(self, serializer):
        _guard_write(self.request)
        serializer.save()

    def perform_destroy(self, instance):
        _guard_write(self.request)
        services.ensure_deletable_room_type(instance)
        _safe_delete(instance, "room_type_protected")


# --- Rooms ------------------------------------------------------------------


class RoomListCreateView(_HotelScopedMixin, generics.ListCreateAPIView):
    def get_serializer_class(self):
        return RoomWriteSerializer if self.request.method == "POST" else RoomSerializer

    def get_queryset(self):
        qs = Room.objects.filter(hotel=self.request.hotel).select_related(
            "floor", "room_type"
        )
        params = self.request.query_params

        status_filter = params.get("status")
        valid_status = {c for c, _ in RoomStatus.choices}
        if status_filter in valid_status:
            qs = qs.filter(status=status_filter)
        elif params.get("include_archived") != "true":
            # Archived rooms are hidden unless explicitly requested.
            qs = qs.exclude(status=RoomStatus.ARCHIVED)

        floor = params.get("floor")
        if floor and str(floor).isdigit():
            qs = qs.filter(floor_id=int(floor))
        room_type = params.get("room_type")
        if room_type and str(room_type).isdigit():
            qs = qs.filter(room_type_id=int(room_type))
        is_active = params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))

        search = params.get("search")
        if search:
            qs = qs.filter(number__icontains=search) | qs.filter(
                display_name__icontains=search
            )
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = RoomWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        initial_status = data.get("initial_status", RoomStatus.AVAILABLE)
        # H1: a non-available initial status also requires rooms.status_update.
        _require_status_update_for(request, [initial_status])
        # H2: single create shares the central path with bulk — quota check,
        # room creation and the initial-status move (RoomStatusLog) all inside
        # ONE atomic transaction. A single create is not batch noise, so its
        # status move notifies normally (notify=True).
        room = services.create_room(
            request.hotel,
            number=data["number"],
            display_name=data.get("display_name", ""),
            floor=data["floor"],
            room_type=data["room_type"],
            is_active=data.get("is_active", True),
            initial_status=initial_status,
            status_note=data.get("status_note", ""),
            user=request.user,
            notify=True,
        )
        return Response(
            RoomSerializer(room).data, status=status.HTTP_201_CREATED
        )


class RoomBulkCreateView(APIView):
    """Create many rooms in one all-or-nothing request (thin view — the batch
    validation, quota check and transaction live in ``services``). Same
    ``rooms.create`` permission and operational gate as the single create; a
    non-available initial status on any row also requires ``rooms.status_update``
    (H1), enforced before any write."""

    def get_permissions(self):
        return [CanCreate()]

    def post(self, request: Request) -> Response:
        _guard_write(request)
        # L1 hardening: reject an oversized batch BEFORE DRF child-validates
        # every element. The list is already parsed, so this is a cheap length
        # check; without it a huge payload (up to the body limit) would be fully
        # per-row validated before rejection. The serializer's validate_rooms
        # and the service keep the same cap as defense-in-depth.
        #
        # A malformed TOP-LEVEL array body (e.g. `[{...}]`) makes request.data a
        # list, not a dict — guard with isinstance so `.get` is never called on
        # it (that would raise AttributeError -> unhandled 500). A non-dict body
        # falls through to the serializer, which returns a clean 400 for the
        # wrong shape.
        raw_rooms = (
            request.data.get("rooms") if isinstance(request.data, dict) else None
        )
        if isinstance(raw_rooms, list) and len(raw_rooms) > services.MAX_BULK_ROOMS:
            raise BulkRequestTooLarge(
                {"limit": services.MAX_BULK_ROOMS, "requested": len(raw_rooms)}
            )
        serializer = RoomBulkCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data["rooms"]
        # H1: any row with a non-available initial status also requires
        # rooms.status_update — enforced BEFORE any write (all-or-nothing).
        _require_status_update_for(
            request,
            [r.get("initial_status", RoomStatus.AVAILABLE) for r in rows],
        )
        rooms = services.bulk_create_rooms(request.hotel, rows, request.user)
        return Response(
            {
                "created_count": len(rooms),
                "rooms": RoomSerializer(rooms, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class RoomDetailView(_HotelScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    def get_serializer_class(self):
        return (
            RoomWriteSerializer
            if self.request.method in ("PUT", "PATCH")
            else RoomSerializer
        )

    def get_queryset(self):
        return Room.objects.filter(hotel=self.request.hotel).select_related(
            "floor", "room_type"
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        partial = kwargs.pop("partial", False)
        room = self.get_object()
        serializer = RoomWriteSerializer(
            room, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        room.refresh_from_db()
        return Response(RoomSerializer(room).data)

    def perform_destroy(self, instance):
        _guard_write(self.request)
        services.ensure_deletable_room(instance)
        _safe_delete(instance, "room_protected")


class RoomOperationalBoardView(APIView):
    """READ-ONLY operational board (owner task): every room with its computed
    display status (occupied/reserved derived from stays and reservations —
    never stored), current in-house stay, next upcoming reservation, plus
    hotel-wide and per-floor summaries. One request feeds the whole board —
    no pagination (a hotel's room inventory is small), no writes."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        return Response(services.operational_board(request.hotel))


class RoomStatusView(APIView):
    """Controlled room-status change endpoint (logs to RoomStatusLog)."""

    def get_permissions(self):
        return [CanStatus()]

    def _get_room(self, request: Request, pk: int) -> Room:
        return generics.get_object_or_404(Room, pk=pk, hotel=request.hotel)

    def post(self, request: Request, pk: int) -> Response:
        return self._change(request, pk)

    def patch(self, request: Request, pk: int) -> Response:
        return self._change(request, pk)

    def _change(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        room = self._get_room(request, pk)
        serializer = RoomStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_room_status(
            room,
            serializer.validated_data["status"],
            note=serializer.validated_data.get("note", ""),
            user=request.user,
        )
        room.refresh_from_db()
        return Response(RoomSerializer(room).data)
