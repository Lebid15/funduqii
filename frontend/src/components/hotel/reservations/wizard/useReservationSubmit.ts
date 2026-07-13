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
  immediateCheckIn,
  uploadReservationDocument,
} from "@/lib/api/reservations";
import type { ImmediateCheckInResult, Reservation } from "@/lib/api/types";

import {
  toCreateBody,
  toImmediateCheckInBody,
  type OccupantDraft,
  type PendingDocument,
  type ReservationDraft,
} from "./useReservationDraft";

export interface ReservationSubmitOutcome {
  reservation: Reservation;
  /** Present only when the immediate atomic check-in path ran. */
  checkIn: ImmediateCheckInResult | null;
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
 * multipart boundary — never send an explicit Content-Type. */
function buildDocumentForm(
  doc: PendingDocument,
  occupantIds: Map<string, number>,
): FormData {
  const body = new FormData();
  body.set("doc_type", doc.doc_type);
  const number = doc.number.trim();
  if (number) body.set("number", number);
  if (doc.occupantKey) {
    const occupantId = occupantIds.get(doc.occupantKey);
    if (occupantId !== undefined) body.set("occupant", String(occupantId));
  }
  if (doc.front_file) body.set("front_file", doc.front_file);
  if (doc.back_file) body.set("back_file", doc.back_file);
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
    (doc) => doc.doc_type !== "" && (doc.front_file !== null || doc.back_file !== null),
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
    async (draft: ReservationDraft): Promise<ReservationSubmitOutcome> => {
      let reservation: Reservation;
      let checkIn: ImmediateCheckInResult | null = null;

      if (draft.booking.immediate_check_in) {
        checkIn = await immediateCheckIn(toImmediateCheckInBody(draft));
        reservation = checkIn.reservation;
      } else {
        reservation = await createReservation(toCreateBody(draft));
      }

      const { total, failed } = await uploadStagedDocuments(reservation, draft);
      return {
        reservation,
        checkIn,
        documentsTotal: total,
        documentsFailed: failed,
      };
    },
    [],
  );
}
