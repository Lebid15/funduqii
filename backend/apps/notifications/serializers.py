"""Serializers for notifications + activity (Phase 14). Read-only shapes —
all writes are recipient-state actions handled by dedicated endpoints."""
from __future__ import annotations

from rest_framework import serializers

from .models import ActivityEvent, Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "notification_number", "scope", "hotel", "category", "severity",
            "title", "message", "related_url", "activity", "is_read", "read_at",
            "is_archived", "archived_at", "created_at",
        ]
        read_only_fields = fields


class ActivityEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(
        source="actor.full_name", read_only=True, default=""
    )
    target_user_name = serializers.CharField(
        source="target_user.full_name", read_only=True, default=""
    )

    class Meta:
        model = ActivityEvent
        fields = [
            "id", "event_number", "event_type", "category", "severity",
            "title", "message", "actor", "actor_name", "target_user",
            "target_user_name", "related_object_type", "related_object_id",
            "related_url", "metadata_json", "occurred_at", "created_at",
        ]
        read_only_fields = fields
