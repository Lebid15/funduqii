"""Guests API views (Phase 7 + final closure), mounted under /api/v1/hotel/.

Scoped to the caller's hotel and guarded by ``guests.*`` permissions. A
suspended hotel is read-only.

Final closure additions:
- ``guests/directory/`` — the guests-SECTION list: only guests with at least
  one REAL stay (in-house or checked-out), with derived stats. The plain
  ``guests/`` list keeps serving reservation/check-in pickers unchanged.
- ``guests/<pk>/profile/`` — the central read-only profile: identity, flags,
  derived stats and the full stay history with view-only links.
- VIP / block / unblock endpoints behind their own permissions.
- Deleting is HARDENED: any operational trace (stay, folio, lost & found)
  deactivates instead of deleting, and the response says which one happened.
"""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import Guest
from .serializers import (
    GuestBlockSerializer,
    GuestSerializer,
    GuestUnblockSerializer,
    GuestVipSerializer,
    can_view_sensitive,
)
from .services import (
    REAL_STAY_STATUSES,
    block_guest,
    deactivate_or_delete,
    mask_document,
    record_guest_created,
    record_guest_updated,
    set_vip,
    unblock_guest,
)

CanView = HasHotelPermission("guests.view")
CanCreate = HasHotelPermission("guests.create")
CanUpdate = HasHotelPermission("guests.update")
CanDelete = HasHotelPermission("guests.delete")
CanMarkVip = HasHotelPermission("guests.mark_vip")
CanBlock = HasHotelPermission("guests.block")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _real_stays(guest):
    """The guest's REAL stays (any role, cancelled excluded), prefetched."""
    return [
        link.stay
        for link in guest.stay_links.all()
        if link.stay.status in REAL_STAY_STATUSES
    ]


def _stats(stays: list) -> dict:
    """Derived stats — never stored: counts, nights, first/last, residency."""
    count = len(stays)
    nights = sum(s.nights for s in stays)
    in_house = [s for s in stays if s.status == "in_house"]
    ordered = sorted(stays, key=lambda s: (s.planned_check_in_date, s.id))
    current = in_house[0] if in_house else None
    return {
        "stays_count": count,
        "nights_total": nights,
        "first_stay_date": str(ordered[0].planned_check_in_date) if ordered else None,
        "last_stay_date": str(ordered[-1].planned_check_in_date) if ordered else None,
        "is_repeat": count > 1,
        "is_resident": current is not None,
        "current_room_number": current.room.number if current else None,
    }


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
    """The PLAIN guest list — reservation/check-in pickers depend on it, so
    its behavior is unchanged (all active guests, no stay requirement)."""

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
        guest = serializer.save(
            hotel=self.request.hotel,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        record_guest_created(guest, user=self.request.user)


class GuestDirectoryView(generics.ListAPIView):
    """The guests-SECTION list: only guests who actually stayed (>= 1 real
    stay), each row carrying derived stats. Stats come from ONE prefetch —
    no per-row queries."""

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        from django.db.models import Count, Q

        qs = (
            Guest.objects.filter(hotel=self.request.hotel)
            .annotate(
                real_stay_count=Count(
                    "stay_links",
                    filter=Q(stay_links__stay__status__in=REAL_STAY_STATUSES),
                )
            )
            .filter(real_stay_count__gte=1)
            .prefetch_related("stay_links__stay__room")
        )
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
            ).distinct()
        return qs

    def list(self, request: Request, *args, **kwargs) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        sensitive = can_view_sensitive(request)
        rows = []
        for guest in page:
            stats = _stats(_real_stays(guest))
            rows.append(
                {
                    "id": guest.id,
                    "full_name": guest.full_name,
                    "phone": guest.phone,
                    "nationality": guest.nationality,
                    "document_type": guest.document_type,
                    "document_number": (
                        guest.document_number
                        if sensitive
                        else mask_document(guest.document_number)
                    ),
                    "is_active": guest.is_active,
                    "is_vip": guest.is_vip,
                    "is_blocked": guest.is_blocked,
                    **stats,
                }
            )
        return self.get_paginated_response(rows)


class GuestDetailView(_GuestScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestSerializer

    def get_queryset(self):
        return Guest.objects.filter(hotel=self.request.hotel)

    def perform_update(self, serializer):
        _guard_write(self.request)
        old = {
            "full_name": serializer.instance.full_name,
            "phone": serializer.instance.phone,
            "document_type": serializer.instance.document_type,
            "document_number": serializer.instance.document_number,
        }
        guest = serializer.save(updated_by=self.request.user)
        record_guest_updated(guest, old_values=old, user=self.request.user)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        guest = self.get_object()
        result = deactivate_or_delete(guest, user=request.user)
        if result == "deactivated":
            guest.refresh_from_db()
            return Response(
                {
                    "result": "deactivated",
                    "guest": GuestSerializer(
                        guest, context={"request": request}
                    ).data,
                }
            )
        return Response({"result": "deleted"})


class GuestProfileView(APIView):
    """The central, READ-ONLY guest profile: identity + flags + derived stats
    + the full stay history with view-only links. Nothing operational can be
    changed from here."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        guest = generics.get_object_or_404(
            Guest.objects.filter(hotel=request.hotel).prefetch_related(
                "stay_links__stay__room__room_type",
                "stay_links__stay__reservation",
                "stay_links__stay__folios",
            ),
            pk=pk,
        )
        sensitive = can_view_sensitive(request)
        can_see_block_reason = has_hotel_permission(
            request.user, request.hotel, "guests.block"
        )

        all_stays = sorted(
            (link.stay for link in guest.stay_links.all()),
            key=lambda s: (s.planned_check_in_date, s.id),
            reverse=True,
        )
        real = [s for s in all_stays if s.status in REAL_STAY_STATUSES]
        stats = _stats(real)
        current = next((s for s in real if s.status == "in_house"), None)

        def _folio_of(stay):
            folios = list(stay.folios.all())
            open_first = sorted(
                folios, key=lambda f: (f.status != "open", -f.id)
            )
            return open_first[0] if open_first else None

        history = []
        for stay in all_stays:
            folio = _folio_of(stay)
            history.append(
                {
                    "stay_id": stay.id,
                    "status": stay.status,
                    "is_current": stay.status == "in_house",
                    "reservation_id": stay.reservation_id,
                    "reservation_number": (
                        stay.reservation.reservation_number
                        if stay.reservation_id
                        else None
                    ),
                    "room_number": stay.room.number,
                    "room_type_name": stay.room.room_type.name,
                    "check_in_date": str(stay.planned_check_in_date),
                    "check_out_date": str(stay.planned_check_out_date),
                    "actual_check_out_at": (
                        stay.actual_check_out_at.isoformat()
                        if stay.actual_check_out_at
                        else None
                    ),
                    "nights": stay.nights,
                    "folio_id": folio.id if folio else None,
                    "folio_number": folio.folio_number if folio else None,
                    "folio_status": folio.status if folio else None,
                }
            )

        current_folio = _folio_of(current) if current else None
        payload = {
            "id": guest.id,
            "full_name": guest.full_name,
            "phone": guest.phone,
            "email": guest.email,
            "nationality": guest.nationality,
            "gender": guest.gender,
            "date_of_birth": str(guest.date_of_birth) if guest.date_of_birth else None,
            "document_type": guest.document_type,
            "document_number": (
                guest.document_number
                if sensitive
                else mask_document(guest.document_number)
            ),
            "address": guest.address,
            "notes": guest.notes,
            "is_active": guest.is_active,
            "is_vip": guest.is_vip,
            "vip_marked_at": (
                guest.vip_marked_at.isoformat() if guest.vip_marked_at else None
            ),
            "vip_marked_by": (
                guest.vip_marked_by.email if guest.vip_marked_by_id else None
            ),
            "is_blocked": guest.is_blocked,
            "blocked_at": guest.blocked_at.isoformat() if guest.blocked_at else None,
            "blocked_by": guest.blocked_by.email if guest.blocked_by_id else None,
            # The reason is sensitive: only block-permission holders see it.
            "block_reason": guest.block_reason if can_see_block_reason else None,
            **stats,
            "current": (
                {
                    "stay_id": current.id,
                    "room_number": current.room.number,
                    "reservation_id": current.reservation_id,
                    "reservation_number": (
                        current.reservation.reservation_number
                        if current.reservation_id
                        else None
                    ),
                    "folio_id": current_folio.id if current_folio else None,
                    "folio_number": (
                        current_folio.folio_number if current_folio else None
                    ),
                    "folio_status": current_folio.status if current_folio else None,
                }
                if current
                else None
            ),
            "stays": history,
            "created_at": guest.created_at.isoformat(),
            "updated_at": guest.updated_at.isoformat(),
            "created_by": guest.created_by.email if guest.created_by_id else None,
            "updated_by": guest.updated_by.email if guest.updated_by_id else None,
        }
        return Response(payload)


class GuestVipView(APIView):
    def get_permissions(self):
        return [CanMarkVip()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        guest = generics.get_object_or_404(Guest, pk=pk, hotel=request.hotel)
        serializer = GuestVipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest = set_vip(guest, vip=serializer.validated_data["vip"], user=request.user)
        return Response(GuestSerializer(guest, context={"request": request}).data)


class GuestBlockView(APIView):
    def get_permissions(self):
        return [CanBlock()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        guest = generics.get_object_or_404(Guest, pk=pk, hotel=request.hotel)
        serializer = GuestBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest = block_guest(
            guest, reason=serializer.validated_data["reason"], user=request.user
        )
        return Response(GuestSerializer(guest, context={"request": request}).data)


class GuestUnblockView(APIView):
    def get_permissions(self):
        return [CanBlock()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        guest = generics.get_object_or_404(Guest, pk=pk, hotel=request.hotel)
        serializer = GuestUnblockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest = unblock_guest(
            guest, note=serializer.validated_data.get("note", ""), user=request.user
        )
        return Response(GuestSerializer(guest, context={"request": request}).data)
