"""Hotel-facing subscription endpoints (§8.4/§8.5), under /api/v1/hotel/.

The hotel's ONLY write access to the subscription lifecycle: view the plans it
can move to (with per-hotel state) and submit / cancel a change request. All
eligibility is decided by the backend service, never the frontend. Reads are
gated by ``settings.view`` and writes by ``settings.update`` (a manager holds
both). A SUSPENDED hotel cannot submit or cancel; a merely expired/inactive one
still can — that is exactly how a lapsed hotel asks to subscribe again.
"""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.permissions import HasHotelPermission
from apps.subscriptions.models import SubscriptionChangeRequest
from apps.subscriptions.request_services import (
    available_plans_for_hotel,
    can_request_renewal,
    cancel_change_request,
    submit_change_request,
)
from apps.subscriptions.serializers import (
    AvailablePlanSerializer,
    SubmitChangeRequestSerializer,
    SubscriptionChangeRequestSerializer,
)

from .views import _ensure_not_suspended

CanView = HasHotelPermission("settings.view")
CanUpdate = HasHotelPermission("settings.update")


class HotelAvailablePlansView(APIView):
    """The plans this hotel can act on, each with its per-hotel state."""

    permission_classes = [CanView]

    def get(self, request: Request) -> Response:
        rows, live_sub = available_plans_for_hotel(request.hotel)
        return Response(
            {
                "plans": AvailablePlanSerializer(rows, many=True).data,
                "can_request_renewal": can_request_renewal(live_sub),
                "current_plan_id": live_sub.plan_id if live_sub is not None else None,
            }
        )


class HotelChangeRequestListCreateView(APIView):
    """List the hotel's own requests, or submit a new one."""

    def get_permissions(self):
        return [CanUpdate()] if self.request.method == "POST" else [CanView()]

    def get(self, request: Request) -> Response:
        qs = (
            SubscriptionChangeRequest.objects.filter(hotel=request.hotel)
            .select_related("requested_plan", "current_subscription__plan")
            .order_by("-created_at")[:100]
        )
        return Response(SubscriptionChangeRequestSerializer(qs, many=True).data)

    def post(self, request: Request) -> Response:
        _ensure_not_suspended(request)
        serializer = SubmitChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        req = submit_change_request(
            request.hotel,
            kind=data["kind"],
            requested_plan=data.get("requested_plan"),
            hotel_note=data.get("hotel_note", ""),
            requested_by=request.user,
        )
        return Response(
            SubscriptionChangeRequestSerializer(req).data,
            status=status.HTTP_201_CREATED,
        )


class HotelChangeRequestCancelView(APIView):
    """Cancel the hotel's own request (only while it is still under review)."""

    permission_classes = [CanUpdate]

    def post(self, request: Request, pk: int) -> Response:
        _ensure_not_suspended(request)
        # Tenant isolation: only the hotel's own request.
        req = generics.get_object_or_404(
            SubscriptionChangeRequest, pk=pk, hotel=request.hotel
        )
        req = cancel_change_request(req, actor=request.user, by_hotel=True)
        return Response(SubscriptionChangeRequestSerializer(req).data)
