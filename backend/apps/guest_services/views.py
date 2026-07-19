"""Guest extra-services API (mounted under /api/v1/hotel/guest-services/).

Two endpoints only (the catalog is managed via the admin — deactivate, never
delete):

- ``POST stays/{stay_id}/add/`` — post a catalog service to the stay's folio.
  Permission REUSE: ``service_orders.create``; a variable-price override
  additionally requires ``finance.charge_create`` (enforced in the service).
- ``GET folio-directory/`` — a compact, paginated, no-N+1 directory of in-house
  stays with the service line count/total and (finance.view only) money.

No new permission namespace; ``source`` is server-set; no direct payment.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError
from rest_framework import generics, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import PermissionDenied
from apps.common.pagination import DefaultPagination
from apps.rbac.permissions import HasHotelMembership, HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.stays.models import Stay
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import GuestExtraService
from .serializers import AddGuestServiceSerializer, GuestExtraServiceSerializer
from .services import (
    add_guest_service_to_stay,
    build_request_fingerprint,
    guest_folio_directory_queryset,
)

ZERO = Decimal("0.00")

# Adding a service is an operational service action -> reuse service_orders.create.
CanAddGuestService = HasHotelPermission("service_orders.create")

# Catalog management reuses the existing services.* codes (NO new namespace).
CanViewCatalog = HasHotelPermission("services.view")
CanCreateCatalog = HasHotelPermission("services.create")
CanUpdateCatalog = HasHotelPermission("services.update")
# Deactivate/activate reuse services.delete (the catalog is deactivated, never
# deleted — there is no DELETE http method anywhere in this app).
CanDeactivateCatalog = HasHotelPermission("services.delete")


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


_DUPLICATE_NAME_ERROR = {"name": "A service with this name already exists."}


class CanViewGuestFolioDirectory(HasHotelMembership):
    """ANY of ``service_orders.create`` / ``services.view`` / ``finance.view``
    unlocks the directory (money fields inside are separately gated on
    ``finance.view``). A plain permission-class ``|`` would break here because
    ``BaseHotelPermission`` raises rather than returns False on a missing code
    (mirrors ``operations.views.CanViewOperationsOverview``)."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        for code in ("service_orders.create", "services.view", "finance.view"):
            if has_hotel_permission(request.user, request.hotel, code):
                return True
        raise PermissionDenied()


def _guard_write(request: Request) -> None:
    # ONE central rule: a suspended hotel / a hotel without an active
    # subscription is refused for operational writes (reads never blocked).
    ensure_hotel_operational(request.hotel)


def _serialize_charge(charge) -> dict:
    return {
        "id": charge.id,
        "charge_number": charge.charge_number,
        "type": charge.type,
        "description": charge.description,
        "quantity": str(charge.quantity),
        "unit_amount": str(charge.unit_amount),
        "amount": str(charge.amount),
        "tax_rate": str(charge.tax_rate),
        "tax_amount": str(charge.tax_amount),
        "total_amount": str(charge.total_amount),
        "currency_snapshot": charge.currency_snapshot,
        "service_name_snapshot": charge.service_name_snapshot,
        "source": charge.source,
        "status": charge.status,
    }


def _serialize_posting(posting) -> dict:
    return {
        "id": posting.id,
        "stay": posting.stay_id,
        "service": posting.guest_extra_service_id,
        "idempotency_key": posting.idempotency_key,
        "created_at": posting.created_at.isoformat(),
        "charge": _serialize_charge(posting.folio_charge),
    }


class AddGuestServiceView(APIView):
    """POST guest-services/stays/{stay_id}/add/ — post a catalog service to the
    stay's folio (one SERVICE charge + a GuestServicePosting), atomically and
    idempotently."""

    def get_permissions(self):
        return [CanAddGuestService()]

    def post(self, request: Request, stay_id: int) -> Response:
        _guard_write(request)
        serializer = AddGuestServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Tenant-scoped fetch -> a cross-hotel stay/service is a 404 (never leaks).
        stay = generics.get_object_or_404(Stay, pk=stay_id, hotel=request.hotel)
        service = generics.get_object_or_404(
            GuestExtraService, pk=data["service"], hotel=request.hotel
        )

        override = data.get("unit_price_override")
        reason = data.get("reason", "")
        fingerprint = build_request_fingerprint(
            service,
            stay_id=stay.id,
            quantity=data["quantity"],
            unit_price_override=override,
            reason=reason,
        )
        posting = add_guest_service_to_stay(
            request.hotel,
            stay=stay,
            service=service,
            quantity=data["quantity"],
            user=request.user,
            idempotency_key=data.get("idempotency_key", ""),
            request_fingerprint=fingerprint,
            unit_price_override=override,
            reason=reason,
        )
        return Response(
            _serialize_posting(posting), status=status.HTTP_201_CREATED
        )


def _directory_row(stay, *, can_see_finance: bool) -> dict:
    from apps.finance.services import money

    row = {
        "stay_id": stay.id,
        "guest_name": stay.primary_guest.full_name,
        "room_number": stay.room.number,
        "room_type_name": stay.room.room_type.name,
        "floor_name": stay.room.floor.name,
        "floor_number": stay.room.floor.number or None,
        "check_in_date": str(stay.planned_check_in_date),
        "check_out_date": str(stay.planned_check_out_date),
        "folio_status": stay.open_folio_status,
        # Operational count MAY show to a non-finance user (no amount leaked).
        "service_count": int(stay.service_count or 0),
    }
    if can_see_finance:
        # ITEM-4 pattern: money keys are OMITTED entirely for a non-finance
        # viewer (never zeroed/nulled) — server-side gating, no client trust.
        balance = (stay.charges_total or ZERO) - (stay.payments_total or ZERO)
        row.update(
            {
                "service_total": str(money(stay.service_total or ZERO)),
                "balance": str(money(balance)),
                "total_payments": str(money(stay.payments_total or ZERO)),
                "currency": stay.open_folio_currency,
            }
        )
    return row


class GuestFolioDirectoryView(APIView):
    """GET guest-services/folio-directory/ — a compact, paginated, no-N+1
    directory of in-house stays (built on the /stays/current/ pattern)."""

    def get_permissions(self):
        return [CanViewGuestFolioDirectory()]

    def get(self, request: Request) -> Response:
        qs = guest_folio_directory_queryset(request.hotel)
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        can_see_finance = has_hotel_permission(
            request.user, request.hotel, "finance.view"
        )
        rows = [
            _directory_row(stay, can_see_finance=can_see_finance) for stay in page
        ]
        return paginator.get_paginated_response(rows)


# --- Catalog management (P9 "Services & Prices") ----------------------------


class CatalogListCreateView(generics.ListCreateAPIView):
    """GET (``services.view``) list the hotel's catalog; POST (``services.create``)
    add an entry. Supports ``?is_active=true|false`` filtering; ordered by
    ``display_order`` then name. NO delete method here."""

    serializer_class = GuestExtraServiceSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [CanCreateCatalog()]
        return [CanViewCatalog()]

    def get_queryset(self):
        qs = GuestExtraService.objects.filter(hotel=self.request.hotel)
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        return qs.order_by("display_order", "name", "id")

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        try:
            serializer.save(
                hotel=self.request.hotel, created_by=_actor(self.request.user)
            )
        except IntegrityError:
            # DB backstop for a concurrent duplicate normalized name.
            raise serializers.ValidationError(_DUPLICATE_NAME_ERROR)


class CatalogDetailView(generics.RetrieveUpdateAPIView):
    """GET (``services.view``) one entry; PATCH (``services.update``) edit it.
    No PUT, no DELETE (both -> 405). ``is_active`` is not editable here (use the
    deactivate/activate endpoints, gated on ``services.delete``)."""

    serializer_class = GuestExtraServiceSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [CanUpdateCatalog()] if self.request.method == "PATCH" else [CanViewCatalog()]

    def get_queryset(self):
        return GuestExtraService.objects.filter(hotel=self.request.hotel)

    def update(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise serializers.ValidationError(_DUPLICATE_NAME_ERROR)


class _CatalogActiveFlagView(APIView):
    """Shared base for deactivate/activate (both gated on ``services.delete``)."""

    target_active: bool

    def get_permissions(self):
        return [CanDeactivateCatalog()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        service = generics.get_object_or_404(
            GuestExtraService, pk=pk, hotel=request.hotel
        )
        if service.is_active != self.target_active:
            service.is_active = self.target_active
            service.save(update_fields=["is_active", "updated_at"])
        return Response(
            GuestExtraServiceSerializer(service, context={"request": request}).data
        )


class CatalogDeactivateView(_CatalogActiveFlagView):
    """POST catalog/{id}/deactivate/ — set is_active=False (never delete)."""

    target_active = False


class CatalogActivateView(_CatalogActiveFlagView):
    """POST catalog/{id}/activate/ — the reactivate counterpart."""

    target_active = True
