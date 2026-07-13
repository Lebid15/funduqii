"use client";

/**
 * Debounced smart guest lookup for the reservation wizard
 * (RESERVATIONS-FORM-UX-CORRECTION). Watches a national_id / phone pair,
 * debounces ~400ms, and calls the hotel-scoped exact-match `lookupGuest`. The
 * BACKEND decides matches, masking and blocking — this hook only surfaces the
 * outcome:
 *   - `idle`      — nothing to search (both inputs empty) or lookup disabled
 *   - `searching` — a request is in flight
 *   - `none`      — no match (a new guest will be created)
 *   - `single`    — exactly one candidate (offer to autofill + link)
 *   - `multiple`  — several candidates (let the user pick)
 *   - `conflict`  — the id resolves to ONE guest and the phone to a DIFFERENT
 *                   guest (§7). We never merge or auto-replace in this case.
 *   - `error`     — the lookup failed (fail-soft; the user can still type)
 *
 * When BOTH the id and phone are searchable we issue two exact-match lookups
 * (one per key) so the id↔phone conflict can be detected precisely; otherwise a
 * single lookup runs. A monotonic request id guards against out-of-order
 * responses clobbering a newer search.
 */
import { useEffect, useRef, useState } from "react";

import { lookupGuest } from "@/lib/api/guests";
import type { Guest } from "@/lib/api/types";

const DEBOUNCE_MS = 400;

export type GuestLookupStatus =
  | "idle"
  | "searching"
  | "none"
  | "single"
  | "multiple"
  | "conflict"
  | "error";

export interface GuestLookupState {
  status: GuestLookupStatus;
  results: Guest[];
  /** Present only when `status === "conflict"`: the two different guests the id
   * and phone each resolve to. Never merged/applied automatically. */
  conflict?: { idGuest: Guest; phoneGuest: Guest };
}

export interface UseGuestLookupParams {
  national_id?: string;
  phone?: string;
  /** When false the hook stays idle (e.g. a guest is already linked). */
  enabled?: boolean;
}

/** Masked values contain bullet characters — they are never valid lookup keys. */
function isSearchable(value: string | undefined): boolean {
  const trimmed = (value ?? "").trim();
  return trimmed.length >= 2 && !trimmed.includes("•");
}

/** De-duplicate candidates by guest id, preserving first-seen order. */
function uniqueById(guests: Guest[]): Guest[] {
  const seen = new Set<number>();
  const out: Guest[] = [];
  for (const guest of guests) {
    if (seen.has(guest.id)) continue;
    seen.add(guest.id);
    out.push(guest);
  }
  return out;
}

function statusForCount(count: number): GuestLookupStatus {
  if (count === 0) return "none";
  if (count === 1) return "single";
  return "multiple";
}

export function useGuestLookup({
  national_id,
  phone,
  enabled = true,
}: UseGuestLookupParams): GuestLookupState {
  const [state, setState] = useState<GuestLookupState>({
    status: "idle",
    results: [],
  });
  // Guards against out-of-order responses clobbering a newer search.
  const requestId = useRef(0);

  const nid = isSearchable(national_id) ? national_id!.trim() : "";
  const tel = isSearchable(phone) ? phone!.trim() : "";

  useEffect(() => {
    if (!enabled || (!nid && !tel)) {
      setState({ status: "idle", results: [] });
      return;
    }

    const id = ++requestId.current;
    setState((prev) => ({ status: "searching", results: prev.results }));

    const timer = setTimeout(() => {
      // Two searchable keys → two exact-match lookups so an id↔phone conflict
      // (the id belongs to one guest, the phone to another) can be detected
      // precisely. A single key → one lookup.
      const idLookup = nid
        ? lookupGuest({ national_id: nid })
        : Promise.resolve({ results: [] });
      const phoneLookup = tel
        ? lookupGuest({ phone: tel })
        : Promise.resolve({ results: [] });

      Promise.all([idLookup, phoneLookup])
        .then(([byId, byPhone]) => {
          if (id !== requestId.current) return;
          const idResults = byId.results ?? [];
          const phoneResults = byPhone.results ?? [];

          // Conflict: the id resolves to exactly one guest, the phone to exactly
          // one guest, and they are different people. Do NOT merge or apply.
          if (
            nid &&
            tel &&
            idResults.length === 1 &&
            phoneResults.length === 1 &&
            idResults[0].id !== phoneResults[0].id
          ) {
            setState({
              status: "conflict",
              results: [idResults[0], phoneResults[0]],
              conflict: { idGuest: idResults[0], phoneGuest: phoneResults[0] },
            });
            return;
          }

          const merged = uniqueById([...idResults, ...phoneResults]);
          setState({ status: statusForCount(merged.length), results: merged });
        })
        .catch(() => {
          if (id !== requestId.current) return;
          setState({ status: "error", results: [] });
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [enabled, nid, tel]);

  return state;
}
