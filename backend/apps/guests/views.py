"""Guests API views (Phase 7), mounted under /api/v1/hotel/.

Scoped to the caller's hotel and guarded by ``guests.*`` permissions. A
suspended hotel is read-only. Deleting a guest that is referenced by a stay
deactivates it (soft) instead of hard-deleting, to preserve stay history.
"""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.rbac.permissions import HasHotelPermission
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import Guest
from .serializers import GuestSerializer

CanView = HasHotelPermission("guests.view")
CanCreate = HasHotelPermission("guests.create")
CanUpdate = HasHotelPermission("guests.update")
CanDelete = HasHotelPermission("guests.delete")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


class _GuestScopedMixin:
    def get_permissions(self):
        method = self.request.method
        if method == "POST":
            return [CanCreate()]
        if method in ("PUT", "PATCH"):
            return [CanUpdate()]
        if method == "DELETE":
            return [CanDelete()]
        return [CanView()]


class GuestListCreateView(_GuestScopedMixin, generics.ListCreateAPIView):
    serializer_class = GuestSerializer

    def get_queryset(self):
        qs = Guest.objects.filter(hotel=self.request.hotel)
        params = self.request.query_params
        is_active = params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        search = params.get("search")
        if search:
            qs = (
                qs.filter(full_name__icontains=search)
                | qs.filter(phone__icontains=search)
                | qs.filter(document_number__icontains=search)
                | qs.filter(email__icontains=search)
            )
        return qs.distinct()

    def perform_create(self, serializer):
        _guard_write(self.request)
        serializer.save(
            hotel=self.request.hotel,
            created_by=self.request.user,
            updated_by=self.request.user,
        )


class GuestDetailView(_GuestScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestSerializer

    def get_queryset(self):
        return Guest.objects.filter(hotel=self.request.hotel)

    def perform_update(self, serializer):
        _guard_write(self.request)
        serializer.save(updated_by=self.request.user)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        guest = self.get_object()
        # Preserve stay history: a referenced guest is deactivated, not deleted.
        if guest.stay_links.exists():
            guest.is_active = False
            guest.updated_by = request.user
            guest.save(update_fields=["is_active", "updated_by", "updated_at"])
            return Response(GuestSerializer(guest).data)
        guest.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
