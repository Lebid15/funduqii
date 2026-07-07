"""Platform-owner API views (Phase 3), mounted under /api/v1/platform/.

Every view here is restricted to the platform owner via ``IsPlatformOwner``.
Hotel users, staff and unauthenticated callers are rejected by the backend —
hiding UI is never the protection. These are the platform owner's basics:
overview, hotels-as-tenants, plans, hotel subscriptions and platform settings.
No hotel-panel, reservations, rooms, guests, money, messaging or public-website
endpoints exist here.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import PlanInUse
from apps.rbac.permissions import IsPlatformOwner
from apps.subscriptions import services as sub_services
from apps.subscriptions.models import (
    HotelSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.tenancy.models import Hotel, HotelStatus

from .models import PlatformSettings
from .serializers import (
    HotelCreateSerializer,
    HotelSerializer,
    HotelSubscriptionSerializer,
    HotelUpdateSerializer,
    ManagerInputSerializer,
    PlatformSettingsSerializer,
    SubscriptionCreateSerializer,
    SubscriptionPlanSerializer,
    SubscriptionUpdateSerializer,
)
from .services import create_hotel, get_primary_manager, set_primary_manager

# Window (in days) used to flag subscriptions as "expiring soon".
EXPIRING_SOON_DAYS = 14


class PlatformOwnerMixin:
    """Shared guard: only the platform owner may reach these endpoints."""

    permission_classes = [IsPlatformOwner]


# --- Overview ---------------------------------------------------------------


class OverviewView(PlatformOwnerMixin, APIView):
    """Summary counters + recent activity for the platform dashboard."""

    def get(self, request: Request) -> Response:
        now = timezone.now()
        soon = now + timedelta(days=EXPIRING_SOON_DAYS)

        hotels = Hotel.objects.all()
        subs = HotelSubscription.objects.all()

        recent_hotels = list(hotels.order_by("-created_at")[:5])
        recent_subs = (
            subs.select_related("hotel", "plan").order_by("-created_at")[:5]
        )

        data = {
            "hotels": {
                "total": hotels.count(),
                "active": hotels.filter(status=HotelStatus.ACTIVE).count(),
                "setup": hotels.filter(status=HotelStatus.SETUP).count(),
                "suspended": hotels.filter(status=HotelStatus.SUSPENDED).count(),
            },
            "subscriptions": {
                "active_trials": subs.filter(
                    status=SubscriptionStatus.TRIAL
                ).count(),
                "active": subs.filter(status=SubscriptionStatus.ACTIVE).count(),
                "expiring_soon": subs.filter(
                    status=SubscriptionStatus.ACTIVE,
                    ends_at__isnull=False,
                    ends_at__gte=now,
                    ends_at__lte=soon,
                ).count(),
                "expired": subs.filter(
                    status=SubscriptionStatus.EXPIRED
                ).count(),
            },
            "recent_hotels": HotelSerializer(recent_hotels, many=True).data,
            "recent_subscriptions": HotelSubscriptionSerializer(
                recent_subs, many=True
            ).data,
        }
        return Response(data)


# --- Subscription plans -----------------------------------------------------


class PlanListCreateView(PlatformOwnerMixin, generics.ListCreateAPIView):
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        qs = SubscriptionPlan.objects.all()
        is_active = self.request.query_params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        return qs


class PlanDetailView(PlatformOwnerMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all()

    def perform_destroy(self, instance: SubscriptionPlan) -> None:
        # A plan referenced by any subscription is never hard-deleted; the owner
        # deactivates it instead (PATCH is_active=false).
        if instance.is_in_use:
            raise PlanInUse()
        instance.delete()


# --- Hotels / tenants -------------------------------------------------------


class HotelListCreateView(PlatformOwnerMixin, generics.ListCreateAPIView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return HotelCreateSerializer
        return HotelSerializer

    def get_queryset(self):
        qs = Hotel.objects.all()
        status_filter = self.request.query_params.get("status")
        valid = {c for c, _ in HotelStatus.choices}
        if status_filter in valid:
            qs = qs.filter(status=status_filter)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(
                slug__icontains=search
            )
        return qs.distinct()

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        manager = data.pop("manager", None)

        hotel = create_hotel(
            name=data["name"],
            slug=data["slug"],
            status=data.get("status"),
        )
        if manager:
            set_primary_manager(
                hotel,
                email=manager["email"],
                full_name=manager["full_name"],
                password=manager["password"],
            )
        return Response(
            HotelSerializer(hotel).data, status=status.HTTP_201_CREATED
        )


class HotelDetailView(PlatformOwnerMixin, generics.RetrieveUpdateAPIView):
    queryset = Hotel.objects.all()

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return HotelUpdateSerializer
        return HotelSerializer

    def update(self, request: Request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", False)
        hotel = self.get_object()
        serializer = self.get_serializer(hotel, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(HotelSerializer(hotel).data)


class HotelManagerView(PlatformOwnerMixin, APIView):
    """Create or link the primary manager of an existing hotel."""

    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        serializer = ManagerInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_primary_manager(
            hotel,
            email=serializer.validated_data["email"],
            full_name=serializer.validated_data["full_name"],
            password=serializer.validated_data["password"],
        )
        return Response(HotelSerializer(hotel).data, status=status.HTTP_200_OK)


# --- Hotel subscriptions ----------------------------------------------------


class SubscriptionListCreateView(PlatformOwnerMixin, generics.ListCreateAPIView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return SubscriptionCreateSerializer
        return HotelSubscriptionSerializer

    def get_queryset(self):
        qs = HotelSubscription.objects.select_related("hotel", "plan").all()
        status_filter = self.request.query_params.get("status")
        valid = {c for c, _ in SubscriptionStatus.choices}
        if status_filter in valid:
            qs = qs.filter(status=status_filter)
        hotel_id = self.request.query_params.get("hotel")
        if hotel_id and str(hotel_id).isdigit():
            qs = qs.filter(hotel_id=int(hotel_id))
        return qs

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = SubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        hotel = data["hotel"]
        plan = data["plan"]
        notes = data.get("notes", "")

        if data["kind"] == SubscriptionCreateSerializer.KIND_TRIAL:
            sub = sub_services.start_trial(
                hotel, plan, trial_days=data.get("trial_days"), notes=notes
            )
        else:
            sub = sub_services.activate_subscription(
                hotel,
                plan,
                starts_at=data.get("starts_at"),
                ends_at=data.get("ends_at"),
                notes=notes,
            )
        return Response(
            HotelSubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED
        )


class SubscriptionDetailView(PlatformOwnerMixin, generics.RetrieveUpdateAPIView):
    queryset = HotelSubscription.objects.select_related("hotel", "plan").all()
    serializer_class = HotelSubscriptionSerializer

    def update(self, request: Request, *args, **kwargs) -> Response:
        sub = self.get_object()
        serializer = SubscriptionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data.get("status")

        if new_status == SubscriptionStatus.CANCELLED:
            sub_services.cancel_subscription(sub)
        elif new_status == SubscriptionStatus.EXPIRED:
            sub_services.expire_subscription(sub)

        if "notes" in serializer.validated_data:
            sub.notes = serializer.validated_data["notes"]
            sub.save(update_fields=["notes", "updated_at"])

        sub.refresh_from_db()
        return Response(HotelSubscriptionSerializer(sub).data)


# --- Platform settings ------------------------------------------------------


class SettingsView(PlatformOwnerMixin, APIView):
    """Read or patch the singleton platform settings row."""

    def get(self, request: Request) -> Response:
        settings = PlatformSettings.load()
        return Response(PlatformSettingsSerializer(settings).data)

    def patch(self, request: Request) -> Response:
        settings = PlatformSettings.load()
        serializer = PlatformSettingsSerializer(
            settings, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
