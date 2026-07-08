/**
 * Map an API error envelope to a translated, user-facing message.
 *
 * The backend returns stable `code` strings; the UI never shows raw backend
 * text. Unknown codes fall back to a generic translated message.
 */
import type { Dictionary } from "@/lib/i18n/dictionaries";

import type { ApiError } from "./client";

export function isApiError(value: unknown): value is ApiError {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    "status" in value
  );
}

export function messageForError(error: unknown, t: Dictionary): string {
  if (!isApiError(error)) {
    return t.errors.generic;
  }
  switch (error.code) {
    case "invalid_media_file": {
      const reason =
        error.details && typeof error.details === "object"
          ? (error.details as { reason?: string }).reason
          : undefined;
      return reason === "size"
        ? t.hotel.settings.fileSizeError
        : t.hotel.settings.fileTypeError;
    }
    case "media_limit_reached":
      return t.hotel.settings.galleryFullError;
    case "hotel_suspended":
      return t.hotel.settings.readOnlySuspended;
    case "resource_in_use":
      return t.rooms.errors.inUse;
    case "cross_tenant_reference":
      return t.rooms.errors.crossTenant;
    case "status_note_required":
      return t.rooms.errors.noteRequired;
    case "no_availability":
      return t.reservations.errors.noAvailability;
    case "cancellation_reason_required":
      return t.reservations.errors.reasonRequired;
    case "invalid_reservation_transition":
      return t.reservations.errors.invalidTransition;
    case "room_assignment_conflict":
      return t.reservations.errors.roomConflict;
    case "invalid_check_in":
      return t.frontDesk.errors.invalidCheckIn;
    case "invalid_check_out":
      return t.frontDesk.errors.invalidCheckOut;
    case "room_occupied":
      return t.frontDesk.errors.roomOccupied;
    case "room_not_ready":
      return t.frontDesk.errors.roomNotReady;
    case "already_checked_in":
      return t.frontDesk.errors.alreadyCheckedIn;
    case "folio_closed":
      return t.finance.errors.folioClosed;
    case "folio_not_balanced":
      return t.finance.errors.folioNotBalanced;
    case "void_reason_required":
      return t.finance.errors.voidReasonRequired;
    case "invalid_finance_operation":
      return t.finance.errors.invalidOperation;
    case "invalid_amount":
      return t.finance.errors.invalidAmount;
    case "trial_already_used":
      return t.subscriptions.trialAlreadyUsed;
    case "conflicting_subscription":
      return t.subscriptions.conflict;
    case "plan_in_use":
      return t.plans.inUseCannotDelete;
    case "invalid_credentials":
      return t.auth.invalidCredentials;
    case "not_platform_owner":
      return t.auth.forbiddenNotOwner;
    case "permission_denied":
    case "user_inactive":
      return t.errors.forbidden;
    case "session_expired":
      return t.errors.sessionExpired;
    case "not_authenticated":
      return t.errors.sessionExpired;
    case "invalid_request":
    case "validation":
      return t.errors.validation;
    default:
      if (error.status === 404) return t.errors.notFound;
      if (error.status === 409) return t.errors.conflict;
      if (error.status >= 500) return t.errors.generic;
      return error.message || t.errors.generic;
  }
}
