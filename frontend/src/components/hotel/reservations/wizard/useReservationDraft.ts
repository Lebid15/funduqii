"use client";

/**
 * Shared draft state for the reservation wizard (RESERVATIONS-FORM-REWORK,
 * Wave 2a). ONE reducer models ALL FOUR steps — Guest, Companions, Documents
 * and Booking — so later waves extend the shape without a refactor:
 *   - Wave 2a implements Guest + Companions (this file's builders map that
 *     portion into the API bodies).
 *   - Wave 2b implements the Documents upload + the Booking/payment UI and
 *     fills the remaining builder branches.
 *
 * The backend stays the single source of truth for availability, capacity,
 * pricing, masking and blocking — nothing here decides those.
 */
import { useMemo, useReducer } from "react";

import type {
  ImmediateCheckInBody,
  ReservationCreateBody,
  ReservationLineBody,
  ReservationOccupantBody,
} from "@/lib/api/reservations";
import type {
  ExpectedPaymentMethod,
  Guest,
  OccupantRelationship,
  ReservationDepositMethod,
  ReservationDocumentType,
  ReservationSource,
} from "@/lib/api/types";

/* -------------------------------------------------------------------------- */
/* Draft shape                                                                */
/* -------------------------------------------------------------------------- */

/** Step 1 — the primary guest. `primary_guest_id` links to the central guest
 * directory when matched via lookup; `national_id_masked` records that the
 * looked-up id came back masked (the user lacks `guests.view_sensitive_data`),
 * so we never round-trip the mask back to the server. `is_blocked` mirrors a
 * linked guest's block state and gates proceeding. */
export interface GuestDraft {
  primary_guest_id: number | null;
  national_id: string;
  national_id_masked: boolean;
  first_name: string;
  last_name: string;
  father_name: string;
  mother_name: string;
  nationality: string;
  date_of_birth: string;
  phone: string;
  email: string;
  no_email: boolean;
  /** Composed from first + father + last while untouched; editable afterwards. */
  full_name: string;
  full_name_touched: boolean;
  is_blocked: boolean;
}

/** One ADULT companion row (step 2). Children stay a plain count. */
export interface OccupantDraft {
  /** Stable local key for React lists (never sent to the server). */
  key: string;
  guest_id: number | null;
  first_name: string;
  last_name: string;
  father_name: string;
  mother_name: string;
  national_id: string;
  national_id_masked: boolean;
  nationality: string;
  date_of_birth: string;
  relationship: OccupantRelationship | "";
}

export interface CompanionsDraft {
  has_companions: boolean;
  occupants: OccupantDraft[];
  /** Count only — no per-child fields are collected. */
  children: number;
}

/** Step 3 (Wave 2b) — a document staged in the UI. Files upload AFTER the
 * reservation is created (the upload needs the reservation id). Defined now;
 * the upload handling lands in Wave 2b. `occupantKey` links to an
 * `OccupantDraft.key` (or null for the primary guest). */
export interface PendingDocument {
  key: string;
  doc_type: ReservationDocumentType;
  number: string;
  occupantKey: string | null;
  front_file: File | null;
  back_file: File | null;
}

/** Step 4 (Wave 2b) — the payment/deposit sub-draft. Money fields are decimal
 * STRINGS (never `parseFloat`). FX (`original_amount`/`exchange_rate`/
 * `rate_basis`) is a Wave 2b concern; the shape is defined now. */
export interface PaymentDraft {
  method: ReservationDepositMethod | "";
  currency: string;
  amount: string;
  original_amount: string;
  exchange_rate: string;
  rate_basis: string;
}

/** One booked room line (step 4). Kept as strings for form controls. */
export interface BookingLineDraft {
  room_type: string;
  room: string;
  quantity: string;
}

/** Step 4 (Wave 2b) — dates, rooms, payment and the immediate-check-in flag. */
export interface BookingDraft {
  check_in_date: string;
  check_out_date: string;
  expected_arrival_time: string;
  lines: BookingLineDraft[];
  /** The physical room chosen from the availability picker (immediate flow). */
  selected_room_id: number | null;
  source: ReservationSource;
  status: "held" | "confirmed";
  /** Informational only (future reservations): the method the guest expects to
   * pay with. Constrained to the backend `ExpectedPaymentMethod` choices — NOT
   * the deposit `payment.method` — and persisted via `toCreateBody`. Empty means
   * "not specified" and is omitted from the create body. */
  expected_payment_method: ExpectedPaymentMethod;
  payment: PaymentDraft;
  /** When on, submit atomically creates + checks in via `immediateCheckIn`. */
  immediate_check_in: boolean;
}

export interface ReservationDraft {
  guest: GuestDraft;
  companions: CompanionsDraft;
  pendingDocuments: PendingDocument[];
  booking: BookingDraft;
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

let keyCounter = 0;
function uid(prefix: string): string {
  keyCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${keyCounter.toString(36)}`;
}

/** The backend masks sensitive ids with bullet characters (matches the guests
 * panel convention). A masked value must never be written back. */
export function isMaskedValue(value: string | undefined | null): boolean {
  return Boolean(value && value.includes("•"));
}

/** Compose the display name from the structured name parts. */
export function composeFullName(
  first: string,
  father: string,
  last: string,
): string {
  return [first, father, last]
    .map((part) => part.trim())
    .filter(Boolean)
    .join(" ");
}

export function createEmptyOccupant(): OccupantDraft {
  return {
    key: uid("occ"),
    guest_id: null,
    first_name: "",
    last_name: "",
    father_name: "",
    mother_name: "",
    national_id: "",
    national_id_masked: false,
    nationality: "",
    date_of_birth: "",
    relationship: "",
  };
}

export function createInitialDraft(
  overrides?: Partial<ReservationDraft>,
): ReservationDraft {
  return {
    guest: {
      primary_guest_id: null,
      national_id: "",
      national_id_masked: false,
      first_name: "",
      last_name: "",
      father_name: "",
      mother_name: "",
      nationality: "",
      date_of_birth: "",
      phone: "",
      email: "",
      no_email: false,
      full_name: "",
      full_name_touched: false,
      is_blocked: false,
    },
    companions: {
      has_companions: false,
      occupants: [],
      children: 0,
    },
    pendingDocuments: [],
    booking: {
      check_in_date: "",
      check_out_date: "",
      expected_arrival_time: "",
      lines: [{ room_type: "", room: "", quantity: "1" }],
      selected_room_id: null,
      source: "direct",
      status: "confirmed",
      expected_payment_method: "",
      payment: {
        method: "",
        currency: "",
        amount: "",
        original_amount: "",
        exchange_rate: "",
        rate_basis: "",
      },
      immediate_check_in: false,
    },
    ...overrides,
  };
}

/** 1 primary + named adult companions + children. */
export function totalPersons(draft: ReservationDraft): number {
  const companions = draft.companions.has_companions
    ? draft.companions.occupants.length
    : 0;
  const children = draft.companions.has_companions
    ? draft.companions.children
    : 0;
  return 1 + companions + Math.max(0, children);
}

/* -------------------------------------------------------------------------- */
/* Reducer                                                                    */
/* -------------------------------------------------------------------------- */

type GuestTextField =
  | "national_id"
  | "first_name"
  | "last_name"
  | "father_name"
  | "mother_name"
  | "nationality"
  | "date_of_birth"
  | "phone"
  | "email";

type OccupantTextField =
  | "first_name"
  | "last_name"
  | "father_name"
  | "mother_name"
  | "national_id"
  | "nationality"
  | "date_of_birth";

type Action =
  | { type: "reset"; draft: ReservationDraft }
  | { type: "guest/set"; field: GuestTextField; value: string }
  | { type: "guest/setFullName"; value: string }
  | { type: "guest/setNoEmail"; value: boolean }
  | { type: "guest/applyMatch"; guest: Guest }
  | { type: "guest/unlink" }
  | { type: "companions/setHas"; value: boolean }
  | { type: "companions/addOccupant" }
  | { type: "companions/removeOccupant"; key: string }
  | {
      type: "companions/setOccupantField";
      key: string;
      field: OccupantTextField;
      value: string;
    }
  | {
      type: "companions/setOccupantRelationship";
      key: string;
      value: OccupantRelationship | "";
    }
  | { type: "companions/applyOccupantMatch"; key: string; guest: Guest }
  | { type: "companions/unlinkOccupant"; key: string }
  | { type: "companions/setChildren"; value: number }
  | { type: "booking/patch"; patch: Partial<BookingDraft> }
  | { type: "booking/patchPayment"; patch: Partial<PaymentDraft> }
  | { type: "documents/set"; documents: PendingDocument[] };

const NAME_FIELDS: ReadonlySet<GuestTextField> = new Set([
  "first_name",
  "father_name",
  "last_name",
]);

function recomposeGuest(guest: GuestDraft): GuestDraft {
  if (guest.full_name_touched) return guest;
  return {
    ...guest,
    full_name: composeFullName(
      guest.first_name,
      guest.father_name,
      guest.last_name,
    ),
  };
}

function mapOccupant(
  occupants: OccupantDraft[],
  key: string,
  map: (occupant: OccupantDraft) => OccupantDraft,
): OccupantDraft[] {
  return occupants.map((occupant) =>
    occupant.key === key ? map(occupant) : occupant,
  );
}

function reducer(state: ReservationDraft, action: Action): ReservationDraft {
  switch (action.type) {
    case "reset":
      return action.draft;

    case "guest/set": {
      const guest: GuestDraft = { ...state.guest, [action.field]: action.value };
      // A manual national_id edit means the field is no longer the masked
      // server value, and it detaches the row from any auto-filled state.
      if (action.field === "national_id") guest.national_id_masked = false;
      const next = NAME_FIELDS.has(action.field) ? recomposeGuest(guest) : guest;
      return { ...state, guest: next };
    }

    case "guest/setFullName":
      return {
        ...state,
        guest: {
          ...state.guest,
          full_name: action.value,
          full_name_touched: true,
        },
      };

    case "guest/setNoEmail":
      return {
        ...state,
        guest: {
          ...state.guest,
          no_email: action.value,
          email: action.value ? "" : state.guest.email,
        },
      };

    case "guest/applyMatch": {
      const g = action.guest;
      const masked = isMaskedValue(g.national_id);
      const next: GuestDraft = {
        ...state.guest,
        primary_guest_id: g.id,
        first_name: g.first_name ?? "",
        last_name: g.last_name ?? "",
        father_name: g.father_name ?? "",
        mother_name: g.mother_name ?? "",
        nationality: g.nationality ?? "",
        date_of_birth: g.date_of_birth ?? "",
        phone: g.phone ?? "",
        email: g.no_email ? "" : g.email ?? "",
        no_email: Boolean(g.no_email),
        // Never overwrite with a masked id; keep whatever the user typed.
        national_id: masked ? state.guest.national_id : g.national_id ?? "",
        national_id_masked: masked,
        is_blocked: Boolean(g.is_blocked),
        full_name_touched: true,
        full_name: g.full_name || state.guest.full_name,
      };
      return { ...state, guest: next };
    }

    case "guest/unlink":
      return {
        ...state,
        guest: {
          ...state.guest,
          primary_guest_id: null,
          is_blocked: false,
          national_id_masked: false,
        },
      };

    case "companions/setHas":
      return {
        ...state,
        companions: {
          ...state.companions,
          has_companions: action.value,
          // First enable seeds one editable row for convenience.
          occupants:
            action.value && state.companions.occupants.length === 0
              ? [createEmptyOccupant()]
              : state.companions.occupants,
        },
      };

    case "companions/addOccupant":
      return {
        ...state,
        companions: {
          ...state.companions,
          occupants: [...state.companions.occupants, createEmptyOccupant()],
        },
      };

    case "companions/removeOccupant":
      return {
        ...state,
        companions: {
          ...state.companions,
          occupants: state.companions.occupants.filter(
            (occupant) => occupant.key !== action.key,
          ),
        },
      };

    case "companions/setOccupantField":
      return {
        ...state,
        companions: {
          ...state.companions,
          occupants: mapOccupant(
            state.companions.occupants,
            action.key,
            (occupant) => ({
              ...occupant,
              [action.field]: action.value,
              ...(action.field === "national_id"
                ? { national_id_masked: false }
                : {}),
            }),
          ),
        },
      };

    case "companions/setOccupantRelationship":
      return {
        ...state,
        companions: {
          ...state.companions,
          occupants: mapOccupant(
            state.companions.occupants,
            action.key,
            (occupant) => ({ ...occupant, relationship: action.value }),
          ),
        },
      };

    case "companions/applyOccupantMatch": {
      const g = action.guest;
      const masked = isMaskedValue(g.national_id);
      return {
        ...state,
        companions: {
          ...state.companions,
          occupants: mapOccupant(
            state.companions.occupants,
            action.key,
            (occupant) => ({
              ...occupant,
              guest_id: g.id,
              first_name: g.first_name ?? "",
              last_name: g.last_name ?? "",
              father_name: g.father_name ?? "",
              mother_name: g.mother_name ?? "",
              nationality: g.nationality ?? "",
              date_of_birth: g.date_of_birth ?? "",
              national_id: masked ? occupant.national_id : g.national_id ?? "",
              national_id_masked: masked,
            }),
          ),
        },
      };
    }

    case "companions/unlinkOccupant":
      return {
        ...state,
        companions: {
          ...state.companions,
          occupants: mapOccupant(
            state.companions.occupants,
            action.key,
            (occupant) => ({
              ...occupant,
              guest_id: null,
              national_id_masked: false,
            }),
          ),
        },
      };

    case "companions/setChildren":
      return {
        ...state,
        companions: {
          ...state.companions,
          children: Number.isFinite(action.value)
            ? Math.max(0, Math.trunc(action.value))
            : 0,
        },
      };

    case "booking/patch":
      return { ...state, booking: { ...state.booking, ...action.patch } };

    case "booking/patchPayment":
      return {
        ...state,
        booking: {
          ...state.booking,
          payment: { ...state.booking.payment, ...action.patch },
        },
      };

    case "documents/set":
      return { ...state, pendingDocuments: action.documents };

    default:
      return state;
  }
}

/* -------------------------------------------------------------------------- */
/* Body builders                                                              */
/* -------------------------------------------------------------------------- */

/** Map the booking-line drafts into API line bodies. A pinned room forces
 * quantity 1; empty rows are dropped. */
function buildLines(draft: ReservationDraft): ReservationLineBody[] {
  return draft.booking.lines
    .filter((line) => line.room_type)
    .map((line) => ({
      room_type: Number(line.room_type),
      room: line.room ? Number(line.room) : null,
      quantity: line.room ? 1 : Number(line.quantity) || 1,
    }));
}

function buildOccupants(draft: ReservationDraft): ReservationOccupantBody[] {
  if (!draft.companions.has_companions) return [];
  return draft.companions.occupants
    .filter(
      (occupant) =>
        occupant.guest_id !== null ||
        occupant.first_name.trim() !== "" ||
        occupant.last_name.trim() !== "",
    )
    .map((occupant) => ({
      guest: occupant.guest_id,
      first_name: occupant.first_name.trim() || undefined,
      last_name: occupant.last_name.trim() || undefined,
      father_name: occupant.father_name.trim() || undefined,
      mother_name: occupant.mother_name.trim() || undefined,
      // A masked id must never round-trip.
      national_id: occupant.national_id_masked
        ? undefined
        : occupant.national_id.trim() || undefined,
      nationality: occupant.nationality.trim() || undefined,
      date_of_birth: occupant.date_of_birth || null,
      relationship: (occupant.relationship || "other") as OccupantRelationship,
    }));
}

/**
 * Build the reservation create body from the draft. Wave 2a implements the
 * guest + occupants portion fully; booking fields are mapped straight from the
 * (Wave 2b) booking sub-draft, so they flow through automatically once that UI
 * lands. `adults` is derived (1 + named companions) — the server reconciles.
 */
export function toCreateBody(draft: ReservationDraft): ReservationCreateBody {
  const { guest, companions, booking } = draft;
  const occupants = buildOccupants(draft);
  const children = companions.has_companions
    ? Math.max(0, companions.children)
    : 0;

  const body: ReservationCreateBody = {
    status: booking.status,
    source: booking.source,
    check_in_date: booking.check_in_date,
    check_out_date: booking.check_out_date,
    expected_arrival_time: booking.expected_arrival_time || null,
    primary_guest: guest.primary_guest_id,
    primary_guest_name:
      guest.full_name.trim() ||
      composeFullName(guest.first_name, guest.father_name, guest.last_name),
    primary_guest_phone: guest.phone.trim() || undefined,
    primary_guest_email: guest.no_email ? undefined : guest.email.trim() || undefined,
    primary_guest_nationality: guest.nationality.trim() || undefined,
    primary_guest_first_name: guest.first_name.trim() || undefined,
    primary_guest_last_name: guest.last_name.trim() || undefined,
    primary_guest_father_name: guest.father_name.trim() || undefined,
    primary_guest_mother_name: guest.mother_name.trim() || undefined,
    // A masked national id is never written back.
    primary_guest_national_id: guest.national_id_masked
      ? undefined
      : guest.national_id.trim() || undefined,
    primary_guest_date_of_birth: guest.date_of_birth || null,
    adults: 1 + occupants.length,
    children,
    lines: buildLines(draft),
  };
  // Informational-only expected method (future reservations); omitted when unset
  // so nothing invalid is ever sent. Constrained to the backend enum by its type.
  if (booking.expected_payment_method) {
    body.expected_payment_method = booking.expected_payment_method;
  }
  if (occupants.length > 0) body.occupants = occupants;
  return body;
}

/**
 * Build the immediate atomic check-in body. Wave 2a fills the `reservation`
 * portion (guest + occupants); Wave 2b finalizes `room`, `deposit` and the FX
 * fields. The deposit is only attached when a method + a positive amount exist.
 */
export function toImmediateCheckInBody(
  draft: ReservationDraft,
): ImmediateCheckInBody {
  const { booking } = draft;
  const p = booking.payment;
  const hasDeposit =
    p.method !== "" &&
    ((p.amount.trim() !== "" && Number(p.amount) > 0) ||
      (p.original_amount.trim() !== "" && Number(p.original_amount) > 0));

  return {
    reservation: toCreateBody(draft),
    room: booking.selected_room_id,
    deposit: hasDeposit
      ? {
          method: p.method as ReservationDepositMethod,
          currency: p.currency || undefined,
          amount: p.amount.trim() || null,
          original_amount: p.original_amount.trim() || null,
          exchange_rate: p.exchange_rate.trim() || null,
          rate_basis: p.rate_basis.trim() || undefined,
        }
      : null,
  };
}

/* -------------------------------------------------------------------------- */
/* Hook                                                                       */
/* -------------------------------------------------------------------------- */

export interface ReservationDraftActions {
  reset: (draft?: ReservationDraft) => void;
  setGuestField: (field: GuestTextField, value: string) => void;
  setFullName: (value: string) => void;
  setNoEmail: (value: boolean) => void;
  applyGuestMatch: (guest: Guest) => void;
  unlinkGuest: () => void;
  setHasCompanions: (value: boolean) => void;
  addOccupant: () => void;
  removeOccupant: (key: string) => void;
  setOccupantField: (
    key: string,
    field: OccupantTextField,
    value: string,
  ) => void;
  setOccupantRelationship: (
    key: string,
    value: OccupantRelationship | "",
  ) => void;
  applyOccupantMatch: (key: string, guest: Guest) => void;
  unlinkOccupant: (key: string) => void;
  setChildren: (value: number) => void;
  patchBooking: (patch: Partial<BookingDraft>) => void;
  patchPayment: (patch: Partial<PaymentDraft>) => void;
  setDocuments: (documents: PendingDocument[]) => void;
}

export interface UseReservationDraft {
  draft: ReservationDraft;
  actions: ReservationDraftActions;
  totalPersons: number;
}

/** The wizard's single source of truth for its in-progress reservation. */
export function useReservationDraft(
  initial?: ReservationDraft,
): UseReservationDraft {
  const [draft, dispatch] = useReducer(
    reducer,
    initial ?? null,
    (seed) => seed ?? createInitialDraft(),
  );

  const actions = useMemo<ReservationDraftActions>(
    () => ({
      reset: (next) =>
        dispatch({ type: "reset", draft: next ?? createInitialDraft() }),
      setGuestField: (field, value) =>
        dispatch({ type: "guest/set", field, value }),
      setFullName: (value) => dispatch({ type: "guest/setFullName", value }),
      setNoEmail: (value) => dispatch({ type: "guest/setNoEmail", value }),
      applyGuestMatch: (guest) => dispatch({ type: "guest/applyMatch", guest }),
      unlinkGuest: () => dispatch({ type: "guest/unlink" }),
      setHasCompanions: (value) =>
        dispatch({ type: "companions/setHas", value }),
      addOccupant: () => dispatch({ type: "companions/addOccupant" }),
      removeOccupant: (key) =>
        dispatch({ type: "companions/removeOccupant", key }),
      setOccupantField: (key, field, value) =>
        dispatch({ type: "companions/setOccupantField", key, field, value }),
      setOccupantRelationship: (key, value) =>
        dispatch({ type: "companions/setOccupantRelationship", key, value }),
      applyOccupantMatch: (key, guest) =>
        dispatch({ type: "companions/applyOccupantMatch", key, guest }),
      unlinkOccupant: (key) =>
        dispatch({ type: "companions/unlinkOccupant", key }),
      setChildren: (value) => dispatch({ type: "companions/setChildren", value }),
      patchBooking: (patch) => dispatch({ type: "booking/patch", patch }),
      patchPayment: (patch) => dispatch({ type: "booking/patchPayment", patch }),
      setDocuments: (documents) => dispatch({ type: "documents/set", documents }),
    }),
    [],
  );

  const total = useMemo(() => totalPersons(draft), [draft]);

  return { draft, actions, totalPersons: total };
}
