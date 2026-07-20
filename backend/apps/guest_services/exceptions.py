"""Domain exceptions for the guest extra-services flow.

They subclass ``apps.common.exceptions.FunduqiiAPIException`` so the project's
unified error envelope (``{"code", "message", "details"?}``) applies unchanged —
without editing the shared central exceptions module. Refusals that already have
a precise shared code (stay-not-in-house, folio-closed, currency-mismatch,
cross-tenant, permission-denied, idempotency-key-conflict, invalid-amount) reuse
the existing exceptions from ``apps.common.exceptions``; only the two genuinely
new guest-service conditions live here.
"""
from __future__ import annotations

from rest_framework import status

from apps.common.exceptions import FunduqiiAPIException


class GuestServiceInactive(FunduqiiAPIException):
    """The requested catalog service is inactive (deactivated) — it can never be
    posted to a folio. ``details.service`` is the neutral id marker."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This guest service is inactive and cannot be added."
    default_code = "guest_service_inactive"


class VariablePriceReasonRequired(FunduqiiAPIException):
    """A variable-price OVERRIDE (a per-posting price that differs from the
    catalog) must carry a reason. Raised when an override is supplied with no
    reason; it never carries the price value itself."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required to override a guest service's price."
    default_code = "variable_price_reason_required"
