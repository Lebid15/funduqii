/** Reservation form (RESERVATIONS-FORM-UX-CORRECTION · F1). The 4-step flow is
 * now a full-screen PAGE shell (fixed header/stepper/footer + one min-height:0
 * scroll band) mounted by the `/hotel/reservations/new` and `/[id]/edit` routes,
 * replacing the old modal wizard. */
export {
  ReservationFormShell,
  type ReservationFormMode,
} from "./ReservationFormShell";
export {
  ReservationStepper,
  type ReservationStep,
} from "./ReservationStepper";
export {
  useReservationDraft,
  createInitialDraft,
  createEmptyOccupant,
  composeFullName,
  isMaskedValue,
  totalPersons,
  toCreateBody,
  toImmediateCheckInBody,
  reservationToDraft,
  toUpdateBody,
  type ReservationToDraftExtras,
  type ReservationUpdateOptions,
  type ReservationDraft,
  type GuestDraft,
  type OccupantDraft,
  type CompanionsDraft,
  type CompanionGroupType,
  type PendingDocument,
  type DocumentTarget,
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
