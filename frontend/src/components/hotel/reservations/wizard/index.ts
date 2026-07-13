/** Reservation wizard (RESERVATIONS-FORM-REWORK). Wave 2a ships the shell +
 * shared draft + Guest and Companions steps; Wave 2b fills Documents + Booking
 * and mounts this in place of the legacy inline form. */
export { ReservationWizard } from "./ReservationWizard";
export {
  useReservationDraft,
  createInitialDraft,
  createEmptyOccupant,
  composeFullName,
  isMaskedValue,
  totalPersons,
  toCreateBody,
  toImmediateCheckInBody,
  type ReservationDraft,
  type GuestDraft,
  type OccupantDraft,
  type CompanionsDraft,
  type PendingDocument,
  type PaymentDraft,
  type BookingDraft,
  type BookingLineDraft,
  type ReservationDraftActions,
  type UseReservationDraft,
} from "./useReservationDraft";
export {
  useGuestLookup,
  type GuestLookupState,
  type GuestLookupStatus,
} from "./useGuestLookup";
export { GuestStep } from "./GuestStep";
export { CompanionsStep } from "./CompanionsStep";
export { DocumentsStep } from "./DocumentsStep";
export { BookingStep } from "./BookingStep";
