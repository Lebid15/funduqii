"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { getProfile } from "@/lib/api/hotel";
import type { HotelProfile } from "@/lib/api/types";

/**
 * The current hotel's profile (identity + subscription state), loaded ONCE
 * per shell mount and shared by the sidebar brand slot and the subscription
 * banner — instead of each fetching it separately. `null` while loading or
 * outside the hotel shell; consumers render graceful fallbacks.
 */
const HotelProfileContext = createContext<HotelProfile | null>(null);

export function HotelProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<HotelProfile | null>(null);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => setProfile(null));
  }, []);

  return (
    <HotelProfileContext.Provider value={profile}>
      {children}
    </HotelProfileContext.Provider>
  );
}

export function useHotelProfile(): HotelProfile | null {
  return useContext(HotelProfileContext);
}
