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

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import PlanInUse
from apps.rbac.permissions import IsPlatformOwner
from apps.subscriptions import request_services, services as sub_services
from apps.subscriptions.enforcement import effectively_live_q
from apps.subscriptions.entitlements import effective_subscription_state
from apps.subscriptions.models import (
    LIVE_STATUSES,
    OPEN_REQUEST_STATUSES,
    ChangeRequestKind,
    ChangeRequestStatus,
    HotelSubscription,
    PlatformSubscriptionPayment,
    SubscriptionChangeRequest,
    SubscriptionPlan,
    SubscriptionStatus,
)
from apps.subscriptions.serializers import (
    ExecuteRequestSerializer,
    PlatformChangeRequestSerializer,
    RejectRequestSerializer,
)
from apps.tenancy.models import Hotel, HotelStatus

from .models import PlatformPublicSettings, PlatformSettings
from .serializers import (
    ActivatePaidSerializer,
    CancelSubscriptionSerializer,
    ChangePlanSerializer,
    HotelCreateSerializer,
    HotelSerializer,
    HotelSubscriptionSerializer,
    HotelUpdateSerializer,
    ManagerInputSerializer,
    PlatformPaymentCreateSerializer,
    PlatformPaymentSerializer,
    PlatformPublicSettingsSerializer,
    PlatformSettingsSerializer,
    ReactivateSerializer,
    RenewSerializer,
    StartTrialSerializer,
    SubscriptionCreateSerializer,
    SubscriptionPlanSerializer,
    SubscriptionUpdateSerializer,
    SuspendHotelSerializer,
    VoidPaymentSerializer,
)
from .services import (
    activate_hotel,
    create_hotel,
    get_primary_manager,
    set_primary_manager,
    suspend_hotel,
    unsuspend_hotel,
)

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
        # Counters use the EFFECTIVE (date-derived) status, never the stored
        # column alone: a trial/active whose end has passed counts as expired.
        live_q = effectively_live_q(now)

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
                    live_q, status=SubscriptionStatus.TRIAL
                ).count(),
                "active": subs.filter(
                    live_q, status=SubscriptionStatus.ACTIVE
                ).count(),
                "expiring_soon": subs.filter(
                    live_q,
                    status=SubscriptionStatus.ACTIVE,
                    ends_at__isnull=False,
                    ends_at__lte=soon,
                ).count(),
                "expired": (
                    subs.filter(status=SubscriptionStatus.EXPIRED).count()
                    + subs.filter(status__in=list(LIVE_STATUSES))
                    .exclude(live_q)
                    .count()
                ),
            },
            "recent_hotels": HotelSerializer(recent_hotels, many=True).data,
            "recent_subscriptions": HotelSubscriptionSerializer(
                recent_subs, many=True
            ).data,
        }
        return Response(data)


# --- Dashboard (Phase 16) -----------------------------------------------------


class DashboardView(PlatformOwnerMixin, APIView):
    """The completed owner dashboard. Numbers are ADMINISTRATIVE indicators —
    the revenue figure is an ESTIMATED recurring revenue from manually
    activated subscriptions, never called profit and never a legal financial
    report."""

    def get(self, request: Request) -> Response:
        from decimal import Decimal

        from apps.hotels.models import HotelSettings
        from apps.subscriptions.enforcement import EXPIRING_SOON_DAYS

        now = timezone.now()
        soon = now + timedelta(days=EXPIRING_SOON_DAYS)
        hotels = Hotel.objects.all()
        subs = HotelSubscription.objects.select_related("hotel", "plan")

        active_subs = subs.filter(status=SubscriptionStatus.ACTIVE).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now)
        )
        trial_subs = subs.filter(
            status=SubscriptionStatus.TRIAL, trial_ends_at__gt=now
        )

        # Estimated MONTHLY recurring revenue per currency (Decimal only):
        # monthly price as-is, yearly price divided by 12, custom excluded.
        revenue: dict[str, Decimal] = {}
        excluded_custom = 0
        for sub in active_subs:
            plan = sub.plan
            if plan.billing_cycle == "monthly":
                monthly = plan.price
            elif plan.billing_cycle == "yearly":
                monthly = (plan.price / Decimal(12)).quantize(Decimal("0.01"))
            else:
                excluded_custom += 1
                continue
            revenue[plan.currency] = revenue.get(plan.currency, Decimal("0")) + monthly

        settings_qs = HotelSettings.objects.all()

        data = {
            "total_hotels": hotels.count(),
            "active_hotels": hotels.filter(status=HotelStatus.ACTIVE).count(),
            "setup_hotels": hotels.filter(status=HotelStatus.SETUP).count(),
            "suspended_hotels": hotels.filter(status=HotelStatus.SUSPENDED).count(),
            "trial_hotels": trial_subs.values("hotel").distinct().count(),
            "paid_hotels": active_subs.values("hotel").distinct().count(),
            "expired_subscriptions": (
                subs.filter(status=SubscriptionStatus.EXPIRED).count()
                + subs.filter(status__in=list(LIVE_STATUSES))
                .exclude(effectively_live_q(now))
                .count()
            ),
            "expiring_soon_subscriptions": subs.filter(
                status__in=(SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE)
            )
            .filter(
                (
                    Q(status=SubscriptionStatus.ACTIVE, ends_at__gt=now, ends_at__lte=soon)
                    | Q(
                        status=SubscriptionStatus.TRIAL,
                        trial_ends_at__gt=now,
                        trial_ends_at__lte=soon,
                    )
                )
            )
            .count(),
            "total_plans": SubscriptionPlan.objects.count(),
            "public_listed_hotels": settings_qs.filter(
                public_is_listed=True, hotel__status=HotelStatus.ACTIVE
            ).count(),
            "public_booking_enabled_hotels": settings_qs.filter(
                public_is_listed=True,
                allow_public_booking=True,
                hotel__status=HotelStatus.ACTIVE,
            ).count(),
            "estimated_monthly_recurring_revenue": {
                currency: str(total) for currency, total in sorted(revenue.items())
            },
            "revenue_excluded_custom_cycles": excluded_custom,
            "recent_hotels": HotelSerializer(
                hotels.order_by("-created_at")[:5], many=True
            ).data,
            "recent_subscription_events": HotelSubscriptionSerializer(
                subs.order_by("-updated_at")[:8], many=True
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


class PlanActivateView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        plan = generics.get_object_or_404(SubscriptionPlan, pk=pk)
        plan.is_active = True
        plan.save(update_fields=["is_active", "updated_at"])
        return Response(SubscriptionPlanSerializer(plan).data)


class PlanDeactivateView(PlatformOwnerMixin, APIView):
    """Deactivation is the safe alternative to deleting a used plan: existing
    subscriptions keep working; new activations on the plan are refused."""

    def post(self, request: Request, pk: int) -> Response:
        plan = generics.get_object_or_404(SubscriptionPlan, pk=pk)
        plan.is_active = False
        plan.save(update_fields=["is_active", "updated_at"])
        return Response(SubscriptionPlanSerializer(plan).data)


# --- Hotels / tenants -------------------------------------------------------


class HotelListCreateView(PlatformOwnerMixin, generics.ListCreateAPIView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return HotelCreateSerializer
        return HotelSerializer

    def get_queryset(self):
        # Phase 17 — the serializer reads settings + status_changed_by per
        # row; one JOIN instead of two queries per hotel (PR #15 review note).
        qs = Hotel.objects.select_related("settings", "status_changed_by").all()
        status_filter = self.request.query_params.get("status")
        valid = {c for c, _ in HotelStatus.choices}
        if status_filter in valid:
            qs = qs.filter(status=status_filter)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(
                slug__icontains=search
            )
        # Phase 16 — owner-panel filters.
        city = self.request.query_params.get("city")
        if city:
            qs = qs.filter(settings__city__icontains=city)
        public = self.request.query_params.get("public")
        if public in ("true", "false"):
            qs = qs.filter(settings__public_is_listed=(public == "true"))
        sub_status = self.request.query_params.get("subscription")
        if sub_status in {c for c, _ in SubscriptionStatus.choices}:
            qs = qs.filter(subscriptions__status=sub_status)
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


# --- Hotel status actions (Phase 16) ------------------------------------------


class HotelActivateView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        activate_hotel(hotel, actor=request.user)
        return Response(HotelSerializer(hotel).data)


class HotelSuspendView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        serializer = SuspendHotelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        suspend_hotel(
            hotel, reason=serializer.validated_data["reason"], actor=request.user
        )
        return Response(HotelSerializer(hotel).data)


class HotelUnsuspendView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        unsuspend_hotel(hotel, actor=request.user)
        return Response(HotelSerializer(hotel).data)


# --- Subscription lifecycle per hotel (Phase 16) -------------------------------


def _maybe_record_payment(request, hotel, sub, data) -> None:
    """Optionally record the MANUAL payment sent along with activate/renew."""
    if data.get("payment_amount") is None:
        return
    sub_services.record_platform_payment(
        hotel,
        subscription=sub,
        amount=data["payment_amount"],
        currency=sub.plan.currency,
        method=data.get("payment_method") or "manual",
        reference=data.get("payment_reference", ""),
        recorded_by=request.user,
    )


class HotelStartTrialView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        serializer = StartTrialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sub = sub_services.start_trial(
            hotel,
            data["plan"],
            trial_days=data.get("trial_days"),
            notes=data.get("notes", ""),
        )
        return Response(
            HotelSubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED
        )


class HotelActivatePaidView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        serializer = ActivatePaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sub = sub_services.activate_subscription(
            hotel,
            data["plan"],
            starts_at=data.get("starts_at"),
            ends_at=data.get("ends_at"),
            notes=data.get("notes", ""),
        )
        _maybe_record_payment(request, hotel, sub, data)
        return Response(
            HotelSubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED
        )


class HotelRenewView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        from apps.common.exceptions import InvalidSubscriptionTransition

        hotel = generics.get_object_or_404(Hotel, pk=pk)
        sub = sub_services.get_current_subscription(hotel)
        if sub is None:
            raise InvalidSubscriptionTransition()
        serializer = RenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sub = sub_services.renew_subscription(
            sub,
            ends_at=data.get("ends_at"),
            days=data.get("days"),
            notes=data.get("notes", ""),
        )
        _maybe_record_payment(request, hotel, sub, data)
        return Response(HotelSubscriptionSerializer(sub).data)


class HotelCancelSubscriptionView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        from apps.common.exceptions import InvalidSubscriptionTransition

        hotel = generics.get_object_or_404(Hotel, pk=pk)
        sub = sub_services.get_current_subscription(hotel)
        if sub is None:
            raise InvalidSubscriptionTransition()
        serializer = CancelSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sub = sub_services.cancel_subscription(sub)
        notes = serializer.validated_data.get("notes", "")
        if notes:
            sub.notes = f"{sub.notes}\n{notes}".strip()
            sub.save(update_fields=["notes", "updated_at"])
        return Response(HotelSubscriptionSerializer(sub).data)


class HotelExpireSubscriptionView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        from apps.common.exceptions import InvalidSubscriptionTransition

        hotel = generics.get_object_or_404(Hotel, pk=pk)
        sub = sub_services.get_current_subscription(hotel)
        if sub is None:
            raise InvalidSubscriptionTransition()
        sub = sub_services.expire_subscription(sub)
        return Response(HotelSubscriptionSerializer(sub).data)


class HotelChangePlanView(PlatformOwnerMixin, APIView):
    """Explicitly move the hotel's live subscription to a different plan.

    Immediate for upgrade and downgrade (no proration); existing resources are
    grandfathered and only NEW ones above the new limits are blocked.
    """

    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        serializer = ChangePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sub = sub_services.change_subscription_plan(
            hotel,
            data["plan"],
            actor=request.user,
            reason=data.get("reason", ""),
            notes=data.get("notes", ""),
        )
        _maybe_record_payment(request, hotel, sub, data)
        return Response(HotelSubscriptionSerializer(sub).data)


class HotelReactivateView(PlatformOwnerMixin, APIView):
    """Revive billing for a hotel whose subscription has ended (a NEW one)."""

    def post(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        serializer = ReactivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sub = sub_services.reactivate_subscription(
            hotel,
            data["plan"],
            starts_at=data.get("starts_at"),
            ends_at=data.get("ends_at"),
            notes=data.get("notes", ""),
        )
        _maybe_record_payment(request, hotel, sub, data)
        return Response(
            HotelSubscriptionSerializer(sub).data, status=status.HTTP_201_CREATED
        )


class HotelSubscriptionStateView(PlatformOwnerMixin, APIView):
    """The hotel's effective subscription state + entitlement usage (owner)."""

    def get(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        return Response(effective_subscription_state(hotel))


class HotelSubscriptionHistoryView(PlatformOwnerMixin, APIView):
    """Full, preserved subscription history of one hotel (nothing deleted)."""

    def get(self, request: Request, pk: int) -> Response:
        hotel = generics.get_object_or_404(Hotel, pk=pk)
        subs = (
            HotelSubscription.objects.filter(hotel=hotel)
            .select_related("hotel", "plan")
            .order_by("-created_at")
        )
        return Response(HotelSubscriptionSerializer(subs, many=True).data)


# --- Manual platform payments (Phase 16 — NOT a gateway) -----------------------


class PlatformPaymentListCreateView(PlatformOwnerMixin, APIView):
    def get(self, request: Request) -> Response:
        qs = PlatformSubscriptionPayment.objects.select_related(
            "hotel", "recorded_by"
        ).all()
        hotel_id = request.query_params.get("hotel")
        if hotel_id and str(hotel_id).isdigit():
            qs = qs.filter(hotel_id=int(hotel_id))
        return Response(PlatformPaymentSerializer(qs[:200], many=True).data)

    def post(self, request: Request) -> Response:
        serializer = PlatformPaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        subscription = None
        if data.get("subscription"):
            subscription = generics.get_object_or_404(
                HotelSubscription, pk=data["subscription"]
            )
        payment = sub_services.record_platform_payment(
            data["hotel"],
            subscription=subscription,
            amount=data["amount"],
            currency=data.get("currency", "USD"),
            method=data["method"],
            reference=data.get("reference", ""),
            note=data.get("note", ""),
            received_at=data.get("received_at"),
            recorded_by=request.user,
        )
        return Response(
            PlatformPaymentSerializer(payment).data, status=status.HTTP_201_CREATED
        )


class PlatformPaymentVoidView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        payment = generics.get_object_or_404(PlatformSubscriptionPayment, pk=pk)
        serializer = VoidPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = sub_services.void_platform_payment(
            payment, reason=serializer.validated_data["reason"]
        )
        return Response(PlatformPaymentSerializer(payment).data)


# --- Public site settings (Phase 16) -------------------------------------------


@transaction.atomic
def _save_and_audit_platform(request, settings_obj, serializer, section):
    """§9.17 — save a validated platform-settings serializer and append a
    platform-scoped (hotel=NULL) audit row with the field-level diff.

    ATOMIC (audit-or-nothing): the save and its audit row commit together."""
    from apps.hotels.models import SettingsAuditScope
    from apps.hotels.settings_services import (
        diff_settings,
        record_settings_change,
        snapshot,
    )

    fields = list(serializer.validated_data.keys())
    before = snapshot(settings_obj, fields)
    # Column-scoped write (see hotel _apply_settings_update): a concurrent save
    # to other platform fields cannot clobber this one's columns.
    for field, value in serializer.validated_data.items():
        setattr(settings_obj, field, value)
    if fields:
        settings_obj.save(update_fields=fields + ["updated_at"])
    record_settings_change(
        scope=SettingsAuditScope.PLATFORM,
        section=section,
        changes=diff_settings(settings_obj, before, snapshot(settings_obj, fields)),
        hotel=None,
        actor=request.user,
    )
    settings_obj.refresh_from_db()


class PublicSiteSettingsView(PlatformOwnerMixin, APIView):
    """Read or patch the singleton public-website settings row."""

    def get(self, request: Request) -> Response:
        settings = PlatformPublicSettings.load()
        return Response(PlatformPublicSettingsSerializer(settings).data)

    def patch(self, request: Request) -> Response:
        settings = PlatformPublicSettings.load()
        serializer = PlatformPublicSettingsSerializer(
            settings, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        _save_and_audit_platform(request, settings, serializer, "public_site")
        return Response(serializer.data)


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
        # Phase 16 — live subscriptions ending within the warning window.
        if self.request.query_params.get("expiring") == "soon":
            from apps.subscriptions.enforcement import EXPIRING_SOON_DAYS

            now = timezone.now()
            soon = now + timedelta(days=EXPIRING_SOON_DAYS)
            qs = qs.filter(
                Q(status=SubscriptionStatus.ACTIVE, ends_at__gt=now, ends_at__lte=soon)
                | Q(
                    status=SubscriptionStatus.TRIAL,
                    trial_ends_at__gt=now,
                    trial_ends_at__lte=soon,
                )
            )
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


# --- Subscription change requests (§8.5 — hotel-initiated, owner review) ------


def _get_request_qs():
    return SubscriptionChangeRequest.objects.select_related(
        "hotel",
        "requested_plan",
        "current_subscription__plan",
        "requested_by",
        "decided_by",
    )


class SubscriptionRequestListView(PlatformOwnerMixin, APIView):
    """All hotel-submitted change requests, newest first (filterable)."""

    def get(self, request: Request) -> Response:
        qs = _get_request_qs().all()
        status_filter = request.query_params.get("status")
        if status_filter == "open":
            qs = qs.filter(status__in=list(OPEN_REQUEST_STATUSES))
        elif status_filter in {c for c, _ in ChangeRequestStatus.choices}:
            qs = qs.filter(status=status_filter)
        kind = request.query_params.get("kind")
        if kind in {c for c, _ in ChangeRequestKind.choices}:
            qs = qs.filter(kind=kind)
        hotel_id = request.query_params.get("hotel")
        if hotel_id and str(hotel_id).isdigit():
            qs = qs.filter(hotel_id=int(hotel_id))
        return Response(
            PlatformChangeRequestSerializer(qs[:300], many=True).data
        )


class SubscriptionRequestDetailView(PlatformOwnerMixin, APIView):
    def get(self, request: Request, pk: int) -> Response:
        req = generics.get_object_or_404(_get_request_qs(), pk=pk)
        return Response(PlatformChangeRequestSerializer(req).data)


class SubscriptionRequestAcceptView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        req = generics.get_object_or_404(SubscriptionChangeRequest, pk=pk)
        req = request_services.accept_change_request(req, actor=request.user)
        return Response(PlatformChangeRequestSerializer(req).data)


class SubscriptionRequestRejectView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        req = generics.get_object_or_404(SubscriptionChangeRequest, pk=pk)
        serializer = RejectRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = request_services.reject_change_request(
            req, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(PlatformChangeRequestSerializer(req).data)


class SubscriptionRequestExecuteView(PlatformOwnerMixin, APIView):
    """Apply an accepted request via the matching lifecycle service."""

    def post(self, request: Request, pk: int) -> Response:
        req = generics.get_object_or_404(SubscriptionChangeRequest, pk=pk)
        serializer = ExecuteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = None
        if data.get("payment_amount") is not None:
            payment = {
                "amount": data["payment_amount"],
                "method": data.get("payment_method"),
                "reference": data.get("payment_reference", ""),
            }
        req, _sub = request_services.execute_change_request(
            req, actor=request.user, payment=payment, notes=data.get("notes", "")
        )
        return Response(PlatformChangeRequestSerializer(req).data)


class SubscriptionRequestCancelView(PlatformOwnerMixin, APIView):
    def post(self, request: Request, pk: int) -> Response:
        req = generics.get_object_or_404(SubscriptionChangeRequest, pk=pk)
        req = request_services.cancel_change_request(
            req, actor=request.user, by_hotel=False
        )
        return Response(PlatformChangeRequestSerializer(req).data)


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
        _save_and_audit_platform(request, settings, serializer, "platform")
        return Response(serializer.data)


class PlatformSettingsAuditView(PlatformOwnerMixin, generics.ListAPIView):
    """§9.17 read-only audit trail of platform-settings changes."""

    def get_serializer_class(self):
        from apps.hotels.serializers import SettingsAuditLogSerializer

        return SettingsAuditLogSerializer

    def get_queryset(self):
        from apps.hotels.models import SettingsAuditLog, SettingsAuditScope

        return (
            SettingsAuditLog.objects.filter(scope=SettingsAuditScope.PLATFORM)
            .select_related("actor")
            .order_by("-created_at", "-id")
        )
