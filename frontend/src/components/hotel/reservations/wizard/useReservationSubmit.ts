"use client";

/**
 * Submit orchestration for the reservation wizard (RESERVATIONS-FORM-REWORK,
 * Wave 2b). ONE call encapsulates the two backend flows and the staged-document
 * upload that must follow them:
 *
 *   1. `immediate_check_in` ON  → `immediateCheckIn(toImmediateCheckInBody)`
 *      atomically creates the reservation, opens the stay and (optionally) takes
 *      the deposit; the reservation id comes back on `result.reservation`.
 *   2. `immediate_check_in` OFF → `createReservation(toCreateBody)`.
 *
 * THEN each staged document uploads to the created reservation id. Uploads never
 * roll the reservation back: a failed upload is counted and surfaced to the user
 * so they can retry later from the reservation details. The backend re-validates
 * every file, currency, capacity and permission — nothing here is authoritative.
 */
import { useCallback } from "react";

import {
  createReservation,
  createReservationDeposit,
  immediateCheckIn,
  replaceReservationDocument,
  updateReservation,
  uploadReservationDocument,
} from "@/lib/api/reservations";
import type { ImmediateCheckInResult, Reservation } from "@/lib/api/types";

import {
  buildDepositBody,
  toCreateBody,
  toImmediateCheckInBody,
  toUpdateBody,
  type OccupantDraft,
  type PendingDocument,
  type ReservationDraft,
  type ReservationUpdateOptions,
} from "./useReservationDraft";

export interface ReservationSubmitOutcome {
  reservation: Reservation;
  /** Present only when the immediate atomic check-in path ran. */
  checkIn: ImmediateCheckInResult | null;
  /** True when a deposit was entered on a FUTURE reservation but the deferred
   * `POST /reservations/<id>/payments/` failed — the reservation is still kept
   * (the deposit can be retried from the reservation details). */
  depositFailed: boolean;
  documentsTotal: number;
  documentsFailed: number;
}

/** A companion counts as sent to the API when it carries an identity — the SAME
 * predicate `buildOccupants` uses in `useReservationDraft`, kept local so the
 * draft builder stays the single writer of the request body. */
function isSentOccupant(occupant: OccupantDraft): boolean {
  return (
    occupant.guest_id !== null ||
    occupant.first_name.trim() !== "" ||
    occupant.last_name.trim() !== ""
  );
}

/** Map each staged companion's local key to its server occupant id. The create
 * response returns occupants in the same order the body sent them, so the sent
 * companions line up 1:1 with `reservation.occupants`. When the response omits
 * occupants the map is empty and companion documents upload WITHOUT an occupant
 * link (still attached to the reservation) — never a fabricated id. */
function occupantIdByKey(
  draft: ReservationDraft,
  reservation: Reservation,
): Map<string, number> {
  const map = new Map<string, number>();
  if (!draft.companions.has_companions) return map;
  const server = reservation.occupants ?? [];
  const sent = draft.companions.occupants.filter(isSentOccupant);
  sent.forEach((occupant, index) => {
    const match = server[index];
    if (match) map.set(occupant.key, match.id);
  });
  return map;
}

/** Build the multipart body for one staged document. The browser sets the
 * multipart boundary — never send an explicit Content-Type. Only occupant-
 * targeted documents carry an `occupant` link; the primary guest and reservation-
 * level relationship proofs stay unlinked (occupant = null). The neutral file
 * slots map to the backend's only two: the required `file` → `front_file` and the
 * optional `additionalFile` → `back_file` (no forced front/back, §12). */
function buildDocumentForm(
  doc: PendingDocument,
  occupantIds: Map<string, number>,
): FormData {
  const body = new FormData();
  body.set("doc_type", doc.doc_type);
  // §7.2 — the document number is no longer collected in the wizard, so it is
  // never sent on upload (the display field in details/print is a separate thing).
  if (doc.target.kind === "occupant") {
    const occupantId = occupantIds.get(doc.target.occupantKey);
    if (occupantId !== undefined) body.set("occupant", String(occupantId));
  }
  if (doc.file) body.set("front_file", doc.file);
  if (doc.additionalFile) body.set("back_file", doc.additionalFile);
  return body;
}

/** Upload every staged document (those with a type AND at least one file) in
 * parallel; count the failures without throwing so one bad file never loses the
 * others or the reservation. */
async function uploadStagedDocuments(
  reservation: Reservation,
  draft: ReservationDraft,
): Promise<{ total: number; failed: number }> {
  const staged = draft.pendingDocuments.filter(
    (doc) => doc.doc_type !== "" && (doc.file !== null || doc.additionalFile !== null),
  );
  if (staged.length === 0) return { total: 0, failed: 0 };

  const occupantIds = occupantIdByKey(draft, reservation);
  const results = await Promise.allSettled(
    staged.map((doc) =>
      uploadReservationDocument(reservation.id, buildDocumentForm(doc, occupantIds)),
    ),
  );
  const failed = results.filter((result) => result.status === "rejected").length;
  return { total: staged.length, failed };
}

/** The wizard's single submit action. Throws only on the reservation
 * create / check-in itself (the caller maps that to a friendly message);
 * document upload failures are reported via the returned counts. */
export function useReservationSubmit() {
  return useCallback(
    async (
      draft: ReservationDraft,
      // §7.3 — the number reserved on form open. Replayed into the create body so
      // the server pins the SAME number; null (reserve failed) → server allocates.
      options?: { idempotencyKey?: string | null },
    ): Promise<ReservationSubmitOutcome> => {
      let reservation: Reservation;
      let checkIn: ImmediateCheckInResult | null = null;
      let depositFailed = false;

      if (draft.booking.immediate_check_in) {
        // Immediate: the deposit flows through the atomic orchestration (the
        // stay/folio are opened in the same transaction) — never a second call.
        checkIn = await immediateCheckIn(toImmediateCheckInBody(draft, options));
        reservation = checkIn.reservation;
      } else {
        // Future/held/confirmed: create first, THEN record any deposit against
        // the reservation's pre-arrival folio (§27). A deposit failure never
        // rolls the reservation back — it is surfaced so staff can retry from
        // the reservation details; the reservation itself is kept.
        reservation = await createReservation(toCreateBody(draft, options));
        const deposit = buildDepositBody(draft);
        if (deposit) {
          try {
            await createReservationDeposit(reservation.id, deposit);
          } catch {
            depositFailed = true;
          }
        }
      }

      const { total, failed } = await uploadStagedDocuments(reservation, draft);
      return {
        reservation,
        checkIn,
        depositFailed,
        documentsTotal: total,
        documentsFailed: failed,
      };
    },
    [],
  );
}

/* -------------------------------------------------------------------------- */
/* Edit save (RESERVATIONS-FORM-UX-CORRECTION §33)                            */
/* -------------------------------------------------------------------------- */

export interface ReservationEditOutcome {
  reservation: Reservation;
  /** A NEW deposit was entered on this (stayless) reservation but the deferred
   * `POST /reservations/<id>/payments/` failed — the edit is still saved. */
  depositFailed: boolean;
  documentsTotal: number;
  documentsFailed: number;
}

export interface ReservationEditOptions extends ReservationUpdateOptions {
  /** A new pre-arrival deposit is only recorded when the reservation has NO stay
   * yet AND the user holds `finance.payment_create` (both decided in the shell).
   * The backend re-enforces the permission regardless. */
  allowNewDeposit: boolean;
}

/** True when an EXISTING document needs the replace endpoint: a new file was
 * staged, or the document type changed. Otherwise the saved document is left
 * untouched — an edit never re-uploads what is on file. */
function needsReplace(doc: PendingDocument): boolean {
  const existing = doc.existing;
  if (!existing) return false;
  if (doc.file !== null || doc.additionalFile !== null) return true;
  // §7.2 removed the document-number field, so `doc.number` always equals the
  // hydrated existing value and `buildReplaceForm` never sends it — the former
  // `numberChanged` branch was dead. Replace now fires only on a real trigger: a
  // new file (handled above) or a document-type change.
  const typeChanged = doc.doc_type !== "" && doc.doc_type !== existing.doc_type;
  return typeChanged;
}

/** Multipart body for REPLACING a saved document. Only CHANGED, non-masked
 * metadata is sent (a masked number is never round-tripped); the occupant link
 * is left as the server already stored it. */
function buildReplaceForm(doc: PendingDocument): FormData {
  const existing = doc.existing;
  const body = new FormData();
  if (doc.doc_type && doc.doc_type !== existing?.doc_type) {
    body.set("doc_type", doc.doc_type);
  }
  // §7.2 — the document number is no longer collected in the wizard; a replace
  // never sends it, leaving whatever is on file untouched.
  if (doc.file) body.set("front_file", doc.file);
  if (doc.additionalFile) body.set("back_file", doc.additionalFile);
  return body;
}

/** Sync the documents step against an edited reservation: REPLACE saved docs that
 * changed and UPLOAD brand-new staged docs (occupant link resolved by the same
 * order-based map create uses). Failures are counted, never thrown, so one bad
 * file never loses the others or the reservation edit. */
async function syncEditDocuments(
  reservation: Reservation,
  draft: ReservationDraft,
): Promise<{ total: number; failed: number }> {
  const occupantIds = occupantIdByKey(draft, reservation);
  const tasks: Promise<unknown>[] = [];
  for (const doc of draft.pendingDocuments) {
    if (doc.existing) {
      if (needsReplace(doc)) {
        tasks.push(replaceReservationDocument(doc.existing.id, buildReplaceForm(doc)));
      }
    } else if (doc.doc_type !== "" && (doc.file !== null || doc.additionalFile !== null)) {
      tasks.push(uploadReservationDocument(reservation.id, buildDocumentForm(doc, occupantIds)));
    }
  }
  if (tasks.length === 0) return { total: 0, failed: 0 };
  const results = await Promise.allSettled(tasks);
  const failed = results.filter((result) => result.status === "rejected").length;
  return { total: tasks.length, failed };
}

/**
 * §33 — the wizard's EDIT save. PATCHes the reservation fields/occupants
 * (`updateReservation`, stay-owned dates/rooms omitted when locked), records a
 * NEW deposit through the deposit endpoint (never re-submitting an existing
 * payment — §31), then replaces/uploads documents through their own endpoints.
 * Immediate check-in is NEVER run from edit. Throws only on the PATCH itself; a
 * deposit or document failure is surfaced via the returned counts.
 */
export function useReservationEditSubmit() {
  return useCallback(
    async (
      reservationId: number,
      draft: ReservationDraft,
      options: ReservationEditOptions,
    ): Promise<ReservationEditOutcome> => {
      const reservation = await updateReservation(
        reservationId,
        toUpdateBody(draft, options),
      );

      let depositFailed = false;
      if (options.allowNewDeposit) {
        const deposit = buildDepositBody(draft);
        if (deposit) {
          try {
            await createReservationDeposit(reservationId, deposit);
          } catch {
            depositFailed = true;
          }
        }
      }

      const { total, failed } = await syncEditDocuments(reservation, draft);
      return {
        reservation,
        depositFailed,
        documentsTotal: total,
        documentsFailed: failed,
      };
    },
    [],
  );
}
