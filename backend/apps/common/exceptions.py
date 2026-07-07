"""
Unified error layer for the Funduqii API.

Every API error is returned as a stable, translatable envelope::

    {"code": "permission_denied", "message": "...", "details": {...}?}

The ``code`` is a machine-stable string the frontend can map to a translated
message later (Phase 2 does not build a full backend translation system).
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException


class FunduqiiAPIException(APIException):
    """Base class for domain exceptions carrying a stable ``default_code``."""


class UserInactive(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "This account is inactive."
    default_code = "user_inactive"


class HotelContextRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A hotel context (X-Hotel-ID header) is required for this request."
    default_code = "hotel_context_required"


class HotelNotFound(FunduqiiAPIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "The requested hotel does not exist."
    default_code = "hotel_not_found"


class NoHotelMembership(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You are not a member of this hotel."
    default_code = "no_hotel_membership"


class MembershipInactive(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Your membership in this hotel is inactive."
    default_code = "membership_inactive"


class HotelAccessDenied(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You cannot access another hotel's data."
    default_code = "hotel_access_denied"


class PermissionDenied(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have permission to perform this action."
    default_code = "permission_denied"


class UnknownPermission(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Unknown permission code."
    default_code = "unknown_permission"


# --- Subscriptions / platform (Phase 3) ------------------------------------


class TrialAlreadyUsed(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This hotel has already used its one-time free trial."
    default_code = "trial_already_used"


class ConflictingSubscription(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This hotel already has an active subscription."
    default_code = "conflicting_subscription"


class PlanInUse(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This plan is in use by one or more hotels and cannot be deleted."
    default_code = "plan_in_use"


class InvalidSubscriptionTransition(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This subscription status change is not allowed."
    default_code = "invalid_subscription_transition"


# --- Hotel settings & media (Phase 4) --------------------------------------


class HotelSuspended(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "This hotel is suspended; settings are read-only."
    default_code = "hotel_suspended"


class InvalidMediaFile(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The uploaded file is not a valid image."
    default_code = "invalid_media_file"


class MediaLimitReached(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The maximum number of gallery images has been reached."
    default_code = "media_limit_reached"


# --- Floors / room types / rooms (Phase 5) ---------------------------------


class ResourceInUse(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This item is in use and cannot be deleted; deactivate it instead."
    default_code = "resource_in_use"


class CrossTenantReference(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The referenced item belongs to a different hotel."
    default_code = "cross_tenant_reference"


class StatusNoteRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A note is required for this status change."
    default_code = "status_note_required"


# --- Reservations & availability (Phase 6) ---------------------------------


class NoAvailability(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Not enough rooms are available for the selected dates."
    default_code = "no_availability"


class InvalidReservationTransition(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This reservation status change is not allowed."
    default_code = "invalid_reservation_transition"


class CancellationReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A cancellation reason is required."
    default_code = "cancellation_reason_required"


def _extract_code(exc) -> str:
    """Prefer the specific ErrorDetail code (e.g. simplejwt's), then fall back."""
    detail = getattr(exc, "detail", None)
    code = getattr(detail, "code", None)
    if isinstance(code, str):
        return code
    return getattr(exc, "default_code", None) or "error"


def _flatten_message(detail) -> str:
    if detail is None:
        return "An error occurred."
    if isinstance(detail, str):
        return str(detail)
    if isinstance(detail, list) and detail:
        return _flatten_message(detail[0])
    if isinstance(detail, dict) and detail:
        return _flatten_message(next(iter(detail.values())))
    return str(detail)


def funduqii_exception_handler(exc, context):
    """Wrap DRF's default handler to emit the unified error envelope."""
    # Imported lazily: rest_framework.views triggers DRF settings resolution
    # (DEFAULT_PERMISSION_CLASSES -> this module), so a top-level import would
    # create a circular import at startup.
    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = getattr(exc, "detail", None)
    payload = {"code": _extract_code(exc), "message": _flatten_message(detail)}
    if isinstance(detail, (list, dict)):
        payload["details"] = detail

    response.data = payload
    return response
