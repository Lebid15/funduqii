"""Rooms API URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .views import (
    FloorDetailView,
    FloorListCreateView,
    RoomDetailView,
    RoomListCreateView,
    RoomOperationalBoardView,
    RoomStatusView,
    RoomTypeDetailView,
    RoomTypeListCreateView,
)

app_name = "rooms"

urlpatterns = [
    path("floors/", FloorListCreateView.as_view(), name="floor-list"),
    path("floors/<int:pk>/", FloorDetailView.as_view(), name="floor-detail"),
    path("room-types/", RoomTypeListCreateView.as_view(), name="room-type-list"),
    path(
        "room-types/<int:pk>/",
        RoomTypeDetailView.as_view(),
        name="room-type-detail",
    ),
    path(
        "rooms/operational-board/",
        RoomOperationalBoardView.as_view(),
        name="room-operational-board",
    ),
    path("rooms/", RoomListCreateView.as_view(), name="room-list"),
    path("rooms/<int:pk>/", RoomDetailView.as_view(), name="room-detail"),
    path("rooms/<int:pk>/status/", RoomStatusView.as_view(), name="room-status"),
]
