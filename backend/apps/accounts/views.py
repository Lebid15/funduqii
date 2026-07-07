"""Authentication and identity endpoints (Phase 2).

Endpoints:
- POST /api/auth/token/          obtain access + refresh (SimpleJWT)
- POST /api/auth/token/refresh/  rotate access token (SimpleJWT, wired in urls)
- POST /api/auth/logout/         blacklist a refresh token
- GET  /api/auth/me/             current user + memberships + current hotel ctx
- GET  /api/auth/context/        current hotel context + granted permissions
- GET  /api/platform/ping/       platform-owner-only foundation probe
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView as BaseTokenObtainPairView

from apps.rbac.permissions import (
    HasHotelMembership,
    IsAuthenticatedAndActive,
    IsPlatformOwner,
)
from apps.rbac.services import get_hotel_permissions
from apps.tenancy.context import resolve_hotel_context
from apps.tenancy.models import HotelMembership

from .serializers import (
    FunduqiiTokenObtainPairSerializer,
    serialize_hotel_context,
    serialize_membership_summary,
    serialize_user,
)


class TokenObtainPairView(BaseTokenObtainPairView):
    serializer_class = FunduqiiTokenObtainPairSerializer


class LogoutView(APIView):
    """Blacklist a refresh token so it can no longer be rotated."""

    permission_classes = [IsAuthenticatedAndActive]

    def post(self, request: Request) -> Response:
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"code": "invalid_request", "message": "A refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response(
                {"code": "token_not_valid", "message": "The refresh token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response({"detail": "Logged out."}, status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    """Return the current user, their hotel memberships, and — if a valid
    X-Hotel-ID header is present — the resolved current hotel context."""

    permission_classes = [IsAuthenticatedAndActive]

    def get(self, request: Request) -> Response:
        memberships = (
            HotelMembership.objects.filter(user=request.user)
            .select_related("hotel")
        )
        data = {
            "user": serialize_user(request.user),
            "memberships": [serialize_membership_summary(m) for m in memberships],
            "current_hotel": None,
        }
        context = resolve_hotel_context(request, required=False)
        if context is not None:
            data["current_hotel"] = serialize_hotel_context(
                context.hotel,
                context.membership,
                get_hotel_permissions(request.user, context.hotel),
            )
        return Response(data)


class ContextView(APIView):
    """Return the current hotel context and the permissions granted in it.
    Requires a valid X-Hotel-ID header for a hotel the user belongs to."""

    permission_classes = [HasHotelMembership]

    def get(self, request: Request) -> Response:
        permissions = get_hotel_permissions(request.user, request.hotel)
        return Response(
            serialize_hotel_context(request.hotel, request.hotel_membership, permissions)
        )


class PlatformPingView(APIView):
    """FOUNDATION probe: reachable only by a platform owner. Not a feature."""

    permission_classes = [IsPlatformOwner]

    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "scope": "platform"})
