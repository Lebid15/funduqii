"""Staff & permissions API views (Phase 11), under /api/v1/hotel/staff/.

Scoped to the caller's hotel, guarded by ``staff.*`` permissions. A suspended
hotel is read-only. All mutations go through the domain services; access is
decided by permission grants only — never by job titles or fixed roles.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework import generics
from rest_framework import status as http_status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.permissions import HasHotelMembership, HasHotelPermission
from apps.rbac.registry import is_valid_permission
from apps.rbac.services import get_hotel_permissions
from apps.tenancy.models import HotelMembership, MembershipType
from apps.subscriptions.enforcement import ensure_hotel_operational

from . import services
from .serializers import (
    DeactivateSerializer,
    LinkExistingUserSerializer,
    PermissionsPutSerializer,
    ResetPasswordSerializer,
    StaffCreateSerializer,
    StaffDetailSerializer,
    StaffListSerializer,
    StaffUpdateSerializer,
)

User = get_user_model()

StaffView = HasHotelPermission("staff.view")
StaffCreate = HasHotelPermission("staff.create")
StaffUpdate = HasHotelPermission("staff.update")
StaffDeactivate = HasHotelPermission("staff.deactivate")
PermissionsView = HasHotelPermission("staff.permissions_view")
PermissionsUpdate = HasHotelPermission("staff.permissions_update")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _get_membership(request: Request, pk: int) -> HotelMembership:
    return generics.get_object_or_404(
        HotelMembership.objects.select_related("user"), pk=pk, hotel=request.hotel
    )


class StaffListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        return [StaffCreate()] if self.request.method == "POST" else [StaffView()]

    def get_serializer_class(self):
        return StaffListSerializer

    def get_queryset(self):
        qs = (
            HotelMembership.objects.filter(hotel=self.request.hotel)
            .select_related("user")
            .annotate(permission_count=Count("permission_grants"))
        )
        p = self.request.query_params
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        if p.get("membership_type") in {c for c, _ in MembershipType.choices}:
            qs = qs.filter(membership_type=p["membership_type"])
        if p.get("has_permission") and is_valid_permission(p["has_permission"]):
            qs = qs.filter(permission_grants__code=p["has_permission"])
        if p.get("search"):
            s = p["search"]
            qs = (
                qs.filter(user__full_name__icontains=s)
                | qs.filter(user__email__icontains=s)
                | qs.filter(user__phone__icontains=s)
                | qs.filter(job_title__icontains=s)
                | qs.filter(staff_code__icontains=s)
            )
        ordering = p.get("ordering")
        if ordering not in (
            "created_at", "-created_at", "user__full_name", "-user__full_name",
        ):
            ordering = "id"
        return qs.order_by(ordering).distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = services.create_staff_member(
            request.hotel,
            actor=request.user,
            email=data["email"],
            full_name=data["full_name"],
            password=data["password"],
            phone=data.get("phone", ""),
            job_title=data.get("job_title", ""),
            staff_code=data.get("staff_code", ""),
            notes=data.get("notes", ""),
            permissions=data.get("permissions", []),
        )
        return Response(
            StaffDetailSerializer(membership).data, status=http_status.HTTP_201_CREATED
        )


class StaffLinkExistingView(APIView):
    permission_classes = [StaffCreate]

    def post(self, request: Request) -> Response:
        _guard_write(request)
        serializer = LinkExistingUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.filter(email__iexact=data["email"]).first()
        if user is None:
            raise NotFound("No user with this email exists.")
        membership = services.link_existing_user(
            request.hotel,
            actor=request.user,
            user=user,
            job_title=data.get("job_title", ""),
            staff_code=data.get("staff_code", ""),
            notes=data.get("notes", ""),
            permissions=data.get("permissions", []),
        )
        return Response(
            StaffDetailSerializer(membership).data, status=http_status.HTTP_201_CREATED
        )


class StaffDetailView(APIView):
    def get_permissions(self):
        return [StaffUpdate()] if self.request.method == "PATCH" else [StaffView()]

    def get(self, request: Request, pk: int) -> Response:
        membership = _get_membership(request, pk)
        return Response(StaffDetailSerializer(membership).data)

    def patch(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        membership = _get_membership(request, pk)
        serializer = StaffUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        membership = services.update_staff_member(
            membership, actor=request.user, **serializer.validated_data
        )
        return Response(StaffDetailSerializer(membership).data)


class StaffDeactivateView(APIView):
    permission_classes = [StaffDeactivate]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        membership = _get_membership(request, pk)
        serializer = DeactivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.deactivate_staff_member(
            membership,
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(StaffDetailSerializer(membership).data)


class StaffReactivateView(APIView):
    permission_classes = [StaffDeactivate]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        membership = _get_membership(request, pk)
        membership = services.reactivate_staff_member(membership, actor=request.user)
        return Response(StaffDetailSerializer(membership).data)


class StaffResetPasswordView(APIView):
    permission_classes = [StaffUpdate]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        membership = _get_membership(request, pk)
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_staff_password(
            membership, actor=request.user, password=serializer.validated_data["password"]
        )
        # The password is delivered to the employee OUTSIDE the system; it is
        # never echoed back in any response.
        return Response({"status": "password_reset"})


class StaffPermissionsView(APIView):
    def get_permissions(self):
        if self.request.method == "PUT":
            return [PermissionsUpdate()]
        return [PermissionsView()]

    def get(self, request: Request, pk: int) -> Response:
        membership = _get_membership(request, pk)
        granted = sorted(
            membership.permission_grants.values_list("code", flat=True)
        )
        return Response(
            {
                "membership": membership.id,
                "full_name": membership.user.full_name,
                "is_manager": membership.is_manager,
                "is_active": membership.is_active,
                "editable": not membership.is_manager,
                "is_self": membership.user_id == request.user.id,
                "granted": granted,
                "effective": get_hotel_permissions(membership.user, request.hotel),
                "registry": services.permission_registry_payload(),
            }
        )

    def put(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        membership = _get_membership(request, pk)
        serializer = PermissionsPutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        granted = services.set_staff_permissions(
            membership,
            actor=request.user,
            codes=serializer.validated_data["permissions"],
        )
        return Response(
            {
                "membership": membership.id,
                "granted": granted,
                "effective": get_hotel_permissions(membership.user, request.hotel),
            }
        )


class PermissionRegistryView(APIView):
    permission_classes = [StaffView]

    def get(self, request: Request) -> Response:
        return Response({"sections": services.permission_registry_payload()})


class MyPermissionsView(APIView):
    """Effective permissions of the CURRENT user in the current hotel — the
    sidebar/route guard reads this. Membership is enough (it is about self);
    the API layer still enforces real permissions on every endpoint."""

    permission_classes = [HasHotelMembership]

    def get(self, request: Request) -> Response:
        membership = request.hotel_membership
        return Response(
            {
                "is_manager": bool(membership and membership.is_manager),
                "permissions": get_hotel_permissions(request.user, request.hotel),
            }
        )


class StaffOverviewView(APIView):
    permission_classes = [StaffView]

    def get(self, request: Request) -> Response:
        return Response(services.staff_overview(request.hotel))
