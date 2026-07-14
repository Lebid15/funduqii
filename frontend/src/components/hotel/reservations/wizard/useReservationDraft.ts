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
  ReservationUpdateBody,
  RoomAssignmentMode,
} from "@/lib/api/reservations";
import type {
  Guest,
  OccupantRelationship,
  Reservation,
  ReservationDepositBody,
  ReservationDepositMethod,
  ReservationDocument,
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

/** How the companions relate to the primary guest. CLIENT-ONLY for now: the
 * backend has no `group_type` field, so it is never sent in the create body
 * (see `toCreateBody`). It drives the family relationship-proof section of the
 * documents step (`my_family`). */
export type CompanionGroupType = "companions" | "my_family";

export interface CompanionsDraft {
  has_companions: boolean;
  /** Companions vs. one family unit — client-only, gates family-proof docs. */
  group_type: CompanionGroupType;
  occupants: OccupantDraft[];
  /** Count only — no per-child fields are collected. */
  children: number;
}

/** Which subject a staged document belongs to. The `occupant` variant carries
 * the STABLE `OccupantDraft.key` (never an array index) so removing or reordering
 * companions can never swap a document onto the wrong person. `relationship_proof`
 * documents (marriage contract / family record) attach at the RESERVATION level
 * (occupant = null) — never to an individual child. */
export type DocumentTarget =
  | { kind: "primary" }
  | { kind: "occupant"; occupantKey: string }
  | { kind: "relationship_proof" };

/** Step 3 — a document staged in the UI and uploaded as PART of Save (the create
 * flow returns the reservation id the upload needs; there is no separate
 * "upload later" step). The owner (§12) forbids FORCING a front/back requirement,
 * and the backend `ReservationDocument` exposes exactly TWO file slots — so each
 * document models ONE required `file` plus ONE OPTIONAL `additionalFile` under
 * neutral labels. At submit `file` maps to `front_file` and `additionalFile` to
 * `back_file` (see `useReservationSubmit`). */
export interface PendingDocument {
  key: string;
  target: DocumentTarget;
  doc_type: ReservationDocumentType;
  number: string;
  file: File | null;
  additionalFile: File | null;
  /** EDIT prefill (§33) — the SAVED server document this card represents. When
   * set, the card shows an "on file" state with View/Replace and is NOT
   * re-staged as a new upload: on save it goes through the REPLACE endpoint only
   * if a new file or changed metadata was staged (see `useReservationEditSubmit`).
   * `null`/absent means a brand-new document staged in the create/edit form. */
  existing?: ReservationDocument | null;
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
  /** The floor chosen in the SEPARATE floor picker (§23) — gates the room list
   * and travels as the auto/manual floor criteria on the line. Client-only. */
  selected_floor_id: number | null;
  /** RESERVATIONS-AUTO-ROOM: how the room is chosen. `"automatic"` (default) →
   * the backend assigns an available room from the floor/type/dates criteria and
   * the client pins nothing; `"manual"` → the staff pick a specific room. */
  room_assignment_mode: RoomAssignmentMode;
  /** The physical room chosen in MANUAL mode (the "manual room id"). Null in
   * automatic mode — the final room comes back on the save response (§5). */
  selected_room_id: number | null;
  source: ReservationSource;
  status: "held" | "confirmed";
  payment: PaymentDraft;
  /** Free-text internal notes for the reservation (§19 section 6). */
  notes: string;
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
      group_type: "companions",
      occupants: [],
      children: 0,
    },
    pendingDocuments: [],
    booking: {
      check_in_date: "",
      check_out_date: "",
      expected_arrival_time: "",
      lines: [{ room_type: "", room: "", quantity: "1" }],
      selected_floor_id: null,
      // RESERVATIONS-AUTO-ROOM §2 — automatic room selection is the default.
      room_assignment_mode: "automatic",
      selected_room_id: null,
      source: "direct",
      status: "confirmed",
      payment: {
        method: "",
        currency: "",
        amount: "",
        original_amount: "",
        exchange_rate: "",
        rate_basis: "",
      },
      notes: "",
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
  | { type: "guest/setNoEmail"; value: boolean }
  | { type: "guest/applyMatch"; guest: Guest }
  | { type: "guest/unlink" }
  | { type: "companions/setHas"; value: boolean }
  | { type: "companions/setGroupType"; value: CompanionGroupType }
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

/** The display full name is ALWAYS derived from the structured parts — staff
 * never type it (RESERVATIONS-FORM-UX-CORRECTION §6). `full_name_touched` stays
 * on the shape for older callers but no longer gates composition. */
function recomposeGuest(guest: GuestDraft): GuestDraft {
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
        // Derived, never the raw stored name — keeps the snapshot consistent
        // with the (display-only) structured parts shown to staff.
        full_name: composeFullName(
          g.first_name ?? "",
          g.father_name ?? "",
          g.last_name ?? "",
        ),
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

    case "companions/setGroupType":
      return {
        ...state,
        companions: { ...state.companions, group_type: action.value },
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

/** Map the booking-line drafts into API line bodies. Empty rows are dropped and
 * the chosen floor travels as the auto/manual criteria (RESERVATIONS-AUTO-ROOM).
 * In AUTOMATIC mode the room id is NEVER sent — the backend assigns it — so the
 * client stays honest even though the server would drop a pinned room anyway. A
 * pinned (manual) room forces quantity 1. */
function buildLines(draft: ReservationDraft): ReservationLineBody[] {
  const automatic = draft.booking.room_assignment_mode === "automatic";
  const floor = draft.booking.selected_floor_id;
  return draft.booking.lines
    .filter((line) => line.room_type)
    .map((line) => {
      const room = automatic ? null : line.room ? Number(line.room) : null;
      const body: ReservationLineBody = {
        room_type: Number(line.room_type),
        room,
        quantity: room != null ? 1 : Number(line.quantity) || 1,
      };
      if (floor != null) body.floor = floor;
      return body;
    });
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
    // RESERVATIONS-AUTO-ROOM §5 — the mode decides whether the backend assigns
    // the room (automatic) or honours the pinned room on the line (manual).
    room_assignment_mode: booking.room_assignment_mode,
  };
  // Free-text internal notes (§19 section 6); omitted when empty.
  const notes = booking.notes.trim();
  if (notes) body.notes = notes;
  if (occupants.length > 0) body.occupants = occupants;
  return body;
}

/**
 * Build the FX-aware deposit body from the payment sub-draft, or `null` when no
 * real payment was entered. A deposit exists only when a method is chosen AND a
 * positive amount (base OR foreign original) is present — a zero/blank amount
 * records nothing (§28). Shared by BOTH money paths: the immediate atomic
 * check-in (embedded in `toImmediateCheckInBody`) and the deferred
 * deposit-for-future (`POST /reservations/<id>/payments/`, §27). Money fields
 * stay decimal STRINGS — never parsed to Float here. `on_room_account` clears
 * the method to "", so it correctly yields no deposit.
 */
export function buildDepositBody(
  draft: ReservationDraft,
): ReservationDepositBody | null {
  const p = draft.booking.payment;
  const hasDeposit =
    p.method !== "" &&
    ((p.amount.trim() !== "" && Number(p.amount) > 0) ||
      (p.original_amount.trim() !== "" && Number(p.original_amount) > 0));
  if (!hasDeposit) return null;
  return {
    method: p.method as ReservationDepositMethod,
    currency: p.currency || undefined,
    amount: p.amount.trim() || null,
    original_amount: p.original_amount.trim() || null,
    exchange_rate: p.exchange_rate.trim() || null,
    rate_basis: p.rate_basis.trim() || undefined,
  };
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
  return {
    reservation: toCreateBody(draft),
    // RESERVATIONS-AUTO-ROOM §5 — never pin a room in automatic mode; the backend
    // assigns it on the line and the check-in admits into that assigned room.
    room:
      booking.room_assignment_mode === "manual" ? booking.selected_room_id : null,
    deposit: buildDepositBody(draft),
  };
}

/* -------------------------------------------------------------------------- */
/* Edit prefill + update body (RESERVATIONS-FORM-UX-CORRECTION §33)           */
/* -------------------------------------------------------------------------- */

/** Companion relationships that mark the group as ONE family unit — used to
 * infer `group_type` when prefilling an edit (the backend stores no group flag,
 * §33: spouse / adult child / parent → "my_family"). Everything else (sibling /
 * relative / other / none) stays plain "companions". */
const FAMILY_RELATIONSHIPS: ReadonlySet<OccupantRelationship> = new Set([
  "spouse",
  "child_adult",
  "parent",
]);

/** Reservation-level document types that attach as relationship / family proof
 * (occupant = null) rather than to the primary guest. */
const RELATIONSHIP_DOC_TYPES: ReadonlySet<ReservationDocumentType> = new Set([
  "marriage_contract",
  "family_book",
  "family_statement",
]);

/** Read-only server data that seeds an EDIT draft alongside the reservation:
 * existing documents (shown "on file", never re-staged) drive the documents step.
 * The financial summary is DISPLAY-only and never enters the mutable draft (§31 —
 * an old transaction is never editable as a form field); it is threaded to the
 * booking step as a separate read-only prop, so it is intentionally absent here. */
export interface ReservationToDraftExtras {
  documents?: ReservationDocument[];
}

/**
 * §33 — build a full `ReservationDraft` from a SAVED reservation so EDIT uses the
 * exact same wizard as CREATE. Maps the primary guest's structured snapshot (+
 * central-guest link, masked national id never round-tripped), each
 * `ReservationOccupant` → an `OccupantDraft` with a STABLE local key (so a doc's
 * occupant linkage survives), the children count, dates/times, the booked
 * room/line, notes and source. Existing documents are attached as `existing`
 * refs — shown on file with View/Replace, never re-uploaded. The financial
 * summary is DISPLAY-only and is passed to the booking step separately, never
 * folded into this editable draft.
 */
export function reservationToDraft(
  reservation: Reservation,
  extras?: ReservationToDraftExtras,
): ReservationDraft {
  const draft = createInitialDraft();

  // --- Primary guest (structured snapshot + link) ---
  const guestMasked = isMaskedValue(reservation.primary_guest_national_id);
  const guestEmail = reservation.primary_guest_email ?? "";
  draft.guest = {
    ...draft.guest,
    primary_guest_id: reservation.primary_guest,
    national_id: guestMasked ? "" : reservation.primary_guest_national_id ?? "",
    national_id_masked: guestMasked,
    first_name: reservation.primary_guest_first_name ?? "",
    last_name: reservation.primary_guest_last_name ?? "",
    father_name: reservation.primary_guest_father_name ?? "",
    mother_name: reservation.primary_guest_mother_name ?? "",
    nationality: reservation.primary_guest_nationality ?? "",
    date_of_birth: reservation.primary_guest_date_of_birth ?? "",
    phone: reservation.primary_guest_phone ?? "",
    email: guestEmail,
    // §33 — the create form's "no email" toggle clears the address; a saved
    // reservation with an empty email is hydrated back into that state so an
    // edit shows the toggle ON instead of a seemingly-missing required field.
    no_email: guestEmail.trim() === "",
    full_name: reservation.primary_guest_name ?? "",
    full_name_touched: true,
    is_blocked: false,
  };

  // --- Adult companions (+ a server-id → local-key map for document linkage) ---
  const serverOccupants = reservation.occupants ?? [];
  const occupantIdToKey = new Map<number, string>();
  const occupants: OccupantDraft[] = serverOccupants.map((occ) => {
    const key = uid("occ");
    occupantIdToKey.set(occ.id, key);
    const occMasked = isMaskedValue(occ.national_id);
    return {
      key,
      guest_id: occ.guest,
      first_name: occ.first_name ?? "",
      last_name: occ.last_name ?? "",
      father_name: occ.father_name ?? "",
      mother_name: occ.mother_name ?? "",
      national_id: occMasked ? "" : occ.national_id ?? "",
      national_id_masked: occMasked,
      nationality: occ.nationality ?? "",
      date_of_birth: occ.date_of_birth ?? "",
      relationship: occ.relationship ?? "",
    };
  });
  const children = Math.max(0, reservation.children ?? 0);
  const groupType: CompanionGroupType = occupants.some(
    (occupant) =>
      occupant.relationship !== "" &&
      FAMILY_RELATIONSHIPS.has(occupant.relationship),
  )
    ? "my_family"
    : "companions";
  draft.companions = {
    has_companions: occupants.length > 0 || children > 0,
    group_type: groupType,
    occupants,
    children,
  };

  // --- Existing documents (metadata only — shown on file, never re-staged) ---
  const documents = extras?.documents ?? [];
  draft.pendingDocuments = documents.map((serverDoc) => {
    let target: DocumentTarget;
    if (serverDoc.occupant != null) {
      // Linked to a companion by STABLE key (falls back to a fresh key so an
      // orphaned link never collides with the primary/proof cards).
      target = {
        kind: "occupant",
        occupantKey: occupantIdToKey.get(serverDoc.occupant) ?? uid("occ-orphan"),
      };
    } else if (RELATIONSHIP_DOC_TYPES.has(serverDoc.doc_type)) {
      target = { kind: "relationship_proof" };
    } else {
      target = { kind: "primary" };
    }
    return {
      key: uid("doc"),
      target,
      doc_type: serverDoc.doc_type,
      number: serverDoc.number ?? "",
      file: null,
      additionalFile: null,
      existing: serverDoc,
    };
  });

  // --- Booking (dates / times / booked line / source / notes) ---
  // §7 — an assigned reservation opens in MANUAL with its CURRENT room kept (never
  // auto-reassigned on open); an unpinned/legacy line opens in automatic. The
  // staff may still switch modes or re-pick a room from the booking step.
  const assignedRoomId = reservation.lines.find((line) => line.room)?.room ?? null;
  draft.booking = {
    ...draft.booking,
    check_in_date: reservation.check_in_date,
    check_out_date: reservation.check_out_date,
    expected_arrival_time: reservation.expected_arrival_time ?? "",
    lines:
      reservation.lines.length > 0
        ? reservation.lines.map((line) => ({
            room_type: String(line.room_type),
            room: line.room ? String(line.room) : "",
            quantity: String(line.quantity),
          }))
        : draft.booking.lines,
    selected_room_id: assignedRoomId,
    room_assignment_mode: assignedRoomId != null ? "manual" : "automatic",
    source: reservation.source,
    status: reservation.status === "held" ? "held" : "confirmed",
    notes: reservation.notes ?? "",
    immediate_check_in: false,
  };

  return draft;
}

/** How the reservation PATCH treats stay-owned fields (§25/§33). */
export interface ReservationUpdateOptions {
  /** When the reservation has a real stay (in-house / checked-out), dates, rooms
   * and arrival time are owned by the stay service — they are OMITTED from the
   * PATCH so an edit can never silently re-book a started stay. */
  lockStayFields: boolean;
}

/**
 * §33 — build the reservation PATCH body from the draft. Reuses the create
 * builder (guest snapshot + occupants + children + dates + lines + notes), then
 * drops `status` (backend-owned, never a free selector on edit — §25) and, when
 * a real stay exists, the stay-owned dates/rooms. Documents and a NEW deposit are
 * NOT part of this body — they go through their own endpoints in the edit submit.
 */
export function toUpdateBody(
  draft: ReservationDraft,
  options: ReservationUpdateOptions,
): ReservationUpdateBody {
  const { status, ...rest } = toCreateBody(draft);
  void status; // backend-owned on edit (§25)
  const body: ReservationUpdateBody = { ...rest };
  if (options.lockStayFields) {
    delete body.check_in_date;
    delete body.check_out_date;
    delete body.expected_arrival_time;
    delete body.lines;
  }
  return body;
}

/* -------------------------------------------------------------------------- */
/* Hook                                                                       */
/* -------------------------------------------------------------------------- */

export interface ReservationDraftActions {
  reset: (draft?: ReservationDraft) => void;
  setGuestField: (field: GuestTextField, value: string) => void;
  setNoEmail: (value: boolean) => void;
  applyGuestMatch: (guest: Guest) => void;
  unlinkGuest: () => void;
  setHasCompanions: (value: boolean) => void;
  setGroupType: (value: CompanionGroupType) => void;
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
      setNoEmail: (value) => dispatch({ type: "guest/setNoEmail", value }),
      applyGuestMatch: (guest) => dispatch({ type: "guest/applyMatch", guest }),
      unlinkGuest: () => dispatch({ type: "guest/unlink" }),
      setHasCompanions: (value) =>
        dispatch({ type: "companions/setHas", value }),
      setGroupType: (value) =>
        dispatch({ type: "companions/setGroupType", value }),
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
