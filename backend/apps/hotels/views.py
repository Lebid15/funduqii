"""Hotel-side API views (Phase 4), mounted under /api/v1/hotel/.

Every endpoint runs in the caller's hotel context (resolved from the X-Hotel-ID
header) and is guarded by a hotel permission — the backend enforces
authentication, active membership, tenant isolation, and the specific
``settings.view`` / ``settings.update`` permission. A suspended hotel is
read-only. Settings (text) and media (files) are handled by separate endpoints.
"""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import HotelSuspended
from apps.rbac.permissions import HasHotelPermission
from apps.tenancy.models import HotelStatus

from . import services
from .models import HotelMedia, HotelSettings, MediaKind
from .serializers import (
    HotelMediaSerializer,
    HotelMediaUpdateSerializer,
    HotelMediaUploadSerializer,
    HotelSettingsSerializer,
)

CanView = HasHotelPermission("settings.view")
CanUpdate = HasHotelPermission("settings.update")


def _ensure_not_suspended(request: Request) -> None:
    if request.hotel.status == HotelStatus.SUSPENDED:
        raise HotelSuspended()


def _get_settings(hotel) -> HotelSettings:
    obj, _ = HotelSettings.objects.get_or_create(hotel=hotel)
    return obj


# --- Settings ---------------------------------------------------------------


class HotelSettingsView(APIView):
    """GET/PATCH the current hotel's text settings (auto-created on first read)."""

    def get_permissions(self):
        return [CanUpdate()] if self.request.method == "PATCH" else [CanView()]

    def get(self, request: Request) -> Response:
        settings_obj = _get_settings(request.hotel)
        return Response(HotelSettingsSerializer(settings_obj).data)

    def patch(self, request: Request) -> Response:
        _ensure_not_suspended(request)
        settings_obj = _get_settings(request.hotel)
        serializer = HotelSettingsSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class HotelProfileView(APIView):
    """Compact read-only view of the current hotel (tenant + settings + media)."""

    permission_classes = [CanView]

    def get(self, request: Request) -> Response:
        # Phase 16: the hotel console reads its own billing state here (safe,
        # read-only) to show the subscription banners.
        from apps.subscriptions.enforcement import subscription_state

        hotel = request.hotel
        settings_obj = _get_settings(hotel)
        media = HotelMedia.objects.filter(hotel=hotel, is_active=True)
        logo = media.filter(kind=MediaKind.LOGO).first()
        cover = media.filter(kind=MediaKind.COVER).first()
        ctx = {"request": request}
        return Response(
            {
                "hotel": {
                    "id": hotel.id,
                    "name": hotel.name,
                    "slug": hotel.slug,
                    "status": hotel.status,
                },
                "display_name": settings_obj.display_name,
                "city": settings_obj.city,
                "country": settings_obj.country,
                "logo": HotelMediaSerializer(logo, context=ctx).data if logo else None,
                "cover": (
                    HotelMediaSerializer(cover, context=ctx).data if cover else None
                ),
                "gallery_count": media.filter(kind=MediaKind.GALLERY).count(),
                "subscription_state": subscription_state(hotel),
            }
        )


# --- Media ------------------------------------------------------------------


class HotelMediaListCreateView(generics.ListAPIView):
    serializer_class = HotelMediaSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    # Media per hotel is a small, bounded set (logo + cover + a capped gallery),
    # so return a plain list rather than a paginated envelope.
    pagination_class = None

    def get_permissions(self):
        return [CanUpdate()] if self.request.method == "POST" else [CanView()]

    def get_queryset(self):
        qs = HotelMedia.objects.filter(hotel=self.request.hotel)
        kind = self.request.query_params.get("kind")
        if kind in {c for c, _ in MediaKind.choices}:
            qs = qs.filter(kind=kind)
        return qs

    def post(self, request: Request, *args, **kwargs) -> Response:
        _ensure_not_suspended(request)
        serializer = HotelMediaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        media = services.create_media(
            hotel=request.hotel,
            kind=serializer.validated_data["kind"],
            file=serializer.validated_data["file"],
            alt_text=serializer.validated_data.get("alt_text", ""),
            user=request.user,
        )
        return Response(
            HotelMediaSerializer(media, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class HotelMediaDetailView(APIView):
    """PATCH metadata (never the file) or DELETE a media asset."""

    def get_permissions(self):
        return [CanView()] if self.request.method == "GET" else [CanUpdate()]

    def _get_object(self, request: Request, pk: int) -> HotelMedia:
        # Tenant isolation: only media belonging to the current hotel.
        return generics.get_object_or_404(HotelMedia, pk=pk, hotel=request.hotel)

    def get(self, request: Request, pk: int) -> Response:
        media = self._get_object(request, pk)
        return Response(
            HotelMediaSerializer(media, context={"request": request}).data
        )

    def patch(self, request: Request, pk: int) -> Response:
        _ensure_not_suspended(request)
        media = self._get_object(request, pk)
        serializer = HotelMediaUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        new_active = data.get("is_active")
        if new_active is True and media.kind in (MediaKind.LOGO, MediaKind.COVER):
            services.activate_media(media)
        elif new_active is not None:
            media.is_active = new_active
        if "alt_text" in data:
            media.alt_text = data["alt_text"]
        if "sort_order" in data:
            media.sort_order = data["sort_order"]
        media.save()
        return Response(
            HotelMediaSerializer(media, context={"request": request}).data
        )

    def delete(self, request: Request, pk: int) -> Response:
        _ensure_not_suspended(request)
        media = self._get_object(request, pk)
        services.delete_media(media)
        return Response(status=status.HTTP_204_NO_CONTENT)
