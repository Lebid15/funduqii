"""Admin registration for guest extra-services (#4).

HARD RULE — no hard delete anywhere: both models forbid delete (row + bulk) via
``has_delete_permission -> False`` and by removing the ``delete_selected`` bulk
action. The catalog stays EDITABLE so a service can be DEACTIVATED (never
deleted); postings are fully READ-ONLY (an audit record — corrections happen in
finance by voiding the underlying charge)."""
from __future__ import annotations

from django.contrib import admin

from .models import GuestExtraService, GuestServicePosting


class _NoDeleteAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)  # no bulk delete
        return actions


@admin.register(GuestExtraService)
class GuestExtraServiceAdmin(_NoDeleteAdmin):
    """Editable so a service can be DEACTIVATED (``is_active=False``) — never
    deleted."""

    list_display = (
        "name",
        "hotel",
        "category",
        "pricing_mode",
        "unit_price",
        "currency",
        "tax_rate",
        "is_active",
        "display_order",
    )
    list_filter = ("hotel", "category", "pricing_mode", "is_active")
    search_fields = ("name",)
    readonly_fields = ("name_normalized", "created_by", "created_at", "updated_at")


@admin.register(GuestServicePosting)
class GuestServicePostingAdmin(_NoDeleteAdmin):
    """Read-only audit record: never added, edited, or deleted from the admin."""

    list_display = (
        "id",
        "hotel",
        "stay",
        "guest_extra_service",
        "folio_charge",
        "idempotency_key",
        "created_at",
    )
    list_filter = ("hotel",)
    search_fields = ("idempotency_key", "request_fingerprint")
    readonly_fields = (
        "hotel",
        "stay",
        "guest_extra_service",
        "folio_charge",
        "idempotency_key",
        "request_fingerprint",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False
