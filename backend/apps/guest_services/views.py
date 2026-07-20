"""Guest extra-services API (mounted under /api/v1/hotel/guest-services/).

Seven routes (see ``urls.py``); the catalog is DEACTIVATED, never deleted, so
there is no DELETE http method anywhere in this app:

Operational
- ``POST stays/{stay_id}/add/`` — post a catalog service to the stay's folio.
  Permission REUSE: ``service_orders.create``; a variable-price override
  additionally requires ``finance.charge_create`` (enforced in the service).
- ``GET stays/{stay_id}/service-lines/`` — the stay's OPEN-folio SERVICE lines
  (money-SAFE: no balance/payments). Any of the three read codes below.
- ``GET folio-directory/`` — a compact, paginated, no-N+1 directory of in-house
  stays with the service line count/total and (finance.view only) money.

Catalog ("Services & Prices")
- ``GET catalog/`` — UNPAGINATED plain array (contract; see
  :class:`CatalogListCreateView`). Readable with ANY of ``services.view`` /
  ``service_orders.create`` / ``finance.view``.
- ``POST catalog/`` — ``services.create``.
- ``GET|PATCH catalog/{id}/`` — read as above; PATCH is ``services.update``.
- ``POST catalog/{id}/deactivate/`` and ``POST catalog/{id}/activate/`` —
  ``services.delete`` (deactivate, never delete).

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
from apps.finance.models import PostingStatus
from apps.rbac.permissions import HasHotelMembership, HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.stays.models import Stay
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import GuestExtraService, GuestServicePosting
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
CanCreateCatalog = HasHotelPermission("services.create")
CanUpdateCatalog = HasHotelPermission("services.update")
# Deactivate/activate reuse services.delete (the catalog is deactivated, never
# deleted — there is no DELETE http method anywhere in this app).
CanDeactivateCatalog = HasHotelPermission("services.delete")


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


_DUPLICATE_NAME_ERROR = {"name": "A service with this name already exists."}


#: The ONE operational read set for this surface. A user who may ADD a service
#: (``service_orders.create``) must also be able to READ the catalog picker and
#: the directory, otherwise the primary persona is 403'd out of its own flow.
GUEST_SERVICE_READ_CODES = ("service_orders.create", "services.view", "finance.view")


class AnyOfGuestServiceRead(HasHotelMembership):
    """ANY of :data:`GUEST_SERVICE_READ_CODES` unlocks the read (money fields
    inside are separately gated on ``finance.view``). A plain permission-class
    ``|`` would break here because ``BaseHotelPermission`` raises rather than
    returns False on a missing code (mirrors
    ``operations.views.CanViewOperationsOverview``)."""

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        for code in GUEST_SERVICE_READ_CODES:
            if has_hotel_permission(request.user, request.hotel, code):
                return True
        raise PermissionDenied()


#: Directory / service-lines reads (unchanged behaviour, renamed base).
CanViewGuestFolioDirectory = AnyOfGuestServiceRead
#: Catalog READS use the SAME any-of set: the AddServiceModal picker is driven by
#: ``GET catalog/``, so gating it on ``services.view`` alone made the catalog
#: unreadable for a ``service_orders.create`` holder and blocked adding a service
#: entirely. Catalog WRITES are unchanged (services.create/update/delete).
CanReadCatalog = AnyOfGuestServiceRead


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
    directory of in-house stays (built on the /stays/current/ pattern).

    ``?search=`` (B1) filters SERVER-SIDE on guest name OR room number, applied
    BEFORE pagination — same param name and semantics as ``GET /rooms/options/``.
    A client-side filter over the current page could only ever search 25 rows and
    would report "no results" for a resident sitting on page 2."""

    def get_permissions(self):
        return [CanViewGuestFolioDirectory()]

    def get(self, request: Request) -> Response:
        can_see_finance = has_hotel_permission(
            request.user, request.hotel, "finance.view"
        )
        # C7 — do not compute money the caller may not see: without ``finance.view``
        # the money subqueries are not even added to the SQL (they were previously
        # computed and then stripped from the payload — no leak, but wasted work).
        qs = guest_folio_directory_queryset(
            request.hotel,
            include_money=can_see_finance,
            # B1 — ``?search=`` is applied in the DB, BEFORE pagination.
            search=request.query_params.get("search") or "",
        )
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        rows = [
            _directory_row(stay, can_see_finance=can_see_finance) for stay in page
        ]
        return paginator.get_paginated_response(rows)


# --- Per-stay service line items (operational, money-SAFE) -------------------


def _user_name(user):
    return getattr(user, "full_name", None) if user is not None else None


def _service_line_row(charge, *, folio_currency, override_reason=None) -> dict:
    """One folio SERVICE line item for the operational surface. Carries the line's
    OWN amounts (the point is to SHOW the service items) but NEVER the folio
    balance / payments / deposits / insurance. ``id`` is the ``FolioCharge`` id so
    the frontend can reuse the EXISTING finance void-charge endpoint on it."""
    voided = charge.status == PostingStatus.VOIDED
    return {
        "id": charge.id,
        "source": charge.source,
        "description": charge.description,
        "service_name_snapshot": charge.service_name_snapshot or charge.description,
        "quantity": str(charge.quantity),
        "unit_amount": str(charge.unit_amount),
        "tax_rate": str(charge.tax_rate),
        "tax_amount": str(charge.tax_amount),
        "total_amount": str(charge.total_amount),
        "currency": folio_currency,
        "created_by": _user_name(charge.created_by),
        "created_at": charge.created_at.isoformat(),
        "status": charge.status,
        # Populated only for a voided line (stable shape: null otherwise).
        "void_reason": (charge.void_reason or None) if voided else None,
        "voided_by": _user_name(charge.voided_by) if voided else None,
        # B3 — the mandatory justification captured when a VARIABLE service was
        # posted at an overridden price (null for every ordinary line). Makes the
        # override auditable on the operational surface, like adjust_charge's reason.
        "price_override_reason": override_reason or None,
    }


class StayServiceLinesView(APIView):
    """GET guest-services/stays/{stay_id}/service-lines/ — the stay's OPEN folio
    SERVICE line items (guest extra services + posted service orders), INCLUDING
    voided ones (void history is operational). Money-SAFE: it returns ONLY the
    service lines — never the balance, payments, deposits, insurance, room nights,
    adjustments/discounts, or any non-service source — so a ``service_orders.create``
    holder WITHOUT ``finance.view`` can still view the items. Empty folio -> []."""

    def get_permissions(self):
        # Same any-of set as the directory (operational users included).
        return [CanViewGuestFolioDirectory()]

    def get(self, request: Request, stay_id: int) -> Response:
        from apps.finance.constants import SERVICE_LINE_SOURCES
        from apps.finance.models import Folio, FolioCharge, FolioStatus

        stay = generics.get_object_or_404(Stay, pk=stay_id, hotel=request.hotel)
        folio = (
            Folio.objects.filter(
                hotel=request.hotel, stay=stay, status=FolioStatus.OPEN
            )
            .order_by("id")
            .first()
        )
        if folio is None:
            return Response([])
        source_values = sorted(str(s) for s in SERVICE_LINE_SOURCES)
        charges = list(
            FolioCharge.objects.filter(folio=folio, source__in=source_values)
            .select_related("created_by", "voided_by")
            .order_by("created_at", "id")
        )
        # B3 — one CONSTANT extra query for the override reasons (never per line).
        # Read guest_services -> finance ONLY: ``FolioCharge`` deliberately exposes
        # no reverse accessor back here (``related_name="+"``), so the lookup goes
        # forward from the posting side and the layering rule is preserved.
        override_reasons = dict(
            GuestServicePosting.objects.filter(
                hotel=request.hotel, folio_charge_id__in=[c.id for c in charges]
            )
            .exclude(price_override_reason="")
            .values_list("folio_charge_id", "price_override_reason")
        )
        return Response(
            [
                _service_line_row(
                    c,
                    folio_currency=folio.currency,
                    override_reason=override_reasons.get(c.id),
                )
                for c in charges
            ]
        )


# --- Catalog management (P9 "Services & Prices") ----------------------------


class CatalogListCreateView(generics.ListCreateAPIView):
    """GET (any of :data:`GUEST_SERVICE_READ_CODES`) list the hotel's catalog;
    POST (``services.create``) add an entry. Supports ``?is_active=true|false``
    filtering; ordered by ``display_order`` then name. NO delete method here.

    CONTRACT — the list response is a PLAIN ARRAY, never a
    ``{count,next,previous,results}`` envelope (``pagination_class = None``). The
    catalog is a bounded per-hotel picker list that the AddServiceModal must show
    in FULL: under the global ``DefaultPagination`` the 26th active service would
    be silently unreachable and could never be added. ``test_catalog_list_is_a_plain_array``
    locks this shape.
    """

    serializer_class = GuestExtraServiceSerializer
    pagination_class = None

    def get_permissions(self):
        if self.request.method == "POST":
            return [CanCreateCatalog()]
        return [CanReadCatalog()]

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
    """GET (any of :data:`GUEST_SERVICE_READ_CODES`) one entry; PATCH
    (``services.update``) edit it. No PUT, no DELETE (both -> 405). ``is_active``
    is not editable here (use the deactivate/activate endpoints, gated on
    ``services.delete``)."""

    serializer_class = GuestExtraServiceSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        return [CanUpdateCatalog()] if self.request.method == "PATCH" else [CanReadCatalog()]

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
