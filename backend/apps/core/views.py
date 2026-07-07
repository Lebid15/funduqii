"""Infrastructure views for the Funduqii backend (Phase 1).

Only a liveness/health probe lives here. No business endpoints are added in
Phase 1.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Report that the API process is up. Infrastructure only, not a feature."""
    return Response({"status": "ok", "service": "funduqii-api"})
