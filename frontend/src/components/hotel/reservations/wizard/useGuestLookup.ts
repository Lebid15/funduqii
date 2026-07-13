"use client";

/**
 * Debounced smart guest lookup for the reservation wizard
 * (RESERVATIONS-FORM-REWORK). Watches a national_id / phone pair, debounces
 * ~400ms, and calls the hotel-scoped exact-match `lookupGuest`. The BACKEND
 * decides matches, masking and blocking — this hook only surfaces the outcome:
 *   - `idle`      — nothing to search (both inputs empty) or lookup disabled
 *   - `searching` — a request is in flight
 *   - `none`      — no match (a new guest will be created)
 *   - `single`    — exactly one candidate (offer to autofill + link)
 *   - `multiple`  — several candidates (let the user pick)
 *   - `error`     — the lookup failed (fail-soft; the user can still type)
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
  | "error";

export interface GuestLookupState {
  status: GuestLookupStatus;
  results: Guest[];
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
      lookupGuest({ national_id: nid || undefined, phone: tel || undefined })
        .then((data) => {
          if (id !== requestId.current) return;
          const results = data.results ?? [];
          setState({
            status:
              results.length === 0
                ? "none"
                : results.length === 1
                  ? "single"
                  : "multiple",
            results,
          });
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
