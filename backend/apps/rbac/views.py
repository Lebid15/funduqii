"""FOUNDATION probe view — exercises HasHotelPermission end-to-end.

This is a Phase 2 wiring test, NOT the reports feature. It is guarded by
``reports.view`` only because it needs *some* permission to check; it returns a
static payload and exposes no business data.
"""
from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import HasHotelPermission

REQUIRED_PERMISSION = "reports.view"


class RequirePermissionProbeView(APIView):
    permission_classes = [HasHotelPermission(REQUIRED_PERMISSION)]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "scope": "hotel",
                "hotel_id": request.hotel.id,
                "required_permission": REQUIRED_PERMISSION,
            }
        )
