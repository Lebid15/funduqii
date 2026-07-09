"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  getPublicSiteSettings,
  type PublicSiteSettings,
} from "@/lib/api/public";

/**
 * Phase 16 — the platform owner's public-site settings, loaded once per
 * public page tree. `null` while loading or on failure: consumers fall back
 * to the built-in dictionary texts, so the public site never breaks because
 * of missing admin configuration.
 */
const SiteSettingsContext = createContext<PublicSiteSettings | null>(null);

export function SiteSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<PublicSiteSettings | null>(null);

  useEffect(() => {
    getPublicSiteSettings()
      .then(setSettings)
      .catch(() => setSettings(null));
  }, []);

  return (
    <SiteSettingsContext.Provider value={settings}>
      {children}
    </SiteSettingsContext.Provider>
  );
}

export function useSiteSettings(): PublicSiteSettings | null {
  return useContext(SiteSettingsContext);
}
