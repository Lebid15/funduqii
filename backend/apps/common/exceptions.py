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


# --- Rooms bulk / central create (ROOMS-REWORK-01) --------------------------


class DuplicateRoomNumber(FunduqiiAPIException):
    """One or more room numbers collide. ``details`` carries ``source`` —
    ``"request"`` (duplicated within the same bulk request) or ``"existing"``
    (already used in the hotel, including a concurrent-insert race) — and the
    list of offending ``numbers``."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "One or more room numbers are already in use or duplicated."
    default_code = "duplicate_room_number"


class BulkRequestTooLarge(FunduqiiAPIException):
    """A bulk room create exceeds the hard per-request cap (``MAX_BULK_ROOMS``).
    ``details`` carries the ``limit`` and the ``requested`` count."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Too many rooms were requested in a single bulk create."
    default_code = "bulk_request_too_large"


# --- Service orders (Phase 9) -----------------------------------------------


class OrderAlreadyPosted(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This order has already been posted to a folio."
    default_code = "order_already_posted"


class OrderNotPostable(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This order cannot be posted to a folio."
    default_code = "order_not_postable"


class OrderNotEditable(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This order can no longer be modified."
    default_code = "order_not_editable"


class OrderItemsRequired(FunduqiiAPIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The order must contain at least one item."
    default_code = "order_items_required"


class InvalidOrderStatusTransition(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This order status change is not allowed."
    default_code = "invalid_order_status_transition"


class ServiceItemUnavailable(FunduqiiAPIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "This service item is inactive or unavailable."
    default_code = "service_item_unavailable"


# --- Operations: housekeeping / maintenance / lost & found (Phase 10) -------


class InvalidOperationStatusTransition(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This operational status change is not allowed."
    default_code = "invalid_operation_status_transition"


class OperationNotEditable(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This record can no longer be modified."
    default_code = "operation_not_editable"


class RoomBlockedByMaintenance(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This room is blocked by maintenance and cannot be made available."
    default_code = "room_blocked_by_maintenance"


class ClaimantRequired(FunduqiiAPIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "A claimant name (or linked guest) is required."
    default_code = "claimant_required"


class DisposalReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required to dispose of this item."
    default_code = "disposal_reason_required"


# --- Staff & permissions management (Phase 11) ------------------------------


class EmailAlreadyRegistered(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A user with this email already exists."
    default_code = "email_already_registered"


class MembershipAlreadyExists(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This user is already a member of this hotel."
    default_code = "membership_already_exists"


class LastManagerProtected(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The hotel's last active manager cannot be deactivated."
    default_code = "last_manager_protected"


class PlatformOwnerNotManageable(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A platform owner account cannot be managed as hotel staff."
    default_code = "platform_owner_not_manageable"


class PermissionEscalationBlocked(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You cannot grant a permission you do not hold yourself."
    default_code = "permission_escalation_blocked"


class ManagerPermissionsNotEditable(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A manager already holds every hotel permission; grants are not editable."
    default_code = "manager_permissions_not_editable"


# --- Staff & employees (final closure round) ---------------------------------


class CannotEditOwnPermissions(FunduqiiAPIException):
    """A user may never change the permission grants of their own membership —
    add, remove, replace, or re-send the same set (no self-service access)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You cannot edit the permissions of your own membership."
    default_code = "cannot_edit_own_permissions"


class SelfActionBlocked(FunduqiiAPIException):
    """Deactivate / promote / demote / delete / change-email against oneself
    is refused (no self-management of sensitive lifecycle actions)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You cannot perform this action on your own account."
    default_code = "self_action_blocked"


class NotAManager(FunduqiiAPIException):
    """Manager-only lifecycle actions (promote/demote) require the ACTOR to be
    a real manager — holding the task permission alone is not enough."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Only a manager can manage manager memberships."
    default_code = "not_a_manager"


class InvalidMembershipType(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The membership is not of the expected type for this action."
    default_code = "invalid_membership_type"


class PrimaryManagerProtected(FunduqiiAPIException):
    """The hotel's primary manager cannot be deactivated, demoted, or deleted
    through staff management — ownership moves have their own path."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The hotel's primary manager cannot be changed here."
    default_code = "primary_manager_protected"


class StaffHasOpenShift(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Close the employee's open shift before deactivating them."
    default_code = "staff_has_open_shift"


class StaffHasTrace(FunduqiiAPIException):
    """A membership/user with any operational, financial, or security trace can
    never be deleted — deactivation is the only path (history is preserved)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This account has operational history and cannot be deleted; "
        "deactivate it instead."
    )
    default_code = "staff_has_trace"


class CrossTenantIdentity(FunduqiiAPIException):
    """The user's email is a global login identity shared beyond this hotel;
    a single-hotel manager may not change it here."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This user's identity spans more than one tenant; change the email "
        "from central identity management."
    )
    default_code = "cross_tenant_identity"


# --- Shifts / handover / daily close (Phase 12) ------------------------------


class ShiftAlreadyOpen(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This user already has an open shift in this hotel."
    default_code = "shift_already_open"


class ShiftNotOpen(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This operation requires an open shift."
    default_code = "shift_not_open"


class CashDifferenceReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required when the counted cash differs from the expected amount."
    default_code = "cash_difference_reason_required"


class HandoverNotRecipient(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Only the designated recipient (or a manager) can act on this handover."
    default_code = "handover_not_recipient"


class RejectionReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required to reject this handover."
    default_code = "rejection_reason_required"


class BusinessDayClosed(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This business date has been closed; new dated activity is not allowed."
    default_code = "business_day_closed"


class DayAlreadyClosed(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This business date is already closed."
    default_code = "day_already_closed"


class OpenShiftsPreventClose(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The day cannot be closed while shifts for this date are still open."
    default_code = "open_shifts_prevent_close"


class PendingHandoversPreventClose(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The day cannot be closed while submitted handovers are unresolved."
    default_code = "pending_handovers_prevent_close"


class BusinessDateMismatch(FunduqiiAPIException):
    """The daily close targets a date that is not the hotel's current stored
    business date — a past date (already rolled) or a future one. Closing is
    only ever allowed for the current open business date."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested date is not the hotel's current business date."
    default_code = "business_date_mismatch"


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


class ReservationHasActiveStay(FunduqiiAPIException):
    """Post-check-in guard (reservations final closure): once the reservation has
    produced ANY stay — in-house OR already checked-out — the STAY is the source
    of truth, so the reservation's dates, rooms, existence (cancel) and new
    deposits must not be changed from the reservations section."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This reservation already has a stay (in-house or checked out). Operate"
        " on the stay from the front desk instead."
    )
    default_code = "reservation_has_active_stay"


# --- Room assignment (Phase 6.1) -------------------------------------------


class RoomAssignmentConflict(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This room is already assigned for the selected dates."
    default_code = "room_assignment_conflict"


# --- Guests, check-in & check-out (Phase 7) --------------------------------


class InvalidCheckIn(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This reservation cannot be checked in."
    default_code = "invalid_check_in"


class InvalidCheckOut(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This stay cannot be checked out."
    default_code = "invalid_check_out"


class RoomOccupied(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This room is already occupied by an in-house stay."
    default_code = "room_occupied"


class RoomNotReady(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This room is not ready for check-in."
    default_code = "room_not_ready"


class AlreadyCheckedIn(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This reservation room has already been checked in."
    default_code = "already_checked_in"


# --- Front desk / stays (final closure round) -------------------------------


class ReservationLineFull(FunduqiiAPIException):
    """Quantity cap: a reservation line may never admit more stays than its
    booked quantity (cancelled stays don't count)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Every booked room of this reservation has already been checked in."
    )
    default_code = "reservation_line_full"


class ArrivalDateInFuture(FunduqiiAPIException):
    """Check-in may not happen before the reservation's arrival date, measured
    by the HOTEL's business date (never the server clock)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This reservation's arrival date has not been reached yet."
    )
    default_code = "arrival_date_in_future"


class InvalidStayChange(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This stay change is not allowed."
    default_code = "invalid_stay_change"


class FolioBalanceOutstanding(FunduqiiAPIException):
    """Check-out is blocked while the stay's open folio holds a non-zero
    balance — settlement happens in Finance, never at the front desk."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This stay's folio has an unsettled balance. Settle it in Finance "
        "before check-out."
    )
    default_code = "folio_balance_outstanding"


class FolioAwaitingFinalCharges(FunduqiiAPIException):
    """Check-out is blocked while reception is still confirming the stay's final
    charges (STAYS-ARRIVALS-DEPARTURES §32) — the folio must not close until the
    final charges (restaurant / services / minibar / damages) are confirmed."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This stay's folio is awaiting final charges. Confirm the final charges "
        "before check-out."
    )
    default_code = "folio_awaiting_final_charges"


class EarlyDepartureReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required for an early departure."
    default_code = "early_departure_reason_required"


# --- Guests (final closure round) --------------------------------------------


class GuestBlocked(FunduqiiAPIException):
    """A guest blocked in THIS hotel cannot receive new reservations or
    check-ins. The block reason is never included here — it is only visible
    to holders of the block permission on the guest profile."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This guest is blocked in this hotel."
    default_code = "guest_blocked"


class BlockReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required to block a guest."
    default_code = "block_reason_required"


# --- Housekeeping (final closure round) ---------------------------------------


class DuplicateActiveTask(FunduqiiAPIException):
    """A room may hold at most ONE active housekeeping task at a time."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This room already has an active housekeeping task."
    default_code = "duplicate_active_task"


class InspectionReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required to reject an inspection."
    default_code = "inspection_reason_required"


# --- Finance (Phase 8) ------------------------------------------------------


class FolioClosed(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This folio is closed or voided and cannot be modified."
    default_code = "folio_closed"


class FolioNotBalanced(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A folio can only be closed when its balance is zero."
    default_code = "folio_not_balanced"


class VoidReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required to void this record."
    default_code = "void_reason_required"


class InvalidFinanceOperation(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This financial operation is not allowed."
    default_code = "invalid_finance_operation"


class InvalidAmount(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The amount is not valid."
    default_code = "invalid_amount"


# --- Finance (folio final closure round) --------------------------------------


class VoidWindowClosed(FunduqiiAPIException):
    """Void is only allowed on the record's own OPEN business date. Once that
    day has passed or was closed, the correction is an adjustment/reversal."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "The void window for this record has closed; post an adjustment or "
        "a payment reversal instead."
    )
    default_code = "void_window_closed"


class VoidWindowOpen(FunduqiiAPIException):
    """Adjustments/reversals are for records whose void window has PASSED —
    same-day corrections must use void so the two paths never overlap."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This record can still be voided; use void instead."
    default_code = "void_window_open"


class FolioHasPostings(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "A folio with any charge, payment, or invoice cannot be voided; "
        "settle and close it instead."
    )
    default_code = "folio_has_postings"


class ChargeAlreadyAdjusted(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This charge already has a posted adjustment."
    default_code = "charge_already_adjusted"


class PaymentAlreadyReversed(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This payment already has a posted reversal."
    default_code = "payment_already_reversed"


class ReservationFolioNotSupported(FunduqiiAPIException):
    """Pre-arrival (reservation-only) folios are not supported: nothing links
    them to the stay at check-in and the check-out gate never sees them. A
    reservation may only be referenced on a folio together with its stay."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A folio cannot be linked to a reservation without a stay."
    default_code = "reservation_folio_not_supported"


class ActiveInvoiceExists(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This folio already has an issued invoice; void it before issuing "
        "a new one."
    )
    default_code = "active_invoice_exists"


# --- Restaurant & café (final closure round) ----------------------------------


class StayNotInHouse(FunduqiiAPIException):
    """New operational-financial relations (orders, folio posting, new stay
    folios) require the stay to still be IN-HOUSE. Reading, printing, and
    corrections on EXISTING records are never gated by this."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The stay is not in-house."
    default_code = "stay_not_in_house"


class OutletDisabled(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This outlet is disabled in the hotel settings."
    default_code = "outlet_disabled"


class OutletMismatch(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The item does not belong to the order's outlet."
    default_code = "outlet_mismatch"


class TableOccupied(FunduqiiAPIException):
    """One OPEN (unsettled, non-cancelled) order per table."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This table already has an open order."
    default_code = "table_occupied"


class TableOutOfService(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This table is out of service."
    default_code = "table_out_of_service"


class TableHasOpenOrder(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A table with an open order cannot leave service."
    default_code = "table_has_open_order"


class OrderAlreadySettled(FunduqiiAPIException):
    """XOR: an order is settled exactly once — direct payment or folio
    posting, never both, never twice, never re-settled."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This order is already settled."
    default_code = "order_already_settled"


class InvalidOrderComposition(FunduqiiAPIException):
    """The order's shape is wrong for its type: a ROOM order needs an
    in-house stay and no table; a TABLE order needs a matching, available
    table of the same outlet."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The order composition is not valid for its type."
    default_code = "invalid_order_composition"


class ExpenseAlreadyReversed(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This expense already has a posted reversal."
    default_code = "expense_already_reversed"


class LastActiveItemNotCancellable(FunduqiiAPIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "The last active item cannot be cancelled; cancel the whole order "
        "instead."
    )
    default_code = "last_active_item_not_cancellable"


# --- Platform owner panel / subscription enforcement (Phase 16) -------------


class SubscriptionInactive(FunduqiiAPIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = (
        "This hotel has no active subscription; important operations are "
        "restricted until the platform owner activates one."
    )
    default_code = "subscription_inactive"


class SuspensionReasonRequired(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A reason is required to suspend a hotel."
    default_code = "suspension_reason_required"


class InvalidHotelStatusTransition(FunduqiiAPIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This hotel status change is not allowed."
    default_code = "invalid_hotel_status_transition"


# --- Subscription entitlements / limits (subscriptions final closure) --------


class RoomLimitReached(FunduqiiAPIException):
    """The hotel's plan room limit is reached. Existing rooms are grandfathered
    (never deleted or disabled); no NEW room may be created until usage drops
    below the limit or the plan is upgraded."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This hotel has reached the room limit of its subscription plan; "
        "existing rooms are kept, but new rooms cannot be created."
    )
    default_code = "room_limit_reached"


class StaffLimitReached(FunduqiiAPIException):
    """The hotel's plan staff (user) limit is reached. Existing staff are
    grandfathered; no NEW staff may be created until usage drops below the
    limit or the plan is upgraded."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This hotel has reached the staff limit of its subscription plan; "
        "existing staff are kept, but new staff cannot be created."
    )
    default_code = "staff_limit_reached"


class PublicBookingLimitReached(FunduqiiAPIException):
    """The hotel's monthly public-booking allowance is reached. Existing
    bookings are untouched; new PUBLIC bookings are refused for this month."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This hotel has reached its monthly public-booking limit; existing "
        "bookings are kept, but new public bookings cannot be created now."
    )
    default_code = "public_booking_limit_reached"


class DuplicatePaymentReference(FunduqiiAPIException):
    """A manual subscription payment reference is unique per hotel among
    non-voided payments (enforced only when a reference is supplied)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "A payment with this reference already exists for this hotel."
    default_code = "duplicate_payment_reference"


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
