"use client";

import { useEffect, useState } from "react";

import { getSettings } from "@/lib/api/hotel";
import type { ServiceOutlet } from "@/lib/api/types";

const ALL_OUTLETS: ServiceOutlet[] = ["restaurant", "cafe"];

/**
 * Cosmetic outlet gating for CREATION paths (orders, tables, catalog): reads
 * the hotel settings once per mount and hides a disabled outlet from create
 * selects. When the caller lacks `settings.view` (or the fetch fails) both
 * outlets stay selectable — the backend re-checks every write and returns
 * `outlet_disabled` regardless. Existing data is never hidden by this.
 */
export function useEnabledOutlets(): ServiceOutlet[] {
  const [enabled, setEnabled] = useState<ServiceOutlet[]>(ALL_OUTLETS);
  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((s) => {
        if (cancelled) return;
        setEnabled(
          ALL_OUTLETS.filter((o) =>
            o === "restaurant" ? s.restaurant_enabled : s.cafe_enabled,
          ),
        );
      })
      .catch(() => {
        // Cosmetic only — keep both outlets; the API still enforces.
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return enabled;
}
