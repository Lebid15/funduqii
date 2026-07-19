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
    case "subscription_inactive":
      return t.subscriptionState.blockedError;
    case "suspension_reason_required":
      return t.hotels.suspendReasonRequired;
    case "invalid_hotel_status_transition":
      return t.hotels.invalidStatusTransition;
    case "trial_already_used":
      return t.subscriptions.errors.trialAlreadyUsed;
    case "conflicting_subscription":
      return t.subscriptions.errors.conflicting;
    case "invalid_subscription_transition":
      return t.subscriptions.errors.invalidTransition;
    case "room_limit_reached":
      return t.subscriptions.errors.roomLimitReached;
    case "staff_limit_reached":
      return t.subscriptions.errors.staffLimitReached;
    case "public_booking_limit_reached":
      return t.subscriptions.errors.publicBookingLimitReached;
    case "duplicate_payment_reference":
      return t.subscriptions.errors.duplicatePaymentReference;
    case "plan_in_use":
      return t.plans.inUseCannotDelete;
    // Subscription change requests (§8.5) — actionable messages instead of the
    // generic 409/400 fallbacks.
    case "subscription_request_conflict":
      return t.subscriptionRequests.errors.conflict;
    case "invalid_subscription_request_transition":
      return t.subscriptionRequests.errors.invalidTransition;
    case "subscription_request_not_allowed":
      return t.subscriptionRequests.errors.notAllowed;
    case "plan_not_available_for_request":
      return t.subscriptionRequests.errors.planNotAvailable;
    case "subscription_request_reason_required":
      return t.subscriptionRequests.errors.reasonRequired;
    case "resource_in_use":
      return t.rooms.errors.inUse;
    case "cross_tenant_reference":
      return t.rooms.errors.crossTenant;
    case "status_note_required":
      return t.rooms.errors.noteRequired;
    case "duplicate_room_number":
      return t.rooms.errors.duplicateRoomNumber;
    case "bulk_request_too_large":
      return t.rooms.errors.bulkTooLarge;
    case "no_availability": {
      // RESERVATIONS-AUTO-ROOM: automatic assignment surfaces the same code with a
      // stable `details.reason` when no specific room could be picked — show a
      // room-selection-aware message instead of the generic dates one.
      const reason =
        error.details && typeof error.details === "object"
          ? (error.details as { reason?: string }).reason
          : undefined;
      return reason === "no_room_available"
        ? t.reservations.errors.noRoomAvailable
        : t.reservations.errors.noAvailability;
    }
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
    case "reservation_line_full":
      return t.frontDesk.errors.lineFull;
    case "arrival_date_in_future":
      return t.frontDesk.errors.arrivalFuture;
    case "invalid_stay_change": {
      // Some stay-change rejections carry a stable `details.reason`; surface the
      // rate-remediation "before check-in" case specifically (the rest stay generic).
      const reason =
        error.details && typeof error.details === "object"
          ? (error.details as { reason?: string }).reason
          : undefined;
      return reason === "rate_remediation_before_check_in"
        ? t.frontDesk.errors.rateBeforeCheckIn
        : t.frontDesk.errors.invalidStayChange;
    }
    case "folio_balance_outstanding":
      return t.frontDesk.errors.folioOutstanding;
    case "early_departure_reason_required":
      return t.frontDesk.errors.earlyReasonRequired;
    // STAYS rate-integrity remediation — distinct, actionable messages instead of
    // the generic 409 conflict line, so the agent knows how to correct the window.
    case "rate_period_overlap":
      return t.frontDesk.errors.rateOverlap;
    case "rate_period_conflict":
      return t.frontDesk.errors.rateConflict;
    case "rate_period_covers_posted_night":
      return t.frontDesk.errors.rateCoversPostedNight;
    case "missing_agreed_nightly_rate":
      return t.frontDesk.errors.missingAgreedRate;
    case "rate_remediation_requires_extension":
      return t.frontDesk.errors.rateRequiresExtension;
    // FIX-1 check-in currency guard (409): the booking's agreed currency cannot be
    // reconciled with the folio/hotel currency (conflicting_line_currencies /
    // missing_line_currency / existing_folio_currency). One operational message —
    // no amounts — covers every reason; check-in is blocked and no folio is created.
    case "folio_currency_mismatch":
      return t.frontDesk.errors.folioCurrencyMismatch;
    case "guest_blocked":
      return t.guests.errors.blocked;
    case "block_reason_required":
      return t.guests.errors.blockReasonRequired;
    // GUESTS-CLOSURE central identity — a reservation create / check-in whose
    // identity collides with a different existing guest (409). Never merged.
    case "guest_identity_conflict":
      return t.guests.errors.identityConflict;
    // GUESTS-CLOSURE public booking — a phone number without a usable country
    // code (400). Actionable guidance instead of the generic validation line.
    case "invalid_phone":
      return t.guests.errors.invalidPhone;
    case "folio_closed":
      return t.finance.errors.folioClosed;
    case "folio_not_balanced":
      return t.finance.errors.folioNotBalanced;
    case "void_reason_required":
      return t.finance.errors.voidReasonRequired;
    case "invalid_finance_operation": {
      // FX/finance failures all arrive under this code with a stable
      // `details.reason`; map the known reasons to a field-specific message so
      // the user learns which input is wrong instead of a generic line.
      const reason =
        error.details && typeof error.details === "object"
          ? (error.details as { reason?: string }).reason
          : undefined;
      switch (reason) {
        case "currency_not_accepted":
          return t.finance.errors.currencyNotAccepted;
        case "exchange_rate_required":
          return t.finance.errors.exchangeRateRequired;
        case "original_amount_required":
          return t.finance.errors.originalAmountRequired;
        case "invalid_exchange_rate":
          return t.finance.errors.invalidExchangeRate;
        case "amount_out_of_range":
          return t.finance.errors.amountOutOfRange;
        case "rate_currency_mismatch":
          return t.finance.errors.rateCurrencyMismatch;
        default:
          return t.finance.errors.invalidOperation;
      }
    }
    case "invalid_amount":
      return t.finance.errors.invalidAmount;
    case "void_window_closed":
      return t.finance.errors.voidWindowClosed;
    case "void_window_open":
      return t.finance.errors.voidWindowOpen;
    case "folio_has_postings":
      return t.finance.errors.folioHasPostings;
    case "charge_already_adjusted":
      return t.finance.errors.chargeAlreadyAdjusted;
    case "payment_already_reversed":
      return t.finance.errors.paymentAlreadyReversed;
    case "expense_already_reversed":
      return t.finance.errors.expenseAlreadyReversed;
    case "reservation_folio_not_supported":
      return t.finance.errors.reservationFolioNotSupported;
    case "active_invoice_exists":
      return t.finance.errors.activeInvoiceExists;
    case "order_already_posted":
      return t.services.errors.alreadyPosted;
    case "order_not_postable":
      return t.services.errors.notPostable;
    case "order_not_editable":
      return t.services.errors.notEditable;
    case "order_items_required":
      return t.services.errors.itemsRequired;
    case "invalid_order_status_transition":
      return t.services.errors.invalidTransition;
    case "service_item_unavailable":
      return t.services.errors.itemUnavailable;
    case "stay_not_in_house":
      return t.services.errors.stayNotInHouse;
    case "outlet_disabled":
      return t.services.errors.outletDisabled;
    case "outlet_mismatch":
      return t.services.errors.outletMismatch;
    case "table_occupied":
      return t.services.errors.tableOccupied;
    case "table_out_of_service":
      return t.services.errors.tableOutOfService;
    case "table_has_open_order":
      return t.services.errors.tableHasOpenOrder;
    case "order_already_settled":
      return t.services.errors.alreadySettled;
    case "last_active_item_not_cancellable":
      return t.services.errors.lastItemNotCancellable;
    case "invalid_order_composition":
      return t.services.errors.invalidComposition;
    case "invalid_operation_status_transition":
      return t.operations.errors.invalidTransition;
    case "operation_not_editable":
      return t.operations.errors.notEditable;
    case "room_blocked_by_maintenance":
      return t.operations.errors.roomBlocked;
    case "room_not_releasable":
      return t.operations.errors.roomNotReleasable;
    case "claimant_required":
      return t.operations.errors.claimantRequired;
    case "claim_proof_required":
      return t.operations.errors.claimProofRequired;
    case "disposal_reason_required":
      return t.operations.errors.disposalReasonRequired;
    case "duplicate_active_task":
      return t.operations.errors.duplicateActive;
    case "inspection_reason_required":
      return t.operations.errors.inspectionReasonRequired;
    case "email_already_registered":
      return t.staff.errors.emailExists;
    case "membership_already_exists":
      return t.staff.errors.membershipExists;
    case "last_manager_protected":
      return t.staff.errors.lastManager;
    case "platform_owner_not_manageable":
      return t.staff.errors.platformOwner;
    case "permission_escalation_blocked":
      return t.staff.errors.escalationBlocked;
    case "manager_permissions_not_editable":
      return t.staff.errors.managerNotEditable;
    case "unknown_permission":
      return t.staff.errors.unknownPermission;
    case "cannot_edit_own_permissions":
      return t.staff.errors.cannotEditOwnPermissions;
    case "self_action_blocked":
      return t.staff.errors.selfActionBlocked;
    case "not_a_manager":
      return t.staff.errors.notAManager;
    case "invalid_membership_type":
      return t.staff.errors.invalidMembershipType;
    case "primary_manager_protected":
      return t.staff.errors.primaryManagerProtected;
    case "staff_has_open_shift":
      return t.staff.errors.staffHasOpenShift;
    case "staff_has_trace":
      return t.staff.errors.staffHasTrace;
    case "cross_tenant_identity":
      return t.staff.errors.crossTenantIdentity;
    case "shift_already_open":
      return t.shifts.errors.alreadyOpen;
    case "shift_not_open":
      return t.shifts.errors.notOpen;
    case "cash_difference_reason_required":
      return t.shifts.errors.differenceReason;
    case "handover_not_recipient":
      return t.shifts.errors.notRecipient;
    case "rejection_reason_required":
      return t.shifts.errors.rejectionReason;
    case "business_day_closed":
      return t.shifts.errors.dayClosed;
    case "day_already_closed":
      return t.shifts.errors.dayAlreadyClosed;
    case "business_date_mismatch":
      return t.shifts.errors.businessDateMismatch;
    case "open_shifts_prevent_close":
      return t.shifts.errors.openShifts;
    case "pending_handovers_prevent_close":
      return t.shifts.errors.pendingHandovers;
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
