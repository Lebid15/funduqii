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
