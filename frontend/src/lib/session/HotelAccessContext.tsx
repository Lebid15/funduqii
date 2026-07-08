"use client";

/**
 * Effective-permissions context for the hotel console (Phase 11).
 *
 * Loads the CURRENT user's effective permissions in the current hotel once
 * per shell mount and exposes a simple `can()` check used by the sidebar and
 * the route guard. This is purely cosmetic gating — every API enforces the
 * same permissions server-side regardless of what the UI shows.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { getMyPermissions } from "@/lib/api/staff";

export interface HotelAccess {
  loading: boolean;
  isManager: boolean;
  permissions: ReadonlySet<string>;
  /** True when the user holds ANY of the given codes (manager: always). */
  can: (...codes: string[]) => boolean;
  refresh: () => void;
}

const HotelAccessContext = createContext<HotelAccess | null>(null);

export function HotelAccessProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [isManager, setIsManager] = useState(false);
  const [permissions, setPermissions] = useState<ReadonlySet<string>>(new Set());
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getMyPermissions()
      .then((data) => {
        if (cancelled) return;
        setIsManager(data.is_manager);
        setPermissions(new Set(data.permissions));
      })
      .catch(() => {
        if (cancelled) return;
        // On failure fall back to "no cosmetic access"; APIs still decide.
        setIsManager(false);
        setPermissions(new Set());
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const value = useMemo<HotelAccess>(
    () => ({
      loading,
      isManager,
      permissions,
      can: (...codes: string[]) =>
        isManager || codes.some((code) => permissions.has(code)),
      refresh: () => setTick((t) => t + 1),
    }),
    [loading, isManager, permissions],
  );

  return (
    <HotelAccessContext.Provider value={value}>
      {children}
    </HotelAccessContext.Provider>
  );
}

/** Null outside the hotel shell (e.g. the platform console). */
export function useHotelAccess(): HotelAccess | null {
  return useContext(HotelAccessContext);
}
