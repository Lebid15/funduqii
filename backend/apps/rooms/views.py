"""Rooms API views (Phase 5), mounted under /api/v1/hotel/.

Floors, room types and rooms — all scoped to the caller's hotel context and
guarded by ``rooms.*`` permissions. A suspended hotel is read-only. This is
inventory only: no reservations, availability, guests or money.
"""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import HotelSuspended
from apps.rbac.permissions import HasHotelPermission
from apps.tenancy.models import HotelStatus

from . import services
from .models import Floor, Room, RoomStatus, RoomType
from .serializers import (
    FloorSerializer,
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
    if request.hotel.status == HotelStatus.SUSPENDED:
        raise HotelSuspended()


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
        instance.delete()


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
        instance.delete()


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
        room = serializer.save(hotel=request.hotel)
        return Response(
            RoomSerializer(room).data, status=status.HTTP_201_CREATED
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
        instance.delete()


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
