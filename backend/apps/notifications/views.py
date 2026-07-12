"""Notification/activity API views (Phase 14), under
/api/v1/hotel/notifications/.

Scoped to the caller's hotel, guarded by ``notifications.*`` / ``activity.*``
permissions. A user sees ONLY their own notifications; the activity center is
permission-scoped (`activity.view_all` or manager → everything; otherwise the
categories the user may view plus their own actions).

A SUSPENDED hotel may read everything here AND mark read/archive — those are
user-state flags, not operational writes (documented decision). There are no
DELETE endpoints and no external channels.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Case, IntegerField, Value, When

from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import get_hotel_permissions
from apps.tenancy.models import MembershipType

from . import services
from .models import (
    ActivityCategory,
    ActivityEvent,
    ActivitySeverity,
    Notification,
    NotificationScope,
)
from .serializers import ActivityEventSerializer, NotificationSerializer

NotifView = HasHotelPermission("notifications.view")
NotifUpdate = HasHotelPermission("notifications.update")
ActivityView = HasHotelPermission("activity.view")

#: Priority ordering: danger, then warning, success, info (then recency).
SEVERITY_RANK = Case(
    When(severity=ActivitySeverity.DANGER, then=Value(0)),
    When(severity=ActivitySeverity.WARNING, then=Value(1)),
    When(severity=ActivitySeverity.SUCCESS, then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)


def _my_notifications(request: Request):
    # Hotel console only ever sees HOTEL-scoped notifications; platform-scoped
    # rows belong to the platform owner's own centre.
    return Notification.objects.filter(
        hotel=request.hotel,
        recipient=request.user,
        scope=NotificationScope.HOTEL,
    )


def _visible_activity(request: Request):
    """Everything for managers / `activity.view_all`; otherwise the categories
    the user's own view permissions cover, plus events they acted in or were
    targeted by (documented rule)."""
    qs = ActivityEvent.objects.filter(
        hotel=request.hotel, scope=NotificationScope.HOTEL
    )
    membership = request.hotel_membership
    if membership and membership.membership_type == MembershipType.MANAGER:
        return qs
    codes = set(get_hotel_permissions(request.user, request.hotel))
    if "activity.view_all" in codes:
        return qs
    categories = [
        category
        for category, needed in services.CATEGORY_VIEW_CODES.items()
        if needed and codes.intersection(needed)
    ]
    from django.db.models import Q

    return qs.filter(
        Q(category__in=categories)
        | Q(actor=request.user)
        | Q(target_user=request.user)
    )


class NotificationsOverviewView(APIView):
    permission_classes = [NotifView]

    def get(self, request: Request) -> Response:
        mine = _my_notifications(request)
        active = mine.filter(is_archived=False)
        today = timezone.localdate()
        return Response(
            {
                "unread_count": active.filter(is_read=False).count(),
                "today_notifications_count": mine.filter(
                    created_at__date=today
                ).count(),
                "warning_count": active.filter(
                    is_read=False, severity=ActivitySeverity.WARNING
                ).count(),
                "danger_count": active.filter(
                    is_read=False, severity=ActivitySeverity.DANGER
                ).count(),
                "archived_count": mine.filter(is_archived=True).count(),
                "recent_activity_count": _visible_activity(request)
                .filter(occurred_at__date=today)
                .count(),
            }
        )


class UnreadCountView(APIView):
    permission_classes = [NotifView]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "unread": _my_notifications(request)
                .filter(is_read=False, is_archived=False)
                .count()
            }
        )


class NotificationListView(generics.ListAPIView):
    permission_classes = [NotifView]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = _my_notifications(self.request)
        p = self.request.query_params
        # Archived rows are hidden unless explicitly requested.
        if p.get("archived") == "true":
            qs = qs.filter(is_archived=True)
        else:
            qs = qs.filter(is_archived=False)
        if p.get("unread") in ("true", "false"):
            qs = qs.filter(is_read=(p["unread"] == "false"))
        if p.get("category") in {c for c, _ in ActivityCategory.choices}:
            qs = qs.filter(category=p["category"])
        if p.get("severity") in {c for c, _ in ActivitySeverity.choices}:
            qs = qs.filter(severity=p["severity"])
        if p.get("date"):
            qs = qs.filter(created_at__date=p["date"])
        ordering = p.get("ordering")
        if ordering in ("created_at", "-created_at"):
            return qs.order_by(ordering, "-id")
        # Default: highest priority first (danger→warning→success→info), then
        # newest. Stable tiebreak on -id keeps pagination consistent.
        return qs.annotate(_sev=SEVERITY_RANK).order_by("_sev", "-created_at", "-id")


class NotificationDetailView(APIView):
    permission_classes = [NotifView]

    def get(self, request: Request, pk: int) -> Response:
        notification = generics.get_object_or_404(_my_notifications(request), pk=pk)
        return Response(NotificationSerializer(notification).data)


class MarkReadView(APIView):
    permission_classes = [NotifUpdate]

    def post(self, request: Request, pk: int) -> Response:
        notification = generics.get_object_or_404(_my_notifications(request), pk=pk)
        return Response(
            NotificationSerializer(services.mark_read(notification)).data
        )


class MarkAllReadView(APIView):
    permission_classes = [NotifUpdate]

    def post(self, request: Request) -> Response:
        updated = services.mark_all_read(request.hotel, request.user)
        return Response({"updated": updated})


class ArchiveView(APIView):
    permission_classes = [NotifUpdate]

    def post(self, request: Request, pk: int) -> Response:
        notification = generics.get_object_or_404(_my_notifications(request), pk=pk)
        return Response(NotificationSerializer(services.archive(notification)).data)


class ActivityListView(generics.ListAPIView):
    permission_classes = [ActivityView]
    serializer_class = ActivityEventSerializer

    def get_queryset(self):
        qs = _visible_activity(self.request).select_related("actor", "target_user")
        p = self.request.query_params
        if p.get("category") in {c for c, _ in ActivityCategory.choices}:
            qs = qs.filter(category=p["category"])
        if p.get("severity") in {c for c, _ in ActivitySeverity.choices}:
            qs = qs.filter(severity=p["severity"])
        if p.get("event_type"):
            qs = qs.filter(event_type=p["event_type"])
        if p.get("actor") and str(p["actor"]).isdigit():
            qs = qs.filter(actor_id=int(p["actor"]))
        if p.get("date"):
            qs = qs.filter(occurred_at__date=p["date"])
        ordering = p.get("ordering")
        if ordering not in ("occurred_at", "-occurred_at"):
            ordering = "-occurred_at"
        return qs.order_by(ordering).distinct()


class ActivityDetailView(APIView):
    permission_classes = [ActivityView]

    def get(self, request: Request, pk: int) -> Response:
        event = generics.get_object_or_404(_visible_activity(request), pk=pk)
        return Response(ActivityEventSerializer(event).data)
