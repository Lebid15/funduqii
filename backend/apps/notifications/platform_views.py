"""Platform-owner notification centre (notifications final closure), mounted
under /api/v1/platform/notifications/.

Restricted to the platform owner via ``IsPlatformOwner`` — NO hotel membership,
NO new RBAC permission. Every query is scoped to ``recipient=request.user`` and
``scope=platform`` so a hotel notification can never appear here and a platform
notification can never appear in a hotel console. Read is GET-only; mark-read /
mark-all-read / archive are POST (recipient-state flags). No DELETE.
"""
from __future__ import annotations

from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.rbac.permissions import IsPlatformOwner

from . import services
from .models import ActivityCategory, ActivitySeverity, Notification, NotificationScope
from .serializers import NotificationSerializer
from .views import SEVERITY_RANK


def _my_platform_notifications(request: Request):
    return Notification.objects.filter(
        recipient=request.user, scope=NotificationScope.PLATFORM
    )


class PlatformNotificationsOverviewView(APIView):
    permission_classes = [IsPlatformOwner]

    def get(self, request: Request) -> Response:
        mine = _my_platform_notifications(request)
        active = mine.filter(is_archived=False)
        return Response(
            {
                "unread_count": active.filter(is_read=False).count(),
                "warning_count": active.filter(
                    is_read=False, severity=ActivitySeverity.WARNING
                ).count(),
                "danger_count": active.filter(
                    is_read=False, severity=ActivitySeverity.DANGER
                ).count(),
                "archived_count": mine.filter(is_archived=True).count(),
            }
        )


class PlatformUnreadCountView(APIView):
    permission_classes = [IsPlatformOwner]

    def get(self, request: Request) -> Response:
        return Response(
            {
                "unread": _my_platform_notifications(request)
                .filter(is_read=False, is_archived=False)
                .count()
            }
        )


class PlatformNotificationListView(generics.ListAPIView):
    permission_classes = [IsPlatformOwner]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = _my_platform_notifications(self.request)
        p = self.request.query_params
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
        ordering = p.get("ordering")
        if ordering in ("created_at", "-created_at"):
            return qs.order_by(ordering, "-id")
        return qs.annotate(_sev=SEVERITY_RANK).order_by("_sev", "-created_at", "-id")


class PlatformNotificationDetailView(APIView):
    permission_classes = [IsPlatformOwner]

    def get(self, request: Request, pk: int) -> Response:
        notification = generics.get_object_or_404(
            _my_platform_notifications(request), pk=pk
        )
        return Response(NotificationSerializer(notification).data)


class PlatformMarkReadView(APIView):
    permission_classes = [IsPlatformOwner]

    def post(self, request: Request, pk: int) -> Response:
        notification = generics.get_object_or_404(
            _my_platform_notifications(request), pk=pk
        )
        return Response(
            NotificationSerializer(services.mark_read(notification)).data
        )


class PlatformMarkAllReadView(APIView):
    permission_classes = [IsPlatformOwner]

    def post(self, request: Request) -> Response:
        return Response(
            {"updated": services.mark_all_read_platform(request.user)}
        )


class PlatformArchiveView(APIView):
    permission_classes = [IsPlatformOwner]

    def post(self, request: Request, pk: int) -> Response:
        notification = generics.get_object_or_404(
            _my_platform_notifications(request), pk=pk
        )
        return Response(NotificationSerializer(services.archive(notification)).data)
